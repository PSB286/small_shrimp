"""
本地引擎 - 增强版
支持：更灵活的数学表达式、基础对话、时间查询、修改技能意图识别
"""

import datetime
import re
import random


class LocalEngine:
    """本地处理引擎（无需联网）"""

    def __init__(self):
        # 招呼语库
        self.greetings = [
            "你好！我是小虾米，有什么能帮你的？",
            "嗨！很高兴见到你！",
            "你好呀！今天想让我帮你做什么呢？",
            "欢迎！小虾米随时为你服务。"
        ]
        self.farewells = [
            "再见！随时来找我聊天！",
            "拜拜！期待下次见面！",
            "好的，有需要再找我！"
        ]
        # 闲聊回复库
        self.small_talk = {
            "你好": "你好！我是小虾米，很高兴认识你！",
            "嗨": "嗨！今天心情怎么样？",
            "哈哈": "哈哈，你笑什么呀？",
            "谢谢": "不客气！能帮到你我很开心！",
            "你是谁": "我是小虾米，一个智能助手，可以帮助你完成各种任务！",
            "你会做什么": "我可以帮你计算、截图、打开应用、查询时间，还能根据你的需求自动生成新功能！"
        }

    def classify(self, text: str) -> dict:
        """
        识别意图
        返回: {"type": "time"|"math"|"greeting"|"chat"|"unknown"|"modify_skill"|"delete_skill"|"list_skills", "data": ...}
        """
        text_lower = text.lower().strip()

        # 1. 时间查询
        if any(kw in text_lower for kw in ["几点", "什么时间", "现在时间", "当前时间"]):
            return {"type": "time"}

        # 2. 数学计算（支持多种格式）
        math_result = self._parse_math(text)
        if math_result is not None:
            return {"type": "math", "data": math_result}

        # 3. 修改技能意图
        modify_keywords = ["修改技能", "改一下技能", "把技能改成", "技能改成", "改成只", "调整技能"]
        if any(kw in text_lower for kw in modify_keywords):
            return {"type": "modify_skill", "data": text}

        # 4. 删除技能意图
        delete_keywords = ["删除技能", "移除技能", "去掉技能"]
        if any(kw in text_lower for kw in delete_keywords):
            return {"type": "delete_skill", "data": text}

        # 5. 列出技能意图
        list_keywords = ["列出技能", "技能列表", "有什么技能", "查看技能"]
        if any(kw in text_lower for kw in list_keywords):
            return {"type": "list_skills", "data": text}

        # 6. 问候和告别
        if any(kw in text_lower for kw in ["你好", "嗨", "hi", "hello", "您好"]):
            return {"type": "greeting"}
        if any(kw in text_lower for kw in ["再见", "拜拜", "bye", "goodbye"]):
            return {"type": "farewell"}

        # 7. 闲聊
        for key in self.small_talk:
            if key in text_lower:
                return {"type": "chat", "data": key}

        # 8. 感谢
        if any(kw in text_lower for kw in ["谢谢", "感谢", "多谢"]):
            return {"type": "thank"}

        return {"type": "unknown"}

    def _parse_math(self, text: str):
        """
        解析数学表达式（支持多种格式）
        支持：3+5, 3*2, 3x2 (自动转换), 3X2, 再x3 (提取数字)
        """
        text_clean = text.replace(" ", "").replace("等于多少", "").replace("是多少", "")

        # 处理 "再x3" 格式 - 提取数字
        if "再x" in text_clean or "再×" in text_clean:
            # 直接使用全局 re（文件顶部已导入）
            match = re.search(r'再[x×](\d+)', text_clean)
            if match:
                # 从上下文获取上一次结果（由调用方处理）
                return {"need_context": True, "value": int(match.group(1))}

        # 替换中文符号
        text_clean = text_clean.replace("×", "*").replace("x", "*").replace("X", "*")
        text_clean = text_clean.replace("÷", "/").replace("除以", "/")
        text_clean = text_clean.replace("加", "+").replace("减", "-").replace("乘", "*")

        # 提取数字和运算符
        pattern = r'[\d.]+[\+\-\*/][\d.]+'
        match = re.search(pattern, text_clean)
        if match:
            try:
                expr = match.group()
                result = eval(expr)
                return {"expression": expr, "result": result}
            except:
                pass

        # 提取单个数字（用于"x3"场景，但需要上下文）
        numbers = re.findall(r'(\d+)', text_clean)
        if len(numbers) == 1 and not re.search(r'[\+\-\*/]', text_clean):
            return {"need_context": True, "value": int(numbers[0])}

        return None

    def execute(self, intent: dict, text: str, context: dict = None) -> str:
        """
        执行本地指令
        context: 可选上下文（如上一次计算结果）
        返回: 字符串结果，或 None（表示需要云端处理）
        """
        intent_type = intent.get("type")

        # 修改技能、删除技能、列出技能 → 返回 None，让上层处理
        if intent_type in ["modify_skill", "delete_skill", "list_skills"]:
            return None

        if intent_type == "time":
            now = datetime.datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            return f"现在时间是：{now}"

        if intent_type == "math":
            data = intent.get("data", {})

            # 需要上下文（如"再x3"）
            if data.get("need_context") and context:
                last_value = context.get("last_math_result")
                if last_value is not None:
                    value = data.get("value", 1)
                    result = last_value * value
                    return f"计算结果：{result}"
                return "请先告诉我一个数字，比如 '3+5'"

            # 普通计算
            if "result" in data:
                return f"计算结果：{data['result']}"

        if intent_type == "greeting":
            return random.choice(self.greetings)

        if intent_type == "farewell":
            return random.choice(self.farewells)

        if intent_type == "chat":
            key = intent.get("data")
            return self.small_talk.get(key, "嗯，我听着呢！继续说吧。")

        if intent_type == "thank":
            return "不客气！还有什么需要帮忙的吗？"

        return None

    def is_math_expression(self, text: str) -> bool:
        """检查是否为数学表达式"""
        return bool(re.search(r'[\d.]+[\+\-\*/xX×÷][\d.]+', text))

    def extract_number(self, text: str) -> int:
        """提取数字"""
        numbers = re.findall(r'(\d+)', text)
        return int(numbers[0]) if numbers else None

    def extract_skill_name(self, text: str) -> str:
        """从文本中提取技能名称"""
        # 匹配 "修改技能 X" 或 "删除技能 X" 或 "把 X 技能改成"
        patterns = [
            r'(?:修改技能|改一下技能|删除技能|移除技能|去掉技能)\s*[：:]\s*(\w+)',
            r'(?:修改技能|改一下技能|删除技能|移除技能|去掉技能)\s+(\w+)',
            r'把\s*(\w+)\s*(?:技能)?\s*(?:改成|改为)',
            r'技能\s*(\w+)\s*(?:改成|改为)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return None