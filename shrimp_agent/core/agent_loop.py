"""
GGB小虾米 核心 Agent
核心职责：环境感知 + 记忆管理 + 技能管理（生成/执行/自优化）+ 聊天分发
"""

from core.skill_manager import SkillManager
from core.skill_matcher import SkillMatcher
from core.skill_factory import generate_skill, bootstrap_skills, load_capabilities, sanitize_filename
from core.self_optimizer import SelfOptimizer
from memory.compressed_memory import CompressedMemory
from core.memory_integration import MemoryIntegration
from utils.logger import logger
from llm.cloud_engine import CloudEngine
import os
import re
import datetime


class AgentLoop:
    def __init__(self):
        self.skills = SkillManager()
        self.matcher = SkillMatcher()
        self.memory = CompressedMemory()
        self.memory_integration = MemoryIntegration()
        self.permanent_memory = self.memory_integration.permanent
        self.cloud = CloudEngine()
        self.agent_name = "GGB小虾米"

        # 环境自适应：启动时按能力清单生成本环境的基础技能
        self.capabilities = load_capabilities()
        if os.getenv("AUTO_BOOTSTRAP", "1") == "1":
            created = bootstrap_skills(self.skills, self.capabilities)
            if created:
                logger.info(f"[Agent] 引导创建基础技能: {created}")

        # 自优化器（技能失败自动修复）
        self.optimizer = SelfOptimizer(self.skills, self.capabilities)

        # 最近用过的技能（对话连续性："追加xxx" → 追加到刚用过的技能）
        self.last_skill = None

        # 歧义确认状态：技能返回 __ASK__ 标记后挂起，等用户确认
        self.pending_ask = None

        saved_name = self.permanent_memory.get_user_name()
        if saved_name:
            self.agent_name = saved_name
            logger.info(f"[Agent] 从永久记忆恢复名称: {saved_name}")

        self.cloud.set_skills_info(self.skills.get_skills_info())
        self.cloud.set_agent_name(self.agent_name)
        self._update_memory_context()

    def _update_memory_context(self):
        memory_context = self.memory_integration.get_memory_context()
        if memory_context:
            self.cloud.set_memory_context(memory_context)

    def _sync_context_from_memory(self):
        saved_name = self.permanent_memory.get_user_name()
        self.agent_name = saved_name or "GGB小虾米"
        self.cloud.set_agent_name(self.agent_name)
        self._update_memory_context()

    def _set_agent_name(self, new_name: str):
        self.agent_name = new_name
        self.cloud.set_agent_name(new_name)
        self.permanent_memory.set_user_name(new_name)
        self._sync_context_from_memory()

    def run(self, user_input: str, history: list = None) -> str:
        if history is None:
            history = []

        logger.info(f"[Agent] 处理: {user_input[:50]}...")

        # 有挂起的歧义确认 → 优先处理用户的确认/取消
        if self.pending_ask:
            resolved = self._handle_pending_ask(user_input)
            if resolved is not None:
                return resolved
            # 不是确认 → 重新提问
            return self._ask_clarification(self.pending_ask["kind"], self.pending_ask["topic"])

        for predicate, handler in self._memory_handlers(user_input):
            if predicate(user_input):
                return handler()

        memory_extract = self.memory_integration.process_user_input(user_input)
        if memory_extract.get("memorized"):
            self._sync_context_from_memory()
            return memory_extract.get("message")

        name_result = self._handle_name_setting(user_input)
        if name_result:
            self._sync_context_from_memory()
            return name_result

        for predicate, handler in self._skill_handlers(user_input, history):
            if predicate(user_input):
                return handler()

        result = self._match_and_execute_skill(user_input, history)
        if result:
            return result

        return self._chat_with_cloud(user_input, history)

    def _memory_handlers(self, user_input: str):
        return [
            (self._is_forget_memory_query, lambda: self._handle_forget_memory(user_input)),
            (self._is_show_memory_query, lambda: self._show_memories()),
            (self._is_who_am_i_query, lambda: self._handle_who_am_i()),
        ]

    def _skill_handlers(self, user_input: str, history: list):
        return [
            (self._is_list_skills_query, lambda: self.skills.list_skills_formatted()),
            (self._is_delete_skill_query, lambda: self._handle_delete_skill(user_input)),
            (self._is_learn_skill_query, lambda: self._handle_learn_skill(user_input, history)),
            (self._is_create_skill_query, lambda: self._handle_create_skill(user_input, history)),
            (self._is_fix_skill_query, lambda: self._handle_fix_skill(user_input)),
            (self._is_enhance_skill_query, lambda: self._handle_enhance_skill(user_input)),
        ]

    # ================================================================
    # 学习技能（三要素：材料 / 学习内容 / 学习程度）
    # ================================================================

    def _is_learn_skill_query(self, user_input: str) -> bool:
        """识别学习技能意图：'学习技能...' 或 同时提到 材料+学习内容/程度"""
        if re.search(r'(?:学习|学会)\s*技能', user_input):
            return True
        return "材料" in user_input and any(k in user_input for k in ["学习内容", "要学习到", "学习程度", "学到什么程度"])

    def _handle_learn_skill(self, user_input: str, history: list) -> str:
        """学习技能：收集 材料/学习内容/学习程度 三要素 → 生成技能"""
        from core.skill_factory import parse_learning_fields, build_learning_description
        fields = parse_learning_fields(user_input)
        missing = [k for k in ("material", "content", "level") if not fields.get(k)]
        if missing:
            names = {"material": "材料", "content": "学习内容", "level": "要学习到的程度"}
            return (
                "📋 **学习技能需要你提供 3 个基本要素：**\n\n"
                "  • **材料**：要学习的对象（如：电脑记事本）\n"
                "  • **学习内容**：要学什么（如：使用记事本）\n"
                "  • **要学习到什么程度**：了解 / 基本使用 / 熟练 / 完全掌握\n\n"
                f"你还需要补充：**{'、'.join(names[m] for m in missing)}**\n\n"
                "可以一次性说：\n"
                "「学习技能：材料：电脑记事本，学习内容：使用记事本，要学习到：完全掌握」"
            )

        description = build_learning_description(
            fields["material"], fields["content"], fields["level"]
        )

        # 预检：已有技能是否已覆盖学习目标（避免白跑生成/合并）
        from core.skill_factory import find_similar_skills
        similar = find_similar_skills(description, self.skills.get_skills_info())
        if similar:
            existing_name = similar[0]
            existing_desc = self.skills.get_skills_info().get(existing_name, {}).get("description", "")
            covered = sum(1 for a in self._COVER_ACTIONS if a in existing_desc)
            if covered >= 3:
                return (
                    f"ℹ️ 这个技能你已经**学会了**：`{existing_name}` 已具备这些能力：\n"
                    f"  📦 {existing_name}：{existing_desc}\n\n"
                    f"可以直接说「执行{existing_name}」使用；\n"
                    f"想加新功能就说「增强技能 {existing_name}：要加的功能」。"
                )
            if self.skills.skill_exists(existing_name):
                # 已有技能但覆盖不足 → 直接增强它到目标程度，而不是新建
                return self._handle_enhance_skill(
                    f"增强技能 {existing_name}：按『{description}』的要求补全功能，学习程度要达到 {fields['level']}"
                )

        # 复用完整创建流程：生成 → 自打磨 → 相似整合 → 创建 → 能力推荐
        return self._handle_create_skill(f"新增技能：{description}", history)

    # ================================================================
    # 技能匹配与执行（核心）
    # ================================================================

    def _match_and_execute_skill(self, user_input: str, history: list) -> str:
        """按规则精准匹配技能，避免不必要的模糊调用。"""
        user_input_clean = user_input.strip()
        logger.info(f"[SkillMatch] Raw input: '{user_input_clean}'")

        if any(word in user_input_clean for word in ["吗", "？", "?", "能不能", "可以", "怎么", "如何", "是否", "什么"]):
            logger.info("[SkillMatch] Question detected, skipping skill execution.")
            return None

        # 否定句（无需/不要/别…）不是技能命令，跳过（交给记忆/聊天）
        if any(k in user_input_clean for k in ["无需", "不要", "别", "不用", "别再", "不要再", "不需要"]):
            return None

        # 引用上一条消息写入技能（"把刚才的诗写到记事本"）
        referenced = self._resolve_write_reference(user_input_clean, history or [])
        if referenced:
            return referenced

        action_match = re.match(r'^(?:打开|运行|启动|执行|使用)\s*(.+)$', user_input_clean)
        if action_match:
            target = action_match.group(1).strip()
            logger.info(f"[SkillMatch] Extracted target: '{target}'")
            for skill_name, info in self.skills.skills.items():
                if self._skill_target_matches(target, skill_name, info):
                    return self._execute_skill(skill_name)
            logger.info(f"[SkillMatch] No exact match for target '{target}'")

        # 自然语言匹配（本地确定性执行，不依赖云端）：
        # 输入同时含"技能目标词"和"动作词" → 直接执行，把完整请求传给技能解析
        for skill_name, info in self.skills.skills.items():
            if self._natural_language_skill_match(user_input_clean, skill_name, info):
                logger.info(f"[SkillMatch] NL match: {skill_name} <- '{user_input_clean}'")
                return self._execute_skill(skill_name, {"param": user_input_clean})

        # 对话连续性：输入以动作词开头且没提到任何目标词 →
        # 回退到最近用过的技能（如刚说完记事本，再说"追加45678"就是追加到记事本）
        last_fallback = re.match(
            r'^(?:帮我|请|麻烦)?\s*(?:追加|写入|写上|写一下|写|读取|读一下|读|清空|清除|记录|改成)\s*(\S+)',
            user_input_clean
        )
        if last_fallback and self.last_skill and self.last_skill in self.skills.skills:
            logger.info(f"[SkillMatch] 对话连续性回退: {self.last_skill} <- '{user_input_clean}'")
            return self._execute_skill(self.last_skill, {"param": user_input_clean})

        logger.info("[SkillMatch] No match, passing to cloud.")
        return None

    # 常见动作词（与技能目标词共同出现时判定为执行意图）
    _ACTION_VERBS = [
        "打开", "运行", "启动", "执行", "使用", "写入", "写上", "写一下", "写",
        "读取", "读一下", "读出来", "读", "看看", "查看", "清空", "清除", "清掉", "追加",
        "记录", "保存", "删除", "设置", "改成", "计算", "搜索", "查询",
        "显示", "播放", "发送", "生成", "创建", "关闭", "说出", "告诉",
        "打印", "查看", "路径",
    ]

    # 判断已有技能是否已覆盖学习目标时用到的动作词
    _COVER_ACTIONS = [
        "打开", "写入", "读取", "清空", "追加", "打印", "显示", "删除", "搜索", "计算",
    ]

    def _resolve_write_reference(self, user_input: str, history: list):
        """
        解析"把X写到Y"类引用：
        先理解对话（LLM 从最近回复中筛选出 X 对应的具体内容，如只取诗），
        再向用户确认筛选结果，确认后才执行技能。
        """
        m = re.search(
            r'(?:把|将)\s*(?:这个|刚才|上面|上一条|刚刚|那个)?\s*([^写\n]+?)\s*(?:写到|写进|写入|存到|放进|加进|记录到)\s*(\S+)',
            user_input
        )
        if not m:
            return None
        ref = m.group(1).strip().strip("的")
        if not ref or not any(k in ref for k in ["内容", "诗", "回答", "回复", "消息", "这段话", "文字", "东西", "前面", "刚才"]):
            return None
        # 收集最近的助手消息作为上下文（最多 2 条，诗可能在更早一条里）
        bot_msgs = []
        for msg in reversed(history or []):
            if msg.get("role") == "assistant":
                bot_msgs.insert(0, msg.get("content", "") or "")
                if len(bot_msgs) >= 2:
                    break
        if not bot_msgs:
            return None
        target = m.group(2).strip()
        from core.skill_factory import extract_target
        for name, info in self.skills.skills.items():
            t = extract_target(info.get("description", "") or "")
            if len(t) >= 2 and t in target:
                # 先理解对话：LLM 筛选出引用对应的具体内容（如只取诗词正文）
                extracted = self._extract_referenced_content(ref, bot_msgs)
                self.pending_ask = {
                    "kind": "write_reference",
                    "skill": name,
                    "content": extracted if (extracted and "无法确定" not in extracted) else "",
                    "ref": ref,
                    "context": "\n\n---\n\n".join(bot_msgs),
                }
                logger.info(f"[Agent] 引用写入确认: ref={ref} content_len={len(self.pending_ask['content'])}")
                return self._ask_write_reference(ref, self.pending_ask["content"])
        return None

    def _extract_referenced_content(self, ref: str, bot_msgs: list, extra: str = "") -> str:
        """LLM 理解对话，筛选出引用对应的具体内容（诗只取诗词正文）"""
        try:
            from llm.cloud_engine import CloudEngine
            cloud = CloudEngine()
            ctx = "\n\n---\n\n".join(bot_msgs)
            prompt = (
                f"用户想把【{ref}】写入记事本。下面是小虾米最近 {len(bot_msgs)} 条回复：\n\n{ctx}\n\n"
                f"请提取用户所指的【{ref}】的具体内容。\n"
                f"规则：只要与【{ref}】对应的那部分（比如诗只取诗词正文，"
                f"去掉前面的寒暄、后面的引导语和解释说明）。"
                + (("\n额外要求：%s" % extra) if extra else "")
                + "\n如果无法确定，只输出：无法确定。否则只输出提取到的内容，不要任何解释。"
            )
            result = cloud.chat(prompt)
            if isinstance(result, dict):
                result = result.get("answer", "")
            return str(result or "").strip()
        except Exception as e:
            logger.warning(f"[Agent] 引用内容提取失败: {e}")
            return ""

    def _ask_write_reference(self, ref: str, content: str) -> str:
        """向用户确认筛选结果（有歧义先提出，确认后再执行）"""
        if content:
            return (
                f"📋 我理解了，要把「{ref}」写入记事本。\n"
                f"我从刚才的回复中**筛选出这段内容**：\n\n{content}\n\n"
                f"回复 **确认** 写入；要调整直接说想法（如：只要诗、去掉标题）；取消说「取消」。"
            )
        return (
            f"📋 我没能确定「{ref}」具体指哪部分，请确认：\n\n"
            f"A. 写入上一条回复的全部内容\n"
            f"B. 只写入其中诗的部分\n"
            f"C. 其他（请说明你的要求）\n\n取消说「取消」。"
        )

    def _natural_language_skill_match(self, user_input: str, skill_name: str, info: dict) -> bool:
        """输入同时提到技能目标物和动作词 → 判定为执行意图"""
        from core.skill_factory import extract_target
        desc = info.get("description", "") or ""
        target = extract_target(desc)
        if len(target) < 2:
            return False
        # 输入必须包含技能的目标名词
        if target not in user_input:
            return False
        # 且包含一个动作词
        if not any(v in user_input for v in self._ACTION_VERBS):
            return False
        return True

    def _skill_target_matches(self, target: str, skill_name: str, info: dict) -> bool:
        # 去掉目标词开头的动作前缀（如"执行打开记事本" → "记事本"）
        target_clean = re.sub(r'^(打开|运行|启动|执行|使用)\s*', '', target).lower()
        normalized_target = target_clean or target.lower()

        # 技能名精确匹配或互相包含
        if normalized_target == skill_name.lower():
            return True
        if skill_name.lower() in normalized_target or normalized_target in skill_name.lower():
            return True
        # 描述包含目标词（如"记事本" → "打开 Windows 记事本程序"）
        desc = info.get("description", "")
        if normalized_target and normalized_target in desc.lower():
            return True
        return False

    # ================================================================
    # 记忆管理
    # ================================================================

    def _is_forget_memory_query(self, user_input: str) -> bool:
        user_input_clean = user_input.strip()
        has_action = any(p in user_input_clean for p in ["忘记", "删除", "清除", "忘掉", "抹去", "重置"])
        has_target = any(k in user_input_clean for k in ["记忆", "名字", "姓名", "偏好", "喜好", "事实", "所有", "全部"])
        return has_action and has_target

    def _handle_forget_memory(self, user_input: str) -> str:
        if "名字" in user_input or "姓名" in user_input:
            current_name = self.permanent_memory.get_user_name()
            if current_name:
                self.permanent_memory.set_user_info("name", None)
                self._sync_context_from_memory()
                return f"✅ 已忘记你的名字 **{current_name}**。"
            return "ℹ️ 我还没有记住你的名字呢。"

        if "偏好" in user_input or "喜好" in user_input:
            preferences = self.permanent_memory.get_all_preferences()
            if preferences:
                for key in list(preferences.keys()):
                    self.permanent_memory.set_preference(key, None)
                self._sync_context_from_memory()
                return "✅ 已忘记你的所有偏好。"
            return "ℹ️ 我还没有记住你的任何偏好呢。"

        if "事实" in user_input:
            facts = self.permanent_memory.get_facts()
            if facts:
                self.permanent_memory.clear_facts()
                self._sync_context_from_memory()
                return f"✅ 已忘记你的 {len(facts)} 条重要事实。"
            return "ℹ️ 我还没有记住任何重要事实呢。"

        if "确认" in user_input or "确定" in user_input:
            self.permanent_memory.clear_all()
            self._sync_context_from_memory()
            return "✅ 已成功删除所有永久记忆！"

        return (
            "⚠️ **确定要删除所有永久记忆吗？**\n\n"
            "这将删除：\n"
            "  • 你的名字\n"
            "  • 你的偏好\n"
            "  • 所有重要事实\n"
            "  • 技能学习档案\n\n"
            "你可以说：\n"
            "  • **忘记名字** - 只删除名字\n"
            "  • **忘记偏好** - 只删除偏好\n"
            "  • **忘记事实** - 只删除事实\n"
            "  • **删除所有记忆确认** - 删除全部"
        )

    def _is_show_memory_query(self, user_input: str) -> bool:
        patterns = ["查看记忆", "显示记忆", "我的记忆", "看看记忆", "记忆列表", "你记得什么", "记住什么"]
        return any(p in user_input for p in patterns)

    def _show_memories(self) -> str:
        all_memories = self.permanent_memory.get_all_memories()
        lines = ["📚 **我的永久记忆**\n"]
        has_memory = False

        user_info = all_memories.get("user_info", {})
        if user_info:
            has_memory = True
            lines.append("👤 **用户信息：**")
            for key, value in user_info.items():
                lines.append(f"  • {key}：{value}")
            lines.append("")

        preferences = all_memories.get("preferences", {})
        if preferences:
            has_memory = True
            lines.append("💡 **用户偏好：**")
            for key, value in preferences.items():
                lines.append(f"  • {key}：{value}")
            lines.append("")

        facts = all_memories.get("important_facts", [])
        if facts:
            has_memory = True
            lines.append("📝 **重要事实（共 {} 条）：**".format(len(facts)))
            for i, fact in enumerate(facts, 1):
                lines.append(f"  {i}. {fact}")
            lines.append("")

        skill_stats = all_memories.get("skill_stats", {})
        if skill_stats:
            has_memory = True
            lines.append("🎓 **技能学习档案：**")
            for name, stat in skill_stats.items():
                lines.append(f"  • {name}：成功 {stat.get('success', 0)}/{stat.get('count', 0)} 次"
                             + ("（连续失败 %d 次）" % stat["consecutive_failures"] if stat.get("consecutive_failures", 0) >= 2 else ""))
            lines.append("")

        if not has_memory:
            lines.append("目前还没有任何永久记忆。")
            lines.append("\n你可以告诉我：")
            lines.append("  • 你的名字：'我叫小明'")
            lines.append("  • 你的偏好：'我喜欢蓝色'")
            lines.append("  • 重要事情：'记住我每天7点起床'")

        return "\n".join(lines)

    def _is_who_am_i_query(self, user_input: str) -> bool:
        patterns = [r'^我是谁', r'^我叫什么', r'^你知道我叫什么', r'^你记得我叫什么', r'^你知道我是谁', r'^你记得我是谁']
        return any(re.search(p, user_input) for p in patterns)

    def _handle_who_am_i(self) -> str:
        user_name = self.permanent_memory.get_user_name()
        if user_name:
            return f"你是 **{user_name}** 呀！😊"
        return "我还不知道你是谁呢！可以告诉我你的名字吗？比如：'我叫小明' 😊"

    def _handle_name_setting(self, user_input: str) -> str:
        patterns = [
            r'(?:以后|从现在开始|今后)\s*你就叫\s*([^\s，,。.！!？?]+)',
            r'你就叫\s*([^\s，,。.！!？?]+)',
            r'叫我\s*([^\s，,。.！!？?]+)',
            r'改名为?\s*([^\s，,。.！!？?]+)',
            r'称呼我\s*([^\s，,。.！!？?]+)',
            r'给你取名\s*([^\s，,。.！!？?]+)',
        ]

        question_words = ['谁', '什么', '哪', '怎么', '为什么', '多少']

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                new_name = match.group(1).strip()
                new_name = re.sub(r'[，,。.！!？?、；;：:]', '', new_name)

                if new_name in question_words:
                    continue
                if not new_name or len(new_name) > 20:
                    return "昵称不能为空，且最多20个字哦！"
                if re.search(r'[<>"\'/\\]', new_name):
                    return "昵称包含非法字符。"

                self.agent_name = new_name
                self.cloud.set_agent_name(new_name)
                self.permanent_memory.set_user_name(new_name)
                self._sync_context_from_memory()

                return f"好的！以后我就叫 **{new_name}** 啦！😊"

        return None

    # ================================================================
    # 技能管理
    # ================================================================

    def _is_list_skills_query(self, user_input: str) -> bool:
        patterns = ["列出技能", "查看技能", "技能列表", "有哪些技能", "所有技能", "你的技能"]
        return any(p in user_input for p in patterns)

    def _is_delete_skill_query(self, user_input: str) -> bool:
        return re.search(r'删除\s*技能\s*(\w+)', user_input) is not None

    def _handle_delete_skill(self, user_input: str) -> str:
        match = re.search(r'删除\s*技能\s*(\w+)', user_input)
        if match:
            skill_name = match.group(1)
            self.matcher.remove_mapping(skill_name)
            self.permanent_memory.reset_skill_stats(skill_name)
            return self.skills.delete_skill(skill_name)
        return "请指定要删除的技能名称，例如：'删除技能 calculator'"

    def _is_create_skill_query(self, user_input: str) -> bool:
        patterns = [r'新增\s*技能', r'增加\s*技能', r'创建\s*技能', r'添加\s*技能', r'生成\s*技能', r'帮我.*技能']
        return any(re.search(p, user_input) for p in patterns)

    def _handle_create_skill(self, user_input: str, history: list) -> str:
        """按能力清单迭代生成新技能（先理解环境、预检可行性）"""
        description = user_input
        match = re.search(r'(?:新增|增加|创建|添加|生成)\s*技能[:：]?\s*(.+?)(?:[。.！!？?]|$)', user_input)
        if match:
            description = match.group(1).strip()

        # 1. 环境可行性预检：需求需要的能力，本环境有没有
        from core.skill_factory import precheck_feasibility
        pre = precheck_feasibility(description, self.capabilities)
        if not pre["feasible"]:
            return (
                f"❌ 这个技能在当前环境做不了：{pre['reason']}\n\n"
                f"📋 当前环境：{self._capabilities_summary()}\n"
                f"（如果是机器人的动作/硬件技能，需要先在 /environment 里声明对应硬件）"
            )

        # 2. 交给技能工厂生成（LLM 迭代 / 模板兜底）
        result = generate_skill(description, self.capabilities, history)
        if not result:
            return (
                "❌ 生成技能失败：AI 没能产出可用的代码。\n"
                f"📋 当前环境：{self._capabilities_summary()}\n\n"
                "可能原因：\n"
                "  • 需求描述太模糊，试试更具体，如「新增技能：用系统画图程序打开图片」\n"
                "  • 云端暂时不可用"
            )

        skill_code, skill_name, skill_desc, msgs = result
        skill_name = sanitize_filename(skill_name, "new_skill")

        # 3. 技能自打磨：静态反模式检查 + 沙箱冒烟测试，失败自动修复（让初版就能用）
        from core.skill_factory import polish_skill_code
        final_code, polish_rounds, polish_log = polish_skill_code(
            skill_code, skill_desc, self.capabilities)
        if final_code is None:
            logger.warning("[Agent] 技能自打磨失败: %s", polish_log)
            return (
                "❌ 技能未能通过自动打磨（初版有运行时问题，自动修复也未成功）。\n\n"
                f"📋 最后问题：{polish_log[-1] if polish_log else '未知'}\n\n"
                "建议换个更具体的描述再试，或说「新增技能：...」重新生成。"
            )
        if polish_rounds > 0:
            skill_code = final_code
            msgs = [f"自动打磨 {polish_rounds} 轮后通过"]

        # 4. 相似技能整合：已有类似技能时，合并进去而不是创建重复
        from core.skill_factory import find_similar_skills, merge_skills
        similar = find_similar_skills(description, self.skills.get_skills_info())
        if similar:
            existing_name = similar[0]
            existing_code = self.skills.get_skill_code(existing_name)
            if existing_code:
                merged = merge_skills(existing_name, existing_code, skill_desc, skill_code, self.capabilities)
                if merged:
                    merged_code, merged_desc = merged
                    backup = os.path.join(self.skills.skills_dir, ".backups")
                    os.makedirs(backup, exist_ok=True)
                    import shutil as _shutil
                    _shutil.copy2(
                        os.path.join(self.skills.skills_dir, f"{existing_name}.py"),
                        os.path.join(backup, f"{existing_name}_premerge.py"),
                    )
                    with open(os.path.join(self.skills.skills_dir, f"{existing_name}.py"),
                              "w", encoding="utf-8") as f:
                        f.write(merged_code)
                    self.skills.reload_skills()
                    self.cloud.set_skills_info(self.skills.get_skills_info())
                    self._update_memory_context()
                    self.permanent_memory.add_fact(
                        f"把「{skill_desc}」整合进了已有技能 {existing_name}（现为：{merged_desc}）", "skills"
                    )
                    suggestions = self._skill_upgrade_suggestions(existing_name, merged_code, merged_desc)
                    return (
                        f"🧩 **已整合相似技能！**\n\n"
                        f"新需求「{skill_desc}」与已有技能 `{existing_name}` 功能重叠，"
                        f"我没有创建重复技能，而是把它合并进了 `{existing_name}`：\n"
                        f"  📦 {existing_name}：{merged_desc}\n\n"
                        f"现在可以说「{description}」直接使用（旧版已备份到 .backups）。"
                        f"{suggestions}"
                    )
                # 合并失败 → 检查已有技能是否已覆盖学习目标：是则不创建重复
                logger.warning("[Agent] 技能 %s 合并失败，检查已有技能覆盖度", existing_name)
                existing_desc = self.skills.get_skills_info().get(existing_name, {}).get("description", "")
                covered = sum(1 for a in self._COVER_ACTIONS if a in existing_desc)
                if covered >= 3:
                    return (
                        f"ℹ️ 这个技能你已经**学会了**：`{existing_name}` 已具备这些能力：\n"
                        f"  📦 {existing_name}：{existing_desc}\n\n"
                        f"可以直接说「执行{existing_name}」使用；\n"
                        f"想加新功能就说「增强技能 {existing_name}：要加的功能」。"
                    )
                # 已有技能覆盖不足 → 退回创建独立技能
                logger.warning("[Agent] 已有技能覆盖不足，创建独立技能 %s", skill_name)

        skills_dir = self.skills.skills_dir
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir)

        filename = f"{skill_name}.py"
        filepath = os.path.join(skills_dir, filename)

        # 名字冲突：自动加后缀（_2, _3...），而不是放弃
        counter = 2
        while os.path.exists(filepath) and counter <= 10:
            filename = f"{skill_name}_{counter}.py"
            filepath = os.path.join(skills_dir, filename)
            counter += 1
        if os.path.exists(filepath):
            return f"⚠️ 同名技能 `{skill_name}` 已存在且无法自动改名，请换一个描述。"
        skill_name = filename[:-3]

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(skill_code)

            self.skills.reload_skills()
            self.cloud.set_skills_info(self.skills.get_skills_info())
            self._update_memory_context()

            keyword = description.replace("打开 ", "").replace("创建 ", "")
            self.matcher.add_mapping(keyword, skill_name, skill_desc)

            # 记入永久记忆：学会的新技能
            self.permanent_memory.add_fact(f"学会了技能 {skill_name}：{skill_desc}", "skills")

            suggestions = self._skill_upgrade_suggestions(skill_name, skill_code, skill_desc)

            return f"✅ **技能创建成功！** 🎉\n\n已创建：`{filename}`\n功能：{skill_desc}\n生成方式：{msgs[0] if msgs else ''}\n\n现在可以直接使用了！😊{suggestions}"
        except Exception as e:
            return f"❌ 创建技能失败：{str(e)}"

    def _skill_upgrade_suggestions(self, skill_name, skill_code, skill_desc):
        """技能生成后，主动推荐还需要补充的能力（避免用户一点点提）"""
        from core.skill_factory import suggest_skill_upgrades
        suggestions = suggest_skill_upgrades(skill_name, skill_desc, skill_code, self.capabilities)
        if not suggestions:
            return ""
        lines = ["", "", "💡 **技能还能更强大（能力推荐）：**"]
        for s in suggestions:
            title = s.get("title", "")
            detail = s.get("detail", "")
            lines.append(f"• {title}" + (f" —— {detail}" if detail else ""))
        lines.append(f"直接说「增强技能 {skill_name}：要加的能力」一次补齐，不用一点点提。")
        try:
            self.permanent_memory.add_custom_memory(
                f"{skill_name} 增强建议：{'；'.join(s.get('title', '') for s in suggestions)}",
                tags=[skill_name, "upgrade"],
            )
        except Exception:
            pass
        return "\n".join(lines)

    def _is_enhance_skill_query(self, user_input: str) -> bool:
        """识别增强/优化技能意图（多种说法）"""
        if "技能" not in user_input:
            return False
        return any(k in user_input for k in ["增强", "升级", "扩展", "完善", "优化", "改进", "改一下", "调整"])

    def _resolve_skill_name(self, user_input: str) -> str:
        """从用户话里解析技能名：显式名字 → 目标名词 → 最近用过的技能"""
        # 1. 显式名字（跟在 增强/优化 技能 后面 或 前面）
        m = re.search(r'(?:增强|升级|扩展|完善|优化|改进|修复)\s*技能\s*(\w+)', user_input)
        if m and self.skills.skill_exists(m.group(1)):
            return m.group(1)
        m = re.search(r'技能\s*(\w+)\s*(?:增强|升级|扩展|完善|优化|改进)', user_input)
        if m and self.skills.skill_exists(m.group(1)):
            return m.group(1)
        # 2. 目标名词解析（如"记事本技能优化一下" → open_notepad）
        from core.skill_factory import extract_target
        for name, info in self.skills.skills.items():
            target = extract_target(info.get("description", "") or "")
            if len(target) >= 2 and target in user_input:
                return name
        # 3. 最近用过的技能
        if self.last_skill and self.skills.skill_exists(self.last_skill):
            return self.last_skill
        return ""

    def _extract_enhance_instructions(self, user_input: str) -> str:
        """提取增强指令：去掉'技能...优化一下'这类前缀，剩下的是要加的功能"""
        # 去掉开头的不满/描述部分，取"优化/增强/改进..."之后的内容
        m = re.search(r'(?:优化|增强|升级|扩展|完善|改进)(?:一下|一下)?[，,：:\s]*([^。]*。?.*)', user_input, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 兜底：去前缀
        text = re.sub(r'^(?:你的|这个|那个|这些)?(?:技能)?\w*?(?:还是)?(?:有点|有些|存在)?(?:问题|毛病)[，,：:\s]*', '', user_input)
        return text.strip()

    def _handle_enhance_skill(self, user_input: str) -> str:
        """
        按指令一次性增强技能（保留原功能 + 新增能力）。
        '增强技能 X：追加写入同一个记事本'
        '这个记事本技能优化一下，打开后打印文件路径'
        """
        skill_name = self._resolve_skill_name(user_input)
        if not skill_name:
            return "请指定要增强的技能名称，例如：'增强技能 open_notepad：追加写入同一个记事本'"
        instructions = self._extract_enhance_instructions(user_input)

        if not self.skills.skill_exists(skill_name):
            return f"⚠️ 技能 {skill_name} 不存在"
        existing_code = self.skills.get_skill_code(skill_name)
        if not existing_code:
            return f"⚠️ 无法读取技能 {skill_name} 的源码"
        desc = self.skills.get_skills_info().get(skill_name, {}).get("description", "")

        from core.skill_factory import enhance_skill, suggest_skill_upgrades
        if not instructions:
            # 没给具体指令 → 用之前推荐的能力（存过 custom memory 就优先取）
            suggestions = []
            for mem in self.permanent_memory.get_all_custom_memories_with_metadata():
                if skill_name in mem.get("tags", []):
                    content = mem.get("content", "")
                    if "增强建议" in content:
                        suggestions = [{"title": t.strip()} for t in content.split("：")[1].split("；") if t.strip()]
                        break
            if not suggestions:
                suggestions = suggest_skill_upgrades(skill_name, desc, existing_code, self.capabilities)
            if not suggestions:
                return f"请具体说明要增强什么，例如：'增强技能 {skill_name}：追加写入同一个记事本'"
            instructions = "；".join(f"{s.get('title', '')}（{s.get('detail', '')}）" for s in suggestions[:3])

        result = enhance_skill(skill_name, existing_code, instructions, self.capabilities)
        if not result:
            return f"❌ 增强失败：AI 未能产出可用的增强代码，请换个说法再试。"
        new_code, new_desc = result

        # 备份 → 写入 → 热重载
        backup_dir = os.path.join(self.skills.skills_dir, ".backups")
        os.makedirs(backup_dir, exist_ok=True)
        import shutil as _shutil
        _shutil.copy2(
            os.path.join(self.skills.skills_dir, f"{skill_name}.py"),
            os.path.join(backup_dir, f"{skill_name}_preenhance.py"),
        )
        with open(os.path.join(self.skills.skills_dir, f"{skill_name}.py"), "w", encoding="utf-8") as f:
            f.write(new_code)
        self.skills.reload_skills()
        self.cloud.set_skills_info(self.skills.get_skills_info())
        self._update_memory_context()
        self.permanent_memory.add_fact(f"增强了技能 {skill_name}：{instructions}", "skills")

        return (
            f"✅ **技能已增强！**\n\n"
            f"📦 {skill_name}：{new_desc}\n"
            f"新增能力：{instructions}\n\n"
            f"旧版已备份到 .backups，随时可说「修复技能 {skill_name}」回退。"
        )

    def _is_fix_skill_query(self, user_input: str) -> bool:
        # 修复/修理 = 修 bug；优化/升级/增强 = 增强功能（走 _handle_enhance_skill）
        return re.search(r'(?:修复|修理)\s*技能\s*(\w+)', user_input) is not None

    def _handle_fix_skill(self, user_input: str) -> str:
        match = re.search(r'(?:修复|修理)\s*技能\s*(\w+)', user_input)
        if not match:
            return "请指定要修复的技能名称，例如：'修复技能 open_notepad'"
        skill_name = match.group(1)
        stats = self.permanent_memory.get_skill_stats(skill_name)
        last_error = stats.get("last_error", "") or "未知错误"
        result = self.optimizer.optimize_skill(skill_name, last_error, force=True)
        if result["success"]:
            self.permanent_memory.record_skill_result(skill_name, True)
            return f"✅ {result['message']}"
        return f"❌ {result['message']}"

    def _execute_skill(self, skill_name: str, params: dict = None) -> str:
        """执行技能并记录结果；失败时进入自优化流程"""
        self.last_skill = skill_name
        try:
            result = self.skills.execute(skill_name, params or {})
            # 技能返回歧义确认标记 __ASK__:kind|detail
            if isinstance(result, str):
                m = re.match(r'^__ASK__:(\w+)\|(.*)$', result.strip(), re.DOTALL)
                if m:
                    parts = m.group(2).split("|")
                    self.pending_ask = {
                        "kind": m.group(1),
                        "topic": parts[0].strip(),
                        "action": parts[1].strip() if len(parts) > 1 else "write",
                    }
                    logger.info("[Agent] 技能 %s 请求歧义确认: %s", skill_name, m.group(1))
                    return self._ask_clarification(m.group(1), self.pending_ask["topic"])
            if result and not result.startswith("[错误]"):
                self.permanent_memory.record_skill_result(skill_name, True)
                return result
            error = result or f"技能 {skill_name} 无输出"
            self.permanent_memory.record_skill_result(skill_name, False, error)
            return self._handle_skill_failure(skill_name, error)
        except Exception as e:
            self.permanent_memory.record_skill_result(skill_name, False, str(e))
            return self._handle_skill_failure(skill_name, str(e))

    def _ask_clarification(self, kind: str, topic: str) -> str:
        """针对歧义请求提问，让用户确认用哪一种"""
        if kind == "creative_poem":
            return (
                f"📋 **需要你确认一下**：你说要写「{topic}」，是指——\n\n"
                f"A. 把《{topic}》的内容（完整诗词/文章）写进记事本\n"
                f"B. 只写入文字「{topic}」\n\n"
                f"回复 A 或 B（或直接描述想要的效果），取消说「取消」。"
            )
        return f"📋 你的请求有歧义，请说明具体想要哪种效果（取消说「取消」）。"

    def _handle_pending_ask(self, user_input: str):
        """处理用户的歧义确认回复；不是确认返回 None（重新提问）"""
        if not self.pending_ask:
            return None
        kind = self.pending_ask.get("kind", "")
        topic = self.pending_ask.get("topic") or self.pending_ask.get("ref") or ""
        text = (user_input or "").strip()

        # 取消
        if any(k in text for k in ["取消", "算了", "不用了", "不了", "算了算了"]):
            self.pending_ask = None
            return "好的，已取消。😊"

        if kind == "creative_poem":
            action = self.pending_ask.get("action", "write")
            if re.fullmatch(r'[aA]', text) or any(k in text for k in ["诗的内容", "写诗", "作诗", "内容", "全诗", "完整"]):
                self.pending_ask = None
                content = self._generate_creative_content(topic)
                if not content or content.startswith("[创作失败]"):
                    return content or "❌ 创作失败，请稍后再试。"
                # 按原请求意图：写入（覆盖）或追加
                prefix = "__RAW_APPEND__:" if action == "append" else "__RAW__:"
                return self._execute_skill("open_notepad", {"param": prefix + content})
            if re.fullmatch(r'[bB]', text) or any(k in text for k in ["文字", "字面", "原样", "几个字"]):
                self.pending_ask = None
                prefix = "__RAW_APPEND__:" if action == "append" else "__RAW__:"
                return self._execute_skill("open_notepad", {"param": prefix + topic})

        if kind == "write_reference":
            skill = self.pending_ask.get("skill", "open_notepad")
            content = self.pending_ask.get("content", "")
            context = self.pending_ask.get("context", "")
            ref = self.pending_ask.get("ref", "")
            # 确认 → 用筛选出的内容写入（没筛选到则写全部）
            if any(k in text for k in ["确认", "对", "好", "可以", "没问题", "就这样", "写入", "写吧", "行"]):
                self.pending_ask = None
                return self._execute_skill(skill, {"param": "__RAW__:" + (content or context)})
            # A：写全部
            if re.fullmatch(r'[aA]', text) or "全部" in text:
                self.pending_ask = None
                return self._execute_skill(skill, {"param": "__RAW__:" + context})
            # B：只要诗的部分
            if re.fullmatch(r'[bB]', text) or "诗" in text:
                extracted = self._extract_referenced_content(ref, [context], extra="只要诗的内容，去掉其他文字")
                self.pending_ask = None
                if extracted and "无法确定" not in extracted:
                    return self._execute_skill(skill, {"param": "__RAW__:" + extracted})
                return "❌ 筛选诗的部分失败，请直接把要写的内容告诉我。"
            # 其他 → 当作调整要求重新筛选
            extracted = self._extract_referenced_content(ref, [context], extra=text)
            if extracted and "无法确定" not in extracted:
                self.pending_ask = None
                return self._execute_skill(skill, {"param": "__RAW__:" + extracted})
            self.pending_ask["content"] = ""
            return self._ask_write_reference(ref, "")

        return None

    def _generate_creative_content(self, topic: str) -> str:
        """调用 LLM 创作内容（如以某题为诗）"""
        try:
            from llm.cloud_engine import CloudEngine
            cloud = CloudEngine()
            result = cloud.chat(
                f"请创作一首以《{topic}》为题的诗词，直接输出完整的诗词内容，不要任何解释、不要标题以外的说明文字。"
            )
            if isinstance(result, dict):
                result = result.get("answer", "")
            content = str(result or "").strip()
            return content if content else "[创作失败] 没有生成内容"
        except Exception as e:
            logger.error(f"[Agent] 创作失败: {e}")
            return f"[创作失败] {str(e)}"

    def _handle_skill_failure(self, skill_name: str, error: str) -> str:
        """技能失败处理：T1 自动修复；T2 连续失败停用待确认"""
        tier = self.skills.get_skill_tier(skill_name)
        stats = self.permanent_memory.get_skill_stats(skill_name)
        consec = stats.get("consecutive_failures", 1)

        if tier == 0:
            return f"❌ 执行 **{skill_name}** 失败：{error}"

        if tier == 1:
            result = self.optimizer.optimize_skill(skill_name, error)
            if result["success"]:
                return f"⚠️ 执行失败：{error}\n\n🔧 已自动修复，可以再试一次！"
            return f"⚠️ 执行 **{skill_name}** 失败：{error}\n\n🔧 自动修复未成功：{result['message']}"

        # T2：学习生成的技能
        if consec >= 2:
            self.optimizer.disable_skill(skill_name)
            return (
                f"⚠️ 执行 **{skill_name}** 失败：{error}\n\n"
                f"🔧 已连续失败 {consec} 次，我暂时停用了它。\n"
                f"你可以说「修复技能 {skill_name}」让我重新修复，或「查看技能」确认状态。"
            )

        result = self.optimizer.optimize_skill(skill_name, error)
        if result["success"]:
            return f"⚠️ 执行失败：{error}\n\n🔧 已自动修复，可以再试一次！"
        return f"⚠️ 执行 **{skill_name}** 失败：{error}\n\n🔧 自动修复未成功：{result['message']}"

    def _to_filename(self, text: str) -> str:
        if not text:
            return "new_skill"
        name = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '_', text)
        if re.search(r'[\u4e00-\u9fff]', name):
            try:
                from pypinyin import pinyin, Style
                return ''.join([p[0] for p in pinyin(name, style=Style.NORMAL)]).lower()
            except:
                return name
        return name.lower()

    # ================================================================
    # 云端聊天
    # ================================================================

    def _chat_with_cloud(self, user_input: str, history: list) -> str:
        """使用云端 LLM 聊天"""
        try:
            memory_context = self.memory_integration.get_memory_context()

            skills_info = self.skills.get_skills_info()
            skills_desc = "\n".join([f"  • {name}: {info['description']}" for name, info in skills_info.items()]) if skills_info else "暂无"

            caps_desc = self._capabilities_summary()

            system_prompt = f"""你是智能助手 **{self.agent_name}**。

【关于用户的信息】
{memory_context if memory_context else "暂无"}

【本环境的硬件能力】
{caps_desc}

【已安装的技能】
{skills_desc}

【你的核心能力】
1. 记忆管理 - 记住用户信息（姓名、偏好、重要事实），忘记用户信息
2. 技能管理 - 新增技能、删除技能、修复技能、列出技能
3. 环境自适应 - 根据本环境硬件自动学习新技能（说"新增技能：XXX"）
4. 自由聊天 - 回答用户的问题

【重要规则】
1. 用自然、友好、热情的语气回答
2. 如果用户说"打开XXX"或"执行XXX"，直接执行对应技能
3. 如果用户想学新东西（如"我想让你学会跳舞"），引导说"新增技能：跳舞"
4. 如果用户说"你好"或"hi"，热情回应
5. 直接输出自然语言，不要输出JSON格式

【对话上下文（会话内短暂记忆，重要）】
消息列表里包含本轮之前的对话历史。用户经常会**延续或引用之前的内容**：
- 刚算完 "1+1=2" 紧接着说 "x3" / "再乘3" → 指 2×3=6（继续上一步运算）
- "它" / "这个" / "刚才的" / "那首诗" 等指代 → 指上一条相关消息
- 说"追加/再写/继续" → 延续上一个话题
请务必结合历史理解当前问题，不要孤立地回答。如果历史不足以确定，再询问用户。

【技能执行协议（重要）】
如果用户的需求【可以用已安装技能完成】，你的回复必须以一行指令开头，不要只口头描述：
__EXEC__:技能名
__EXEC__:技能名|用户完整请求
- 技能名必须是上面【已安装的技能】列表中的名字
- 参数必须是用户的【完整原话】，不要改写、不要只传名词；
  技能内部会自己识别动作（写入/读取/清空/打开等）并提取内容
- 指令行之外不要输出任何说明文字

当前时间：{datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"""

            # 提取最近一轮对话（用户+助手），显式放在消息最前面，强化短暂记忆
            recent_turns = []
            for msg in (history or [])[-4:]:
                role = "我" if msg.get("role") == "user" else "小虾米"
                recent_turns.append(f"{role}: {str(msg.get('content', ''))[:120]}")
            messages = []
            if recent_turns:
                messages.append({"role": "system", "content": "【最近对话回顾】\n" + "\n".join(recent_turns)})
            messages += [
                {"role": "system", "content": system_prompt},
                *history[-10:],
                {"role": "user", "content": user_input}
            ]

            result = self.cloud.chat(messages)

            answer = ""
            if isinstance(result, dict):
                answer = result.get("answer", "")
            elif isinstance(result, str):
                answer = result

            # 解析技能执行协议指令：__EXEC__:技能名|参数
            exec_result = self._handle_exec_directive(answer, user_input)
            if exec_result is not None:
                return exec_result

            if answer and len(answer) > 1:
                return answer

            return "抱歉，我没有理解你的意思。你可以试试：\n- 记住什么：'记住我喜欢吃西瓜'\n- 查看记忆：'查看记忆'\n- 创建技能：'新增技能：跳个舞'\n- 查看环境：'查看环境能力'"

        except Exception as e:
            logger.error(f"[Agent] 云端聊天失败: {e}")
            return f"抱歉，我暂时无法回答。你可以换个方式问我。😊"

    def _handle_exec_directive(self, reply, fallback_param=None):
        """
        处理云端返回的技能执行指令 __EXEC__:技能名|参数。
        参数为空时用用户原始请求兜底（技能内部解析动作）。
        找到就真正执行技能并返回结果；否则返回 None（正常聊天）。
        """
        if not reply:
            return None
        # 指令可出现在回复任意位置：__EXEC__:技能名|参数
        m = re.search(r'__EXEC__:(\w+)(?:\|([^\n]*))?', reply)
        if not m:
            return None
        skill_name = m.group(1)
        param = (m.group(2) or "").strip() or (fallback_param or "").strip()
        note = reply.replace(m.group(0), "").strip()

        if not self.skills.skill_exists(skill_name):
            return (note + "\n\n" if note else "") + f"⚠️ 技能 {skill_name} 不存在，无法执行。"

        result = self._execute_skill(skill_name, {"param": param} if param else {})
        if note:
            return f"{note}\n\n{result}"
        return result

    def _capabilities_summary(self) -> str:
        """把能力清单转成一句话描述"""
        caps = self.capabilities or {}
        parts = []
        servos = caps.get("actuators") or []
        if servos:
            parts.append("舵机x%d (%s)" % (len(servos), ", ".join(s.get("id", "?") for s in servos)))
        if caps.get("display"):
            parts.append("屏幕(可做表情)")
        if caps.get("audio_in"):
            parts.append("麦克风(可收音)")
        if caps.get("audio_out"):
            parts.append("喇叭(可说话)")
        if caps.get("network"):
            parts.append("可联网")
        return "、".join(parts) if parts else "无特殊硬件（纯聊天）"
