"""
记忆集成模块 - 只处理明确的记忆指令
"""

from memory.permanent_memory import PermanentMemory
from utils.logger import logger
import re


class MemoryIntegration:
    """记忆集成处理器"""

    def __init__(self):
        self.permanent = PermanentMemory()

    def process_user_input(self, user_input: str) -> dict:
        """
        只处理非常明确的记忆指令
        其他全部交给云端处理
        """
        result = {"memorized": False, "type": None, "key": None, "value": None}
        user_input_clean = user_input.strip()

        # 只匹配明确的"我叫XXX"（必须是完整的陈述句）
        name_match = re.match(r'^我叫\s*([^\s，,。.！!？?]{1,20})$', user_input_clean)
        if name_match:
            name = name_match.group(1).strip()
            if name and name not in ['谁', '什么', '哪']:
                self.permanent.set_user_name(name)
                return {
                    "memorized": True,
                    "type": "name",
                    "key": "name",
                    "value": name,
                    "message": f"好的，我记住你叫 **{name}** 了！😊"
                }

        # 匹配"我喜欢XXX"（必须是完整的陈述句）
        pref_match = re.match(r'^我喜欢\s*([^\s，,。.！!？?]{1,20})$', user_input_clean)
        if pref_match:
            pref = pref_match.group(1).strip()
            if pref and pref not in ['什么', '啥', '哪']:
                self.permanent.set_preference("general", pref)
                return {
                    "memorized": True,
                    "type": "preference",
                    "key": "general",
                    "value": pref,
                    "message": f"好的，我记住你喜欢 **{pref}** 了！✨"
                }

        # 匹配"记住XXX"（必须是完整的陈述句）
        fact_match = re.match(r'^记住\s*(.+?)(?:[。.！!？?]|$)', user_input_clean)
        if fact_match:
            fact = fact_match.group(1).strip()
            if fact and len(fact) > 2 and '吗' not in fact:
                self.permanent.add_fact(fact, "user_important")
                return {
                    "memorized": True,
                    "type": "fact",
                    "key": "important_fact",
                    "value": fact,
                    "message": f"好的，我会记住：**{fact}** 📝"
                }

        # 匹配"无需/不要/别/不用 + 规则"（用户偏好/习惯，真正入库，不再口头说说）
        rule_match = re.match(
            r'^(?:以后|今后|从现在开始|之后)?\s*(?:无需|不要|别|不用|别再|不要再)\s*(.+?)(?:[。.！!？?]|$)',
            user_input_clean
        )
        if rule_match:
            rule_text = rule_match.group(1).strip()
            if rule_text and len(rule_text) >= 3 and '吗' not in rule_text and '什么' not in rule_text:
                self.permanent.set_preference("rule_" + rule_text[:12], rule_text)
                return {
                    "memorized": True,
                    "type": "preference",
                    "key": "rule",
                    "value": rule_text,
                    "message": f"好的，我记住了：**{user_input_clean}** ✨"
                }

        return result

    def get_memory_context(self) -> str:
        """获取记忆上下文"""
        return self.permanent.get_context_prompt()

    def get_all_memories(self) -> dict:
        return self.permanent.get_all_memories()