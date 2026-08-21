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
            (self._is_create_skill_query, lambda: self._handle_create_skill(user_input, history)),
            (self._is_fix_skill_query, lambda: self._handle_fix_skill(user_input)),
            (self._is_enhance_skill_query, lambda: self._handle_enhance_skill(user_input)),
        ]

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

        logger.info("[SkillMatch] No match, passing to cloud.")
        return None

    # 常见动作词（与技能目标词共同出现时判定为执行意图）
    _ACTION_VERBS = [
        "打开", "运行", "启动", "执行", "使用", "写入", "写上", "写一下", "写",
        "读取", "读一下", "读出来", "读", "清空", "清除", "清掉", "追加",
        "记录", "保存", "删除", "设置", "改成", "计算", "搜索", "查询",
        "显示", "播放", "发送", "生成", "创建", "关闭", "说出", "告诉",
    ]

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

        # 3. 相似技能整合：已有类似技能时，合并进去而不是创建重复
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
                # 合并失败 → 退回创建新技能
                logger.warning("[Agent] 技能 %s 合并失败，创建独立技能", skill_name)

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
        return re.search(r'(?:增强|升级|扩展|完善)\s*技能\s*(\w+)', user_input) is not None

    def _handle_enhance_skill(self, user_input: str) -> str:
        """
        按指令一次性增强技能（保留原功能 + 新增能力）。
        '增强技能 X：追加写入同一个记事本'
        """
        match = re.search(r'(?:增强|升级|扩展|完善)\s*技能\s*(\w+)(?:[:：]\s*(.*))?', user_input)
        if not match:
            return "请指定要增强的技能名称，例如：'增强技能 open_notepad：追加写入同一个记事本'"
        skill_name = match.group(1)
        instructions = (match.group(2) or "").strip()

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
        return re.search(r'(?:修复|优化|改进|升级|修理)\s*技能\s*(\w+)', user_input) is not None

    def _handle_fix_skill(self, user_input: str) -> str:
        match = re.search(r'(?:修复|优化|改进|升级|修理)\s*技能\s*(\w+)', user_input)
        if not match:
            return "请指定要修复的技能名称，例如：'修复技能 dance'"
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
        try:
            result = self.skills.execute(skill_name, params or {})
            if result and not result.startswith("[错误]"):
                self.permanent_memory.record_skill_result(skill_name, True)
                return result
            error = result or f"技能 {skill_name} 无输出"
            self.permanent_memory.record_skill_result(skill_name, False, error)
            return self._handle_skill_failure(skill_name, error)
        except Exception as e:
            self.permanent_memory.record_skill_result(skill_name, False, str(e))
            return self._handle_skill_failure(skill_name, str(e))

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

【技能执行协议（重要）】
如果用户的需求【可以用已安装技能完成】，你的回复必须以一行指令开头，不要只口头描述：
__EXEC__:技能名
__EXEC__:技能名|用户完整请求
- 技能名必须是上面【已安装的技能】列表中的名字
- 参数必须是用户的【完整原话】，不要改写、不要只传名词；
  技能内部会自己识别动作（写入/读取/清空/打开等）并提取内容
- 指令行之外不要输出任何说明文字

当前时间：{datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"""

            messages = [
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
