"""
永久记忆模块 - 持久化存储用户偏好和重要信息
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
from utils.logger import logger


class PermanentMemory:
    """永久记忆管理类"""

    def __init__(self, storage_file: str = "memory/permanent_memory.json"):
        self.storage_file = storage_file
        self.memory_data = {
            "user_info": {},
            "preferences": {},
            "important_facts": [],
            "custom_memories": [],
            "skill_stats": {},
            "conversation_summary": "",
            "last_updated": None,
            "created_at": None
        }
        self._load()

    def _load(self):
        """从文件加载永久记忆"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self.memory_data.update(loaded_data)
                    logger.info("[PermanentMemory] 永久记忆加载成功")
            else:
                os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
                self._save()
                logger.info("[PermanentMemory] 创建新的永久记忆文件")
        except Exception as e:
            logger.error(f"[PermanentMemory] 加载永久记忆失败: {e}")

    def _save(self):
        """保存永久记忆到文件"""
        try:
            self.memory_data["last_updated"] = datetime.now().isoformat()
            if not self.memory_data.get("created_at"):
                self.memory_data["created_at"] = datetime.now().isoformat()

            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.memory_data, f, ensure_ascii=False, indent=2)
            logger.info("[PermanentMemory] 永久记忆保存成功")
        except Exception as e:
            logger.error(f"[PermanentMemory] 保存永久记忆失败: {e}")

    # ==================== 用户信息管理 ====================

    def set_user_info(self, key: str, value: Any) -> bool:
        """设置用户信息"""
        try:
            self.memory_data["user_info"][key] = {
                "value": value,
                "updated_at": datetime.now().isoformat()
            }
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 设置用户信息失败: {e}")
            return False

    def get_user_info(self, key: str) -> Optional[Any]:
        """获取用户信息"""
        info = self.memory_data["user_info"].get(key)
        if info:
            return info.get("value")
        return None

    def get_all_user_info(self) -> Dict:
        """获取所有用户信息"""
        return {k: v.get("value") for k, v in self.memory_data["user_info"].items()}

    def set_user_name(self, name: str) -> bool:
        """设置用户姓名"""
        return self.set_user_info("name", name)

    def get_user_name(self) -> Optional[str]:
        """获取用户姓名"""
        return self.get_user_info("name")

    # ==================== 偏好管理 ====================

    def set_preference(self, key: str, value: Any) -> bool:
        """设置用户偏好"""
        try:
            self.memory_data["preferences"][key] = {
                "value": value,
                "updated_at": datetime.now().isoformat()
            }
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 设置偏好失败: {e}")
            return False

    def get_preference(self, key: str) -> Optional[Any]:
        """获取用户偏好"""
        pref = self.memory_data["preferences"].get(key)
        if pref:
            return pref.get("value")
        return None

    def get_all_preferences(self) -> Dict:
        """获取所有偏好"""
        return {k: v.get("value") for k, v in self.memory_data["preferences"].items()}

    # ==================== 重要事实管理 ====================

    def add_fact(self, fact: str, category: str = "general") -> bool:
        """添加重要事实"""
        try:
            self.memory_data["important_facts"].append({
                "fact": fact,
                "category": category,
                "added_at": datetime.now().isoformat()
            })
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 添加事实失败: {e}")
            return False

    def get_facts(self, category: str = None) -> List[str]:
        """获取重要事实"""
        facts = self.memory_data["important_facts"]
        if category:
            return [f["fact"] for f in facts if f.get("category") == category]
        return [f["fact"] for f in facts]

    def get_all_facts_with_metadata(self) -> List[Dict]:
        """获取所有事实（含元数据）"""
        return self.memory_data["important_facts"]

    def delete_fact(self, index: int) -> bool:
        """删除指定事实"""
        try:
            if 0 <= index < len(self.memory_data["important_facts"]):
                del self.memory_data["important_facts"][index]
                self._save()
                return True
            return False
        except Exception as e:
            logger.error(f"[PermanentMemory] 删除事实失败: {e}")
            return False

    def clear_facts(self) -> bool:
        """清空所有事实"""
        try:
            self.memory_data["important_facts"] = []
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 清空事实失败: {e}")
            return False

    # ==================== 自定义记忆管理 ====================

    def add_custom_memory(self, content: str, tags: List[str] = None) -> bool:
        """添加自定义记忆"""
        try:
            self.memory_data["custom_memories"].append({
                "content": content,
                "tags": tags or [],
                "added_at": datetime.now().isoformat()
            })
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 添加自定义记忆失败: {e}")
            return False

    def get_custom_memories(self, tag: str = None) -> List[str]:
        """获取自定义记忆"""
        memories = self.memory_data["custom_memories"]
        if tag:
            return [m["content"] for m in memories if tag in m.get("tags", [])]
        return [m["content"] for m in memories]

    def get_all_custom_memories_with_metadata(self) -> List[Dict]:
        """获取所有自定义记忆（含元数据）"""
        return self.memory_data["custom_memories"]

    def delete_custom_memory(self, index: int) -> bool:
        """删除指定自定义记忆"""
        try:
            if 0 <= index < len(self.memory_data["custom_memories"]):
                del self.memory_data["custom_memories"][index]
                self._save()
                return True
            return False
        except Exception as e:
            logger.error(f"[PermanentMemory] 删除自定义记忆失败: {e}")
            return False

    # ==================== 技能档案（自优化经验库） ====================

    def record_skill_result(self, skill_name: str, success: bool, error: str = "") -> bool:
        """记录一次技能执行结果，维护成功率与连续失败次数"""
        try:
            stats = self.memory_data.setdefault("skill_stats", {})
            entry = stats.setdefault(skill_name, {
                "count": 0, "success": 0, "failures": 0,
                "consecutive_failures": 0, "last_error": "",
                "last_run": None, "last_success": None
            })
            entry["count"] += 1
            entry["last_run"] = datetime.now().isoformat()
            if success:
                entry["success"] += 1
                entry["consecutive_failures"] = 0
                entry["last_error"] = ""
                entry["last_success"] = entry["last_run"]
            else:
                entry["failures"] += 1
                entry["consecutive_failures"] += 1
                entry["last_error"] = (error or "")[:200]
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 记录技能结果失败: {e}")
            return False

    def get_skill_stats(self, skill_name: str) -> dict:
        """获取单个技能的执行统计"""
        return self.memory_data.get("skill_stats", {}).get(skill_name, {})

    def get_all_skill_stats(self) -> Dict:
        """获取所有技能统计"""
        return self.memory_data.get("skill_stats", {})

    def reset_skill_stats(self, skill_name: str = None) -> bool:
        """重置技能统计（指定技能或全部）"""
        try:
            if skill_name is None:
                self.memory_data["skill_stats"] = {}
            else:
                self.memory_data.setdefault("skill_stats", {}).pop(skill_name, None)
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 重置技能统计失败: {e}")
            return False

    # ==================== 对话摘要 ====================

    def set_conversation_summary(self, summary: str) -> bool:
        """设置对话摘要"""
        try:
            self.memory_data["conversation_summary"] = summary
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 设置对话摘要失败: {e}")
            return False

    def get_conversation_summary(self) -> str:
        """获取对话摘要"""
        return self.memory_data.get("conversation_summary", "")

    # ==================== 完整记忆查询 ====================

    def get_all_memories(self) -> Dict:
        """获取所有永久记忆"""
        return {
            "user_info": self.get_all_user_info(),
            "preferences": self.get_all_preferences(),
            "important_facts": self.get_facts(),
            "custom_memories": self.get_custom_memories(),
            "skill_stats": self.get_all_skill_stats(),
            "conversation_summary": self.get_conversation_summary(),
            "last_updated": self.memory_data.get("last_updated"),
            "created_at": self.memory_data.get("created_at")
        }

    def get_context_prompt(self) -> str:
        """生成用于系统提示的上下文字符串"""
        parts = []

        user_info = self.get_all_user_info()
        if user_info:
            info_str = "，".join([f"{k}是{v}" for k, v in user_info.items() if v])
            if info_str:
                parts.append(f"用户信息：{info_str}")

        preferences = self.get_all_preferences()
        if preferences:
            pref_str = "，".join([f"喜欢{k}是{v}" for k, v in preferences.items() if v])
            if pref_str:
                parts.append(f"用户偏好：{pref_str}")

        facts = self.get_facts()
        if facts:
            parts.append(f"重要事实：{'; '.join(facts)}")

        summary = self.get_conversation_summary()
        if summary:
            parts.append(f"对话摘要：{summary}")

        return "\n".join(parts) if parts else ""

    def clear_all(self) -> bool:
        """清空所有永久记忆"""
        try:
            self.memory_data = {
                "user_info": {},
                "preferences": {},
                "important_facts": [],
                "custom_memories": [],
                "skill_stats": {},
                "conversation_summary": "",
                "last_updated": datetime.now().isoformat(),
                "created_at": self.memory_data.get("created_at", datetime.now().isoformat())
            }
            self._save()
            return True
        except Exception as e:
            logger.error(f"[PermanentMemory] 清空所有记忆失败: {e}")
            return False