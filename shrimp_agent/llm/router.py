"""
模型路由器 - 增强版，支持上下文传递和修改技能
"""

import datetime
import re
from llm.local_engine import LocalEngine
from llm.cloud_engine import CloudEngine


class ModelRouter:
    def __init__(self):
        self.local = LocalEngine()
        self.cloud = CloudEngine()
        self.context = {}
        self.skill_manager = None

    def set_skill_manager(self, skill_manager):
        """注入技能管理器"""
        self.skill_manager = skill_manager

    def route_local(self, user_input: str) -> str:
        """尝试本地处理"""
        intent = self.local.classify(user_input)

        if intent.get("type") in ["modify_skill", "delete_skill", "list_skills"]:
            return None

        result = self.local.execute(intent, user_input, self.context)

        if result:
            if intent.get("type") == "math" and "计算结果" in result:
                try:
                    numbers = re.findall(r'[\d.]+', result)
                    if numbers:
                        self.context["last_math_result"] = float(numbers[-1])
                except:
                    pass
            return result

        if "再x" in user_input or "再×" in user_input:
            last_val = self.context.get("last_math_result")
            if last_val is not None:
                try:
                    num = self.local.extract_number(user_input)
                    if num:
                        result = last_val * num
                        self.context["last_math_result"] = result
                        return f"计算结果：{result}"
                except:
                    pass
            return "请先进行一次数学计算，比如 '3+5'"
        
        return None

    def route_cloud(self, user_input: str, history: list):
        """云端推理"""
        return self.cloud.chat(user_input, history)