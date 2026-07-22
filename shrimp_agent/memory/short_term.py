class ShortTermMemory:
    def __init__(self, max_length=20):
        self.max_length = max_length
        self.history = []

    def add(self, user_msg: str, assistant_msg: str):
        """添加对话轮次"""
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": assistant_msg})
        
        # 超过长度，滑动窗口
        if len(self.history) > self.max_length * 2:
            # 保留最近 20 条（10轮对话）
            self.history = self.history[-20:]

    def get_history(self):
        """获取当前历史"""
        return self.history.copy()

    def clear(self):
        """清空历史"""
        self.history = []

class ShortTermMemory:
    def __init__(self, max_length=20):
        self.max_length = max_length
        self.history = []

    def add(self, user_msg: str, assistant_msg: str):
        """添加对话轮次"""
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": assistant_msg})
        
        # 超过长度，滑动窗口
        if len(self.history) > self.max_length * 2:
            self.history = self.history[-20:]

    def add_system_message(self, message: str):
        """添加系统消息（不显示给用户，但保留在上下文中）"""
        self.history.append({"role": "system", "content": message})
        # 限制长度
        if len(self.history) > self.max_length * 2 + 2:
            # 保留系统消息和最近的对话
            system_msgs = [m for m in self.history if m.get("role") == "system"]
            other_msgs = [m for m in self.history if m.get("role") != "system"]
            self.history = system_msgs[-5:] + other_msgs[-20:]

    def get_history(self):
        """获取当前历史"""
        return self.history.copy()

    def clear(self):
        """清空历史"""
        self.history = []