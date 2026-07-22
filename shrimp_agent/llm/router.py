"""
模型路由器 - 增强版，支持上下文传递
"""

import datetime
import re
from llm.local_engine import LocalEngine
from llm.cloud_engine import CloudEngine


class ModelRouter:
    def __init__(self):
        self.local = LocalEngine()
        self.cloud = CloudEngine()
        self.context = {}  # 上下文存储

    def route_local(self, user_input: str) -> str:
        """尝试本地处理"""
        # 1. 意图识别
        intent = self.local.classify(user_input)
        
        # 2. 执行（传递上下文）
        result = self.local.execute(intent, user_input, self.context)
        
        if result:
            # 如果是数学计算，保存结果到上下文
            if intent.get("type") == "math" and "计算结果" in result:
                try:
                    # 提取结果数字
                    numbers = re.findall(r'[\d.]+', result)
                    if numbers:
                        self.context["last_math_result"] = float(numbers[-1])
                except:
                    pass
            return result
        
        # 3. 特殊处理：如果用户说"再x3"，尝试从上下文恢复
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