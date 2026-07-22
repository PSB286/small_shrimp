"""
技能学习器 - 从对话中学习，主动推荐新技能
"""

import json
from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
from core.skill_creator import SkillCreator
from utils.logger import logger


class SkillLearner:
    """
    从用户对话中学习，发现需要自动化的重复任务
    """
    
    def __init__(self):
        self.creator = SkillCreator()
        self.history_window = 20  # 分析最近20轮对话
        self.skill_threshold = 3   # 同一需求出现3次以上建议创建技能
    
    def analyze_conversation(self, history: List[Dict]) -> Optional[Dict]:
        """
        分析对话历史，发现可以自动化的模式
        """
        if len(history) < 4:
            return None
        
        recent = history[-self.history_window:]
        
        # 提取用户问题
        user_questions = [
            msg.get("content", "") 
            for msg in recent 
            if msg.get("role") == "user"
        ]
        
        if len(user_questions) < 2:
            return None
        
        # 检测重复模式
        patterns = self._detect_patterns(user_questions)
        
        if not patterns:
            return None
        
        # 选择最可能的模式
        best_pattern = max(patterns, key=lambda x: x.get("count", 0))
        
        if best_pattern.get("count", 0) < self.skill_threshold:
            return None
        
        # 生成技能建议
        return {
            "skill_name": self._generate_skill_name(best_pattern["keywords"]),
            "description": best_pattern["description"],
            "params": best_pattern.get("params", {}),
            "reason": f"用户多次提到相关需求 (共{best_pattern['count']}次)"
        }
    
    def _detect_patterns(self, questions: List[str]) -> List[Dict]:
        """检测对话模式"""
        patterns = []
        
        # 关键词模式
        keyword_patterns = {
            "time|日期|星期|几点": {
                "description": "获取当前时间或日期",
                "keywords": ["时间", "日期", "星期", "几点"]
            },
            "计算|加减乘除|等于": {
                "description": "数学计算",
                "keywords": ["计算", "加", "减", "乘", "除", "等于"]
            },
            "截图|屏幕|截屏": {
                "description": "屏幕截图",
                "keywords": ["截图", "截屏", "屏幕截图"]
            },
            "文件|保存|读取|写入": {
                "description": "文件操作",
                "keywords": ["文件", "保存", "读取", "写入"]
            },
            "搜索|查找|查一下": {
                "description": "搜索信息",
                "keywords": ["搜索", "查找", "查"]
            },
            "打开|启动|运行": {
                "description": "打开应用程序",
                "keywords": ["打开", "启动", "运行"]
            }
        }
        
        for pattern, info in keyword_patterns.items():
            count = 0
            matched_keywords = []
            for q in questions:
                for kw in info["keywords"]:
                    if kw in q:
                        count += 1
                        matched_keywords.append(kw)
                        break
            
            if count >= self.skill_threshold:
                patterns.append({
                    "pattern": pattern,
                    "count": count,
                    "description": info["description"],
                    "keywords": matched_keywords[:3],
                    "params": self._infer_params(questions, info["keywords"])
                })
        
        return patterns
    
    def _infer_params(self, questions: List[str], keywords: List[str]) -> Dict:
        """从问题中推断参数"""
        params = {}
        
        # 检查是否有数值
        import re
        numbers = re.findall(r'\d+', " ".join(questions))
        if numbers and len(numbers) > 1:
            params["value"] = "数字"
        
        # 检查是否有文件路径
        if any("文件" in q or "路径" in q for q in questions):
            params["file_path"] = "文件路径"
        
        return params
    
    def _generate_skill_name(self, keywords: List[str]) -> str:
        """生成技能名称"""
        # 使用关键词组合
        name_parts = [kw for kw in keywords if kw and len(kw) > 1]
        name = "_".join(name_parts[:2]) if name_parts else "auto_skill"
        
        # 确保只包含字母数字和下划线
        import re
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)
        
        # 避免以数字开头
        if name and name[0].isdigit():
            name = "skill_" + name
            
        return name or "auto_skill"
    
    def suggest_skill(self, history: List[Dict]) -> Optional[Dict]:
        """向用户建议新技能"""
        result = self.analyze_conversation(history)
        if result:
            logger.info(f"[SkillLearner] 建议新技能: {result['skill_name']} - {result['description']}")
        return result