"""
GGB小虾米 核心 Agent
核心职责：记忆管理 + 技能管理 + 聊天分发
"""

from core.skill_manager import SkillManager
from core.skill_matcher import SkillMatcher
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

        screenshot_skill = self._find_screenshot_skill()
        if screenshot_skill and any(keyword in user_input_clean for keyword in ["截个图", "截图", "屏幕截图", "截屏"]):
            logger.info(f"[SkillMatch] Screenshot keyword detected, executing: {screenshot_skill}")
            return self._execute_skill(screenshot_skill)
        if any(keyword in user_input_clean for keyword in ["截个图", "截图", "屏幕截图", "截屏"]):
            logger.info("[SkillMatch] No screenshot skill found, returning guidance.")
            return "我还没有截图技能哦！你可以说 **新增技能：截图** 来添加这个功能。📸"

        action_match = re.match(r'^(?:打开|运行|启动|执行|使用)\s*(.+)$', user_input_clean)
        if not action_match:
            logger.info("[SkillMatch] No action word at start, skipping skill execution.")
            return None

        target = action_match.group(1).strip()
        logger.info(f"[SkillMatch] Extracted target: '{target}'")

        for skill_name, info in self.skills.skills.items():
            if self._skill_target_matches(target, skill_name, info):
                return self._execute_skill(skill_name)

        logger.info(f"[SkillMatch] No exact match for target '{target}', passing to cloud.")
        return None

    def _find_screenshot_skill(self):
        for skill_name in self.skills.skills.keys():
            if "screenshot" in skill_name.lower() or "截图" in skill_name:
                return skill_name
        return None

    def _skill_target_matches(self, target: str, skill_name: str, info: dict) -> bool:
        normalized_target = target.lower()
        if normalized_target == skill_name.lower():
            return True

        desc = info.get("description", "")
        normalized_desc = desc.replace("打开", "").replace("系统", "").replace("应用", "").strip().lower()
        return normalized_target in {desc.lower(), normalized_desc}

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
            "  • 所有重要事实\n\n"
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
            # 同时删除匹配规则
            self.matcher.remove_mapping(skill_name)
            return self.skills.delete_skill(skill_name)
        return "请指定要删除的技能名称，例如：'删除技能 calculator'"

    def _is_create_skill_query(self, user_input: str) -> bool:
        patterns = [r'新增\s*技能', r'增加\s*技能', r'创建\s*技能', r'添加\s*技能', r'生成\s*技能', r'帮我.*技能']
        return any(re.search(p, user_input) for p in patterns)

    def _handle_create_skill(self, user_input: str, history: list) -> str:
        description = user_input
        match = re.search(r'(?:新增|增加|创建|添加|生成)\s*技能[:：]?\s*(.+?)(?:[。.！!？?]|$)', user_input)
        if match:
            description = match.group(1).strip()
        
        skill_code, skill_name, skill_desc = self._generate_skill_via_api(description, history)
        
        if not skill_code:
            return "❌ 生成技能失败，请提供更详细的功能描述。😊"
        
        skills_dir = "skills"
        if not os.path.exists(skills_dir):
            os.makedirs(skills_dir)

        if not skill_name or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', skill_name):
            skill_name = self._to_filename(description) or "new_skill"

        filename = f"{skill_name}.py"
        filepath = os.path.join(skills_dir, filename)

        try:
            if os.path.exists(filepath):
                return f"⚠️ 技能 `{filename}` 已存在！"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(skill_code)

            self.skills.reload_skills()
            self.cloud.set_skills_info(self.skills.get_skills_info())
            self._update_memory_context()
            
            # 添加到匹配规则
            keyword = description.replace("打开 ", "").replace("创建 ", "")
            self.matcher.add_mapping(keyword, skill_name, skill_desc)

            return f"✅ **技能创建成功！** 🎉\n\n已创建：`{filename}`\n功能：{skill_desc}\n\n现在可以直接使用了！😊"
        except Exception as e:
            return f"❌ 创建技能失败：{str(e)}"

    def _generate_skill_via_api(self, description: str, history: list) -> tuple:
        system_prompt = (
            "你是技能生成助手。根据用户描述生成完整的技能Python文件。\n\n"
            "格式：\n"
            "def skill_name(param: str = '') -> str:\n"
            '    """功能描述"""\n'
            "    # 实现\n"
            "    return '结果'\n\n"
            "__skill_meta__ = {\n"
            '    "description": "描述",\n'
            '    "params": {}\n'
            "}\n\n"
            "规则：\n"
            "1. 函数名英文小写，下划线分隔\n"
            "2. 包含必要 import\n"
            "3. 包含 __skill_meta__\n"
            "4. 只返回代码"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            *history[-3:],
            {"role": "user", "content": f"生成技能：{description}"}
        ]

        try:
            result = self.cloud.chat(messages)
            skill_code = ""
            if isinstance(result, dict):
                skill_code = result.get("answer", "")
            elif isinstance(result, str):
                skill_code = result

            code_match = re.search(r'```python\s*(.*?)\s*```', skill_code, re.DOTALL)
            if code_match:
                skill_code = code_match.group(1)

            if not skill_code or len(skill_code) < 30:
                return None, None, None

            func_match = re.search(r'def\s+(\w+)\s*\(', skill_code)
            skill_name = func_match.group(1) if func_match else self._to_filename(description)

            desc_match = re.search(r'"description":\s*"([^"]+)"', skill_code)
            skill_desc = desc_match.group(1) if desc_match else description

            return skill_code, skill_name, skill_desc

        except Exception as e:
            logger.error(f"[Agent] API生成技能失败: {e}")
            return None, None, None

    def _execute_skill(self, skill_name: str) -> str:
        try:
            result = self.skills.execute(skill_name, {})
            if result and not result.startswith("[错误]"):
                return result
            return f"⚠️ 执行 **{skill_name}** 失败：{result}"
        except Exception as e:
            return f"❌ 执行技能失败：{str(e)}"

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
            
            system_prompt = f"""你是智能助手 **{self.agent_name}**。

【关于用户的信息】
{memory_context if memory_context else "暂无"}

【已安装的技能】
{skills_desc}

【你的核心能力】
1. 记忆管理 - 记住用户信息（姓名、偏好、重要事实），忘记用户信息
2. 技能管理 - 新增技能、删除技能、列出技能
3. 自由聊天 - 回答用户的问题

【重要规则】
1. 用自然、友好、热情的语气回答
2. 如果用户问"现在几点"或"几点了"，直接告诉当前时间
3. 如果用户说"截个图"或"截图"，直接执行截图技能
4. 如果用户说"打开XXX"，直接执行对应技能
5. 如果用户说"你好"或"hi"，热情回应
6. 直接输出自然语言，不要输出JSON格式

当前时间：{datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"""

            messages = [
                {"role": "system", "content": system_prompt},
                *history[-10:],
                {"role": "user", "content": user_input}
            ]
            
            result = self.cloud.chat(messages)
            
            if isinstance(result, dict):
                answer = result.get("answer", "")
                if answer and len(answer) > 1:
                    return answer
            if isinstance(result, str) and len(result) > 2:
                return result
            
            return "抱歉，我没有理解你的意思。你可以试试：\n- 记住什么：'记住我喜欢吃西瓜'\n- 查看记忆：'查看记忆'\n- 创建技能：'新增技能：打开浏览器'"
            
        except Exception as e:
            logger.error(f"[Agent] 云端聊天失败: {e}")
            return f"抱歉，我暂时无法回答。你可以换个方式问我。😊"