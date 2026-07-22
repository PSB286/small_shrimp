"""
云端 LLM 封装 - 增强错误处理
"""

import json
import requests
from config import settings
from utils.logger import logger


class CloudEngine:
    def __init__(self):
        self.api_key = settings.api_key
        self.api_url = settings.api_url
        self.skills_info = {}

    def set_skills_info(self, skills_info):
        """注入技能列表"""
        self.skills_info = skills_info

    def chat(self, user_input: str, history: list):
        """调用云端 API"""
        # 构建系统提示
        system_prompt = f"""
你是智能助手，必须输出纯 JSON。可用工具：
{json.dumps(self.skills_info, indent=2, ensure_ascii=False)}

输出格式：
1. 完成任务：{{"answer": "答案", "status": "done"}}
2. 调用工具：{{"action": "工具名", "params": {{}}, "status": "continue"}}
3. 无法解决：{{"answer": "原因", "status": "give_up"}}

【重要规则】
- 对于"增加xxx功能"或"添加xxx技能"，应调用 skill_manager 添加技能
- 对于需要记忆的信息，应调用 learn_preference
- 如果用户说"再x3"，先询问上一次计算的结果
"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            *history[-10:],  # 只保留最近10条对话
            {"role": "user", "content": user_input}
        ]
        
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": messages,
                    "temperature": 0.1
                },
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"[Cloud] API 错误: {response.status_code}")
                # 降级到本地处理
                return self._fallback_response(user_input)
            
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            # 尝试解析 JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # 如果返回的不是 JSON，尝试提取
                return self._extract_json_from_text(content)
                
        except requests.exceptions.Timeout:
            logger.error("[Cloud] API 超时")
            return self._fallback_response(user_input)
        except Exception as e:
            logger.error(f"[Cloud] 调用失败: {e}")
            return {"status": "give_up", "answer": f"调用失败: {str(e)}"}

    def _extract_json_from_text(self, text: str):
        """从文本中提取 JSON"""
        try:
            # 查找 JSON 对象
            import re
            match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except:
            pass
        # 返回文本作为答案
        return {"status": "done", "answer": text}

    def _fallback_response(self, user_input: str):
        """降级响应"""
        # 检查是否包含"增加"、"添加"等关键词
        if any(kw in user_input for kw in ["增加", "添加", "创建"]):
            return {
                "status": "continue",
                "action": "skill_manager",
                "params": {
                    "action": "add",
                    "skill_name": "new_skill",
                    "description": user_input
                }
            }
        return {
            "status": "done",
            "answer": "抱歉，我暂时无法处理这个请求。请确保网络连接正常，或尝试更简单的指令。"
        }