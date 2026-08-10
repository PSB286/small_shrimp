"""
技能匹配管理器 - 从配置文件加载匹配规则，支持动态重载
"""

import json
import os
import re
from utils.logger import logger


class SkillMatcher:
    def __init__(self, config_path: str = "config/skill_mappings.json"):
        self.config_path = config_path
        self.mappings = []
        self.auto_create = True
        self.patterns = {}
        self._load()
    
    def _load(self):
        """加载匹配配置"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"[SkillMatcher] 配置文件不存在: {self.config_path}")
                self._create_default_config()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.mappings = data.get("mappings", [])
            self.auto_create = data.get("auto_create", True)
            self.patterns = data.get("patterns", {})
            
            logger.info(f"[SkillMatcher] 加载了 {len(self.mappings)} 条匹配规则")
        except Exception as e:
            logger.error(f"[SkillMatcher] 加载配置失败: {e}")
            self.mappings = []
    
    def _create_default_config(self):
        """创建默认配置文件"""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        default_config = {
            "mappings": [
                {
                    "keywords": ["截个图", "截图", "屏幕截图", "截屏"],
                    "skill": "screenshot",
                    "description": "截取屏幕截图"
                },
                {
                    "keywords": ["打开计算器", "计算器"],
                    "skill": "open_calculator",
                    "description": "打开计算器"
                },
                {
                    "keywords": ["打开浏览器", "浏览器"],
                    "skill": "browser",
                    "description": "打开浏览器"
                }
            ],
            "auto_create": True,
            "patterns": {
                "open": "^(?:打开|运行|启动|执行|使用)\\s*(.+)$"
            }
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        logger.info(f"[SkillMatcher] 创建默认配置文件: {self.config_path}")
        self._load()
    
    def reload(self):
        """重新加载配置"""
        self._load()
        return True
    
    def match(self, user_input: str) -> dict:
        """
        匹配用户输入
        返回: {"matched": True, "skill": "screenshot", "keyword": "截个图"} 或 {"matched": False}
        """
        user_input_clean = user_input.strip()
        
        # 1. 关键词匹配
        for mapping in self.mappings:
            keywords = mapping.get("keywords", [])
            for keyword in keywords:
                if keyword in user_input_clean:
                    return {
                        "matched": True,
                        "skill": mapping.get("skill"),
                        "keyword": keyword,
                        "description": mapping.get("description", "")
                    }
        
        # 2. 正则模式匹配（如：打开XXX）
        open_pattern = self.patterns.get("open", "")
        if open_pattern:
            match = re.match(open_pattern, user_input_clean)
            if match:
                keyword = match.group(1)
                return {
                    "matched": True,
                    "skill": None,  # 技能不存在，需要查找或创建
                    "keyword": keyword,
                    "description": f"打开 {keyword}",
                    "need_create": True
                }
        
        return {"matched": False}
    
    def add_mapping(self, keyword: str, skill: str, description: str = ""):
        """动态添加匹配规则"""
        # 检查是否已存在
        for mapping in self.mappings:
            if keyword in mapping.get("keywords", []):
                logger.info(f"[SkillMatcher] 规则已存在: {keyword} -> {skill}")
                return False
        
        self.mappings.append({
            "keywords": [keyword],
            "skill": skill,
            "description": description or skill
        })
        self._save()
        logger.info(f"[SkillMatcher] 添加规则: {keyword} -> {skill}")
        return True
    
    def remove_mapping(self, keyword: str):
        """动态删除匹配规则"""
        for i, mapping in enumerate(self.mappings):
            if keyword in mapping.get("keywords", []):
                self.mappings.pop(i)
                self._save()
                logger.info(f"[SkillMatcher] 删除规则: {keyword}")
                return True
        return False
    
    def _save(self):
        """保存配置"""
        try:
            data = {
                "mappings": self.mappings,
                "auto_create": self.auto_create,
                "patterns": self.patterns
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"[SkillMatcher] 保存配置失败: {e}")
            return False
    
    def list_all(self):
        """列出所有匹配规则"""
        return self.mappings