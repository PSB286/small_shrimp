"""
压缩记忆 - 增加系统消息支持
"""

from collections import deque
import json
from datetime import datetime


class CompressedMemory:
    def __init__(self, max_length=50):
        self.messages = deque(maxlen=max_length)
        self.system_messages = deque(maxlen=10)
        self.summary = None

    def add(self, user_msg: str, assistant_msg: str):
        """添加对话"""
        self.messages.append({
            "role": "user",
            "content": user_msg,
            "timestamp": datetime.now().isoformat()
        })
        self.messages.append({
            "role": "assistant",
            "content": assistant_msg,
            "timestamp": datetime.now().isoformat()
        })

    def add_system_message(self, content: str):
        """添加系统消息（如名称变更）"""
        self.system_messages.append({
            "role": "system",
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_history(self):
        """获取对话历史"""
        history = []
        # 先添加系统消息
        for msg in self.system_messages:
            history.append({
                "role": "system",
                "content": msg["content"]
            })
        # 再添加对话消息
        for msg in self.messages:
            history.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        return history

    def get_summary(self):
        """获取压缩摘要"""
        if self.summary:
            return self.summary

        if len(self.messages) == 0:
            return "暂无对话历史"

        # 简单摘要：取最近的几条消息
        recent = list(self.messages)[-6:]
        summary = "最近对话：\n"
        for msg in recent:
            role = "用户" if msg["role"] == "user" else "助手"
            summary += f"{role}: {msg['content'][:50]}...\n"
        return summary

    def clear(self):
        """清空记忆"""
        self.messages.clear()
        self.system_messages.clear()
        self.summary = None

    def get_system_messages(self):
        """获取系统消息"""
        return list(self.system_messages)