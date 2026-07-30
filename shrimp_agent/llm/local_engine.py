"""
本地引擎 - 增强意图识别 + 昵称支持
"""

import re
import datetime
import math


class LocalEngine:
    def __init__(self):
        self.context = {}

    def classify(self, user_input: str) -> dict:
        """
        意图分类
        """
        user_input = user_input.strip()

        # 1. 昵称设置检测（最高优先级）
        name_patterns = [
            r'以后你就叫',
            r'叫我',
            r'改名',
            r'称呼我',
            r'你就叫',
            r'给你取名',
            r'取名叫',
        ]
        for pattern in name_patterns:
            if pattern in user_input:
                return {"type": "set_name", "confidence": 0.95}

        # 2. 技能管理类
        if re.search(r'(?:列出|显示|查看|有哪些)\s*技能', user_input):
            return {"type": "list_skills", "confidence": 0.9}

        if re.search(r'删除\s*技能\s*\w+', user_input) or re.search(r'删除\s*\w+', user_input):
            return {"type": "delete_skill", "confidence": 0.8}

        if re.search(r'修改\s*技能', user_input) or re.search(r'改(?:一下)?\s*\w+', user_input):
            return {"type": "modify_skill", "confidence": 0.8}

        # 3. 数学计算
        if re.search(r'[\d.]+[\s]*[+\-*/%][\s]*[\d.]+', user_input):
            return {"type": "math", "confidence": 0.95}

        # 4. 时间查询
        if any(kw in user_input for kw in ["现在几点", "几点了", "当前时间", "现在时间"]):
            return {"type": "time", "confidence": 0.95}

        # 5. 日期查询
        if any(kw in user_input for kw in ["今天几号", "今天星期", "什么日子"]):
            return {"type": "date", "confidence": 0.9}

        # 6. 问候
        if any(kw in user_input for kw in ["你好", "hi", "hello", "嗨", "在吗"]):
            return {"type": "greeting", "confidence": 0.8}

        # 7. 感谢
        if any(kw in user_input for kw in ["谢谢", "感谢", "多谢"]):
            return {"type": "thanks", "confidence": 0.8}

        # 8. 询问记忆
        if any(kw in user_input for kw in ["还记得", "记得吗", "你记得", "记忆"]):
            return {"type": "query_memory", "confidence": 0.7}

        # 默认
        return {"type": "unknown", "confidence": 0.3}

    def execute(self, intent: dict, user_input: str, context: dict) -> str:
        """
        执行本地意图
        """
        intent_type = intent.get("type")

        if intent_type == "set_name":
            return self._handle_set_name(user_input, context)

        if intent_type == "math":
            return self._handle_math(user_input, context)

        if intent_type == "time":
            return self._handle_time()

        if intent_type == "date":
            return self._handle_date()

        if intent_type == "greeting":
            agent_name = context.get("agent_name", "GGB小虾米")
            return f"你好！我是 **{agent_name}** ，有什么可以帮你的吗？😊"

        if intent_type == "thanks":
            return "不客气！很高兴能帮到你！😊"

        if intent_type == "query_memory":
            return None  # 交给云端处理

        return None

    def _handle_set_name(self, user_input: str, context: dict) -> str:
        """处理昵称设置"""
        patterns = [
            r'(?:以后|从现在开始|今后|从今天起)\s*你就叫\s*([^\s，,。.！!？?]+)',
            r'(?:以后|从现在开始|今后|从今天起)\s*叫我\s*([^\s，,。.！!？?]+)',
            r'你就叫\s*([^\s，,。.！!？?]+)',
            r'叫我\s*([^\s，,。.！!？?]+)',
            r'改名为?\s*([^\s，,。.！!？?]+)',
            r'改名成\s*([^\s，,。.！!？?]+)',
            r'称呼(?:我|你)\s*([^\s，,。.！!？?]+)',
            r'给你取名\s*([^\s，,。.！!？?]+)',
            r'取名叫\s*([^\s，,。.！!？?]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                new_name = match.group(1).strip()
                new_name = re.sub(r'[，,。.！!？?、；;：:]', '', new_name)

                if not new_name or len(new_name) > 20:
                    return None

                context["agent_name"] = new_name
                responses = [
                    f"好的！以后我就叫 **{new_name}** 啦！😊",
                    f"收到！从现在开始，请叫我 **{new_name}** ！✨",
                    f"没问题！我的新名字是 **{new_name}** ，请多指教！🌟",
                ]
                import random
                return random.choice(responses)

        return "请告诉我你想让我叫什么名字？例如：'以后你就叫小可爱'"

    def _handle_math(self, user_input: str, context: dict) -> str:
        """处理数学计算"""
        try:
            expression = re.sub(r'[×xX]', '*', user_input)
            expression = re.sub(r'[÷]', '/', expression)

            if not re.match(r'^[\d\s+\-*/%().]+$', expression):
                return None

            result = eval(expression)

            context["last_math_result"] = float(result) if isinstance(result, (int, float)) else None

            return f"计算结果：{result}"
        except:
            return None

    def _handle_time(self) -> str:
        """处理时间查询"""
        now = datetime.datetime.now()
        return f"当前时间：{now.strftime('%H:%M:%S')}"

    def _handle_date(self) -> str:
        """处理日期查询"""
        now = datetime.datetime.now()
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        return f"今天是 {now.strftime('%Y年%m月%d日')} 星期{weekdays[now.weekday()]}"

    def extract_skill_name(self, user_input: str) -> str:
        """提取技能名称"""
        patterns = [
            r'(?:删除|修改)\s*技能\s*(\w+)',
            r'(?:删除|修改)\s*(\w+)',
            r'技能\s*(\w+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                return match.group(1)
        return None

    def extract_number(self, user_input: str) -> float:
        """提取数字"""
        match = re.search(r'[\d.]+', user_input)
        if match:
            return float(match.group())
        return None