"""
技能学习器 - 从对话中学习，主动推荐新技能

两条路径：
A. LLM 路径（优先）：分析最近对话 → 结合能力清单判断是否存在
   "反复出现但没技能"的需求 → 返回技能建议（名称/描述/参数/理由）
B. 关键词路径（兜底）：内置重复模式检测（计算/搜索/打开…），
   同一需求出现 >= skill_threshold 次才建议

配合 skill_factory 使用：建议 → 生成 → 自动创建 → 小虾米越用越强。
"""

import json
import re
from typing import List, Dict, Optional

from utils.logger import logger

try:
    from llm.cloud_engine import CloudEngine
except Exception:  # pragma: no cover
    CloudEngine = None


class SkillLearner:
    def __init__(self):
        self.history_window = 20   # 分析最近20轮对话
        self.skill_threshold = 3   # 关键词路径：同一需求出现3次以上才建议

    # ==================== LLM 能力感知路径 ====================

    def suggest_skill(self, history: List[Dict], capabilities: Optional[Dict] = None) -> Optional[Dict]:
        """
        分析对话历史，发现可以自动化的重复需求（能力感知）。
        返回 {"skill_name", "description", "params", "reason"} 或 None
        """
        if not history or len(history) < 4:
            return None

        # 优先 LLM 路径
        llm_result = self._suggest_via_llm(history, capabilities)
        if llm_result:
            return llm_result

        # 兜底：关键词路径
        return self.analyze_conversation(history)

    def _suggest_via_llm(self, history, capabilities) -> Optional[Dict]:
        if CloudEngine is None:
            return None
        from config import settings
        if not settings.api_key or settings.api_key == "sk-xxx":
            return None

        recent = history[-self.history_window:]
        context = "\n".join([
            f"{'用户' if msg.get('role') == 'user' else '助手'}: {msg.get('content', '')[:100]}"
            for msg in recent
        ])
        caps_json = json.dumps(capabilities or {}, ensure_ascii=False)
        prompt = f"""
分析以下对话，判断用户是否反复提出类似需求，并且这些需求可以用一个技能解决。

【环境能力清单】
{caps_json}

【对话历史】
{context}

判断标准：
1. 同一类需求是否出现至少2次？
2. 该需求能否用清单内的能力实现（舵机/屏幕/麦克风/文件/网络…）？
3. 该需求是否已有技能可以覆盖？

输出 JSON（不要输出其他内容）：
{{"should_create": true/false, "skill_name": "英文小写下划线", "description": "一句话功能描述", "params": {{"参数名": "说明"}}, "reason": "为什么创建"}}
"""
        try:
            cloud = CloudEngine()
            result = cloud.chat(prompt)
            text = ""
            if isinstance(result, dict):
                text = result.get("answer", "")
            elif isinstance(result, str):
                text = result
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group(0))
            if data.get("should_create") and data.get("skill_name"):
                return {
                    "skill_name": data["skill_name"],
                    "description": data.get("description", ""),
                    "params": data.get("params", {}),
                    "reason": data.get("reason", "LLM 分析发现重复需求"),
                }
        except Exception as e:
            logger.warning(f"[SkillLearner] LLM 分析失败: {e}")
        return None

    # ==================== 关键词兜底路径 ====================

    def analyze_conversation(self, history: List[Dict]) -> Optional[Dict]:
        """关键词模式检测（离线兜底）"""
        if len(history) < 4:
            return None

        recent = history[-self.history_window:]
        user_questions = [
            msg.get("content", "")
            for msg in recent
            if msg.get("role") == "user"
        ]
        if len(user_questions) < 2:
            return None

        patterns = self._detect_patterns(user_questions)
        if not patterns:
            return None

        best_pattern = max(patterns, key=lambda x: x.get("count", 0))
        if best_pattern.get("count", 0) < self.skill_threshold:
            return None

        return {
            "skill_name": self._generate_skill_name(best_pattern["keywords"]),
            "description": best_pattern["description"],
            "params": best_pattern.get("params", {}),
            "reason": f"用户多次提到相关需求 (共{best_pattern['count']}次)"
        }

    def _detect_patterns(self, questions: List[str]) -> List[Dict]:
        patterns = []
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
            },
            "跳舞|舞": {
                "description": "跳舞（动作序列）",
                "keywords": ["跳舞", "舞"]
            },
            "摇尾巴|尾巴": {
                "description": "摇尾巴",
                "keywords": ["摇尾巴", "尾巴"]
            },
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
        params = {}
        numbers = re.findall(r'\d+', " ".join(questions))
        if numbers and len(numbers) > 1:
            params["value"] = "数字"
        if any("文件" in q or "路径" in q for q in questions):
            params["file_path"] = "文件路径"
        return params

    def _generate_skill_name(self, keywords: List[str]) -> str:
        name_parts = [kw for kw in keywords if kw and len(kw) > 1]
        name = "_".join(name_parts[:2]) if name_parts else "auto_skill"
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)
        if name and name[0].isdigit():
            name = "skill_" + name
        return name or "auto_skill"
