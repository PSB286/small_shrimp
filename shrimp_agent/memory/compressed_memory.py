"""
压缩记忆 - 融合旧架构的历史压缩功能
对话历史超过阈值时自动压缩
"""

import json
from typing import List, Dict
from utils.logger import logger


class CompressedMemory:
    """带自动压缩的短期记忆"""
    
    def __init__(self, max_length: int = 20, compress_threshold: int = 30):
        self.max_length = max_length
        self.compress_threshold = compress_threshold
        self.history = []
        self.compressed_count = 0
    
    def add(self, user_msg: str, assistant_msg: str):
        """添加对话"""
        self.history.append({"role": "user", "content": user_msg})
        self.history.append({"role": "assistant", "content": assistant_msg})
        
        # 超过阈值，触发压缩
        if len(self.history) > self.compress_threshold:
            self._compress()
    
    def _compress(self):
        """
        压缩历史（从旧架构迁移）
        保留最近的对话，压缩较早的部分
        """
        if len(self.history) <= self.max_length:
            return
        
        # 保留最近 max_length 条
        keep_count = self.max_length
        keep = self.history[-keep_count:]
        
        # 生成压缩摘要
        summary = self._generate_summary(self.history[:-keep_count])
        
        # 重建历史：摘要 + 最近对话
        self.history = [
            {"role": "system", "content": f"【历史摘要】{summary}"}
        ] + keep
        
        self.compressed_count += 1
        logger.info(f"[Memory] 已压缩历史，当前 {len(self.history)} 条")
    
    def _generate_summary(self, old_history: List[Dict]) -> str:
        """生成历史摘要（简化版，可集成 AI）"""
        if not old_history:
            return ""
        
        # 提取用户消息
        user_msgs = [h["content"][:50] for h in old_history if h.get("role") == "user"]
        if not user_msgs:
            return ""
        
        # 简单摘要
        summary = f"用户此前讨论了 {len(user_msgs)} 个话题，包括：{', '.join(user_msgs[:3])}"
        if len(user_msgs) > 3:
            summary += f" 等 {len(user_msgs)} 条消息"
        
        return summary
    
    def get_history(self) -> List[Dict]:
        """获取历史"""
        return self.history.copy()
    
    def clear(self):
        """清空历史"""
        self.history = []
        self.compressed_count = 0
    
    def add_system_message(self, message: str):
        """添加系统消息"""
        self.history.append({"role": "system", "content": message})
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total": len(self.history),
            "compressed": self.compressed_count,
            "max_length": self.max_length
        }