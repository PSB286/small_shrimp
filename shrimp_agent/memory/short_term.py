"""
短期记忆模块 - 存储对话历史
"""

from collections import deque


class ShortTermMemory:
    def __init__(self, max_length=20):
        self.messages = deque(maxlen=max_length)

    def add(self, user_msg: str, assistant_msg: str):
        """添加对话"""
        self.messages.append({
            "role": "user",
            "content": user_msg
        })
        self.messages.append({
            "role": "assistant",
            "content": assistant_msg
        })

    def get_history(self):
        """获取对话历史"""
        return list(self.messages)

    def clear(self):
        """清空记忆"""
        self.messages.clear()

    def get_last_n(self, n: int):
        """获取最近 n 条消息"""
        return list(self.messages)[-n:]