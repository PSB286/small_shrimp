"""
Agent 核心循环 - 增强上下文支持 + 修改技能
"""

from llm.router import ModelRouter
from core.skill_manager import SkillManager
from memory.compressed_memory import CompressedMemory
from utils.logger import logger
from config import settings
from llm.cloud_engine import CloudEngine
import json
import os
import re


class AgentLoop:
    def __init__(self):
        self.skills = SkillManager()
        self.router = ModelRouter()
        self.router.set_skill_manager(self.skills)  # 注入技能管理器
        self.memory = CompressedMemory()
        self.cloud = CloudEngine()
        self.max_steps = settings.max_steps

        # 上下文
        self.context = {}

        self.cloud.set_skills_info(self.skills.get_skills_info())

    def run(self, user_input: str, history: list = None) -> str:
        """主入口"""
        if history is None:
            history = []

        logger.info(f"[Agent] 处理: {user_input[:50]}...")

        # 1. 获取本地意图
        intent = self.router.local.classify(user_input)
        intent_type = intent.get("type")

        # 2. 处理技能管理类意图
        if intent_type == "list_skills":
            return self.skills.list_skills_formatted()

        if intent_type == "delete_skill":
            return self._handle_delete_skill(user_input)

        if intent_type == "modify_skill":
            return self._handle_modify_skill(user_input, history)

        # 3. 尝试本地处理（传递上下文）
        local_result = self.router.route_local(user_input)
        if local_result:
            # 更新上下文
            if "计算结果" in local_result:
                try:
                    nums = re.findall(r'[\d.]+', local_result)
                    if nums:
                        self.context["last_math_result"] = float(nums[-1])
                except:
                    pass
            return local_result

        # 4. 云端推理
        for attempt in range(settings.max_retries):
            try:
                result = self._execute_cloud(user_input, history)
                if result and not result.startswith("[错误]"):
                    return result
                logger.warning(f"[Agent] 第 {attempt+1} 次尝试失败")
            except Exception as e:
                logger.error(f"[Agent] 执行异常: {e}")

        # 5. 最终降级
        return self._fallback_response(user_input)

    def _handle_delete_skill(self, user_input: str) -> str:
        """处理删除技能请求"""
        skill_name = self.router.local.extract_skill_name(user_input)
        if not skill_name:
            # 尝试更宽松的匹配
            match = re.search(r'删除\s*(\w+)', user_input)
            if match:
                skill_name = match.group(1)

        if not skill_name:
            return "请指定要删除的技能名称，例如：'删除技能 screenshot'"

        return self.skills.delete_skill(skill_name)

    def _handle_modify_skill(self, user_input: str, history: list) -> str:
        """处理修改技能请求"""
        # 1. 提取技能名称
        skill_name = self.router.local.extract_skill_name(user_input)
        if not skill_name:
            # 尝试更宽松的匹配
            match = re.search(r'(?:修改|改一下|把)\s*(\w+)\s*(?:技能)?', user_input)
            if match:
                skill_name = match.group(1)

        if not skill_name:
            return "请指定要修改的技能名称，例如：'修改技能 screenshot，改成只截一张图'"

        # 2. 检查技能是否存在
        if not self.skills.skill_exists(skill_name):
            return f"[错误] 未找到技能: {skill_name}，请检查技能名称是否正确。"

        # 3. 获取原始代码
        original_code = self.skills.get_skill_code(skill_name)
        if not original_code:
            return f"[错误] 无法读取技能 {skill_name} 的代码"

        # 4. 构建 LLM 请求
        system_prompt = """你是一个技能修改助手。用户想要修改一个技能，请根据用户的修改要求，修改原始代码。

重要规则：
1. 保持函数名和参数不变
2. 只修改函数内部的逻辑
3. 保持 __skill_meta__ 元数据（如果有）
4. 只返回修改后的完整代码，不要有任何解释或额外文字"""

        full_prompt = (
            f"用户修改要求：{user_input}\n\n"
            f"原始技能代码（{skill_name}.py）：\n"
            f"```python\n{original_code}\n```\n\n"
            f"请根据用户要求修改代码，只返回修改后的完整代码。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt}
        ]

        # 5. 调用云端 LLM
        try:
            result = self.cloud.chat(messages)

            # 解析结果
            new_code = None
            if isinstance(result, dict):
                new_code = result.get("new_code") or result.get("answer")
            elif isinstance(result, str):
                # 尝试提取代码块
                code_match = re.search(r'```python\s*(.*?)\s*```', result, re.DOTALL)
                if code_match:
                    new_code = code_match.group(1)
                else:
                    # 尝试直接提取
                    new_code = result.strip()

            if new_code:
                # 清理可能的额外标记
                new_code = new_code.strip()
                return self.skills.modify_skill(skill_name, new_code)
            else:
                return f"[错误] LLM 未能生成修改后的代码: {str(result)[:200]}"

        except Exception as e:
            return f"[错误] 修改技能失败: {str(e)}"

    def _execute_cloud(self, user_input: str, history: list) -> str:
        """云端推理 - 执行技能后直接返回，防止重复调用"""
        step = 0
        while step < self.max_steps:
            step += 1

            result = self.router.route_cloud(user_input, history)

            if isinstance(result, str):
                return result

            if isinstance(result, dict):
                status = result.get("status", "")

                if status == "done":
                    return result.get("answer", "已完成")

                if status == "give_up":
                    return result.get("answer", "无法解决")

                if status == "continue":
                    action = result.get("action")
                    params = result.get("params", {})

                    # 执行技能
                    output = self.skills.execute(action, params)

                    # 🔥 关键修改：无论执行结果如何，直接返回，不再继续循环
                    if output and output.startswith("[错误]"):
                        return output
                    return output  # 直接返回，避免重复调用

            return "[错误] AI 输出格式异常"

        return f"[错误] 超过最大步骤限制 ({self.max_steps} 步)"

    def _fallback_response(self, user_input: str) -> str:
        """降级响应"""
        if any(kw in user_input for kw in ["增加", "添加", "创建", "加一个"]):
            return "要添加新功能，请说 '增加技能：功能名'，例如 '增加技能：计算器'"
        if any(kw in user_input for kw in ["修改", "改一下", "改成"]):
            return "要修改技能，请说 '修改技能 [技能名]，改成 [新功能描述]'，例如 '修改技能 screenshot，改成只截一张图'"
        if any(kw in user_input for kw in ["删除", "移除", "去掉"]):
            return "要删除技能，请说 '删除技能 [技能名]'，例如 '删除技能 screenshot'"
        if any(kw in user_input for kw in ["技能", "有哪些"]):
            return "要查看所有技能，请说 '列出技能'"
        return "抱歉，我没能理解你的意思。你可以试试：\n- 数学计算：3+5\n- 时间查询：现在几点\n- 查看技能：列出技能\n- 修改技能：修改技能 screenshot，改成只截一张图"