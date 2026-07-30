"""
云端 LLM 封装 - 纯文本交互，不强制 JSON
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
        self.agent_name = "GGB小虾米"
        self.memory_context = ""

    def set_skills_info(self, skills_info):
        """注入技能列表"""
        self.skills_info = skills_info

    def set_agent_name(self, name: str):
        """设置Agent名称"""
        if name and len(name) <= 20:
            self.agent_name = name
            logger.info(f"[CloudEngine] 名称已更新: {name}")

    def set_memory_context(self, context: str):
        """设置记忆上下文"""
        self.memory_context = context
        logger.info(f"[CloudEngine] 记忆上下文已更新")

    def get_agent_name(self) -> str:
        return self.agent_name

    def chat(self, messages):
        """
        调用云端 API，返回纯文本回答
        messages: 可以是字符串（用户输入）或消息列表
        """
        # 构建系统提示
        skills_info = self.skills_info
        skills_desc = "\n".join([f"  • {name}: {info['description']}" for name, info in skills_info.items()]) if skills_info else "暂无"

        system_prompt = f"""你是智能助手 **{self.agent_name}**。

【关于用户的信息】
{self.memory_context if self.memory_context else "暂无"}

【已安装的技能】
{skills_desc}

【你的核心能力】
1. 记忆管理 - 记住用户信息（姓名、偏好、重要事实），忘记用户信息
2. 技能管理 - 新增技能、删除技能、列出技能
3. 自由聊天 - 回答用户的问题

【重要规则】
1. 用自然、友好、热情的语气直接回答用户
2. 如果用户问"现在几点"，直接告诉当前时间
3. 如果用户说"截个图"，提醒用户需要"新增技能：截图"来添加
4. 如果用户说"打开XXX"，检查是否有对应技能，有则告诉用户使用，没有则引导创建
5. 如果用户说"你好"，热情回应
6. 直接输出自然语言，不要输出JSON格式

当前时间：{self._get_current_time()}"""

        # 构建消息列表
        if isinstance(messages, str):
            full_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": messages}
            ]
        elif isinstance(messages, list):
            full_messages = [
                {"role": "system", "content": system_prompt}
            ]
            full_messages.extend(messages)
        else:
            return "抱歉，我不理解你的请求。"

        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": full_messages,
                    "temperature": 0.7,
                    "max_tokens": 2048
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"[Cloud] API 错误: {response.status_code}")
                return self._fallback_response("API调用失败")

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            if content and len(content) > 1:
                return content.strip()
            else:
                return self._fallback_response("API返回空内容")

        except requests.exceptions.Timeout:
            logger.error("[Cloud] API 超时")
            return "抱歉，请求超时了。请稍后再试。"
        except requests.exceptions.ConnectionError:
            logger.error("[Cloud] API 连接失败")
            return "抱歉，无法连接到云端服务。请检查网络连接。"
        except Exception as e:
            logger.error(f"[Cloud] 调用失败: {e}")
            return self._fallback_response(str(e))

    def _get_current_time(self) -> str:
        """获取当前时间"""
        import datetime
        now = datetime.datetime.now()
        return now.strftime("%Y年%m月%d日 %H:%M:%S")

    def _fallback_response(self, error: str) -> str:
        """降级响应"""
        return f"抱歉，我暂时无法处理这个请求。你可以试试：\n- 告诉我你的名字：'我叫小明'\n- 让我记住什么：'记住我喜欢吃西瓜'\n- 查看我的技能：'列出技能'\n- 创建技能：'新增技能：打开浏览器'"