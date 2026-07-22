"""
Agent 核心循环 - 增强上下文支持
"""

from llm.router import ModelRouter
from core.enhanced_skill_manager import EnhancedSkillManager
from memory.compressed_memory import CompressedMemory
from core.skill_creator_enhanced import EnhancedSkillCreator
from utils.logger import logger
from config import settings
from llm.cloud_engine import CloudEngine
import json
import os


class AgentLoop:
    def __init__(self):
        self.router = ModelRouter()
        self.skills = EnhancedSkillManager()
        self.memory = CompressedMemory()
        self.creator = EnhancedSkillCreator()
        self.cloud = CloudEngine()
        self.max_steps = settings.max_steps
        
        # 上下文
        self.context = {}
        
        self.cloud.set_skills_info(self.skills.get_skills_info())
        self._register_protected_skills()
    
    def _register_protected_skills(self):
        """注册系统保护技能"""
        pass
    
    def _handle_protected_skill(self, skill_name: str, params: dict) -> str:
        """处理系统保护技能"""
        if skill_name == "learn_preference":
            return self._learn_preference(params.get("pref_text", ""))
        elif skill_name == "get_current_skills":
            return self._get_current_skills()
        elif skill_name == "skill_manager":
            return self._skill_manager(**params)
        elif skill_name == "create_skill":
            return self._create_skill(**params)
        return None
    
    def _learn_preference(self, pref_text: str) -> str:
        """学习偏好"""
        import re
        memory_file = os.path.join("data", "memory.json")
        if os.path.exists(memory_file):
            with open(memory_file, 'r', encoding='utf-8') as f:
                memory = json.load(f)
        else:
            memory = {"identity": {"name": ""}, "preferences": [], "other": []}
        
        name_match = re.search(r"(?:我是|我叫|我的名字是)\s*(.+?)(?:[，,。.]|$)", pref_text)
        if name_match:
            name = name_match.group(1).strip()
            memory["identity"]["name"] = name
            os.makedirs(os.path.dirname(memory_file), exist_ok=True)
            with open(memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, ensure_ascii=False, indent=2)
            return f"[记忆] 已记住: 你是 {name}"
        
        memory["preferences"].append(pref_text)
        os.makedirs(os.path.dirname(memory_file), exist_ok=True)
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
        return f"[记忆] 已记住: {pref_text}"
    
    def _get_current_skills(self) -> str:
        """获取技能列表"""
        info = self.skills.get_skills_info()
        visible = [name for name, data in info.items() if not data.get("protected", False)]
        if not visible:
            return "当前没有任何可用技能"
        result = f"【当前可用技能】（共 {len(visible)} 个）\n"
        for name in visible:
            result += f"  📦 {name}\n"
        return result.strip()
    
    def _skill_manager(self, action: str, skill_name: str = None, **kwargs) -> str:
        """技能管理"""
        if action == "list":
            return self._get_current_skills()
        elif action == "add":
            return "请使用 '增加技能' 或 '添加技能' 命令"
        elif action == "remove" and skill_name:
            if self.skills.is_protected(skill_name):
                return f"[错误] {skill_name} 是系统内部技能，不可操作"
            filepath = os.path.join("skills", f"{skill_name}.py")
            if os.path.exists(filepath):
                os.remove(filepath)
                self.skills.load_skills()
                return f"[成功] 已删除技能: {skill_name}"
            return f"[错误] 技能 {skill_name} 不存在"
        return f"[错误] 不支持的操作: {action}"
    
    def _create_skill(self, skill_name: str, description: str, params: dict = None) -> str:
        """创建技能"""
        if params is None:
            params = {}
        success, msg = self.creator.create_skill(skill_name, description, params)
        if success:
            self.skills.load_skills()
            self.cloud.set_skills_info(self.skills.get_skills_info())
        return msg
    
    def run(self, user_input: str, history: list = None) -> str:
        """主入口"""
        if history is None:
            history = []
        
        logger.info(f"[Agent] 处理: {user_input[:50]}...")
        
        # 1. 尝试本地处理（传递上下文）
        local_result = self.router.route_local(user_input)
        if local_result:
            # 更新上下文
            if "计算结果" in local_result:
                try:
                    import re
                    nums = re.findall(r'[\d.]+', local_result)
                    if nums:
                        self.context["last_math_result"] = float(nums[-1])
                except:
                    pass
            return local_result
        
        # 2. 云端推理
        for attempt in range(settings.max_retries):
            try:
                result = self._execute_cloud(user_input, history)
                if result and not result.startswith("[错误]"):
                    return result
                logger.warning(f"[Agent] 第 {attempt+1} 次尝试失败")
            except Exception as e:
                logger.error(f"[Agent] 执行异常: {e}")
        
        # 3. 最终降级
        return self._fallback_response(user_input)
    
    def _execute_cloud(self, user_input: str, history: list) -> str:
        """云端推理"""
        step = 0
        
        while step < self.max_steps:
            step += 1
            
            result = self.router.route_cloud(user_input, history)
            
            if isinstance(result, str):
                return result
            
            if isinstance(result, dict):
                status = result.get("status", "")
                
                if status == "done":
                    return result.get("answer", "已完成")
                
                if status == "give_up":
                    return result.get("answer", "无法解决")
                
                if status == "continue":
                    action = result.get("action")
                    params = result.get("params", {})
                    
                    # 检查是否为系统保护技能
                    if action in self.skills.PROTECTED_SKILLS:
                        output = self._handle_protected_skill(action, params)
                        if output:
                            return output
                    
                    # 执行普通技能
                    output = self.skills.execute(action, params)
                    if output and output.startswith("[错误]"):
                        return output
                    
                    history.append({"role": "assistant", "content": str(result)})
                    history.append({"role": "user", "content": f"结果: {output}。请继续。"})
                    continue
            
            return "[错误] AI 输出格式异常"
        
        return f"[错误] 超过最大步骤限制 ({self.max_steps} 步)"
    
    def _fallback_response(self, user_input: str) -> str:
        """降级响应"""
        if any(kw in user_input for kw in ["增加", "添加", "创建", "加一个"]):
            return "要添加新功能，请说 '增加技能：功能名'，例如 '增加技能：计算器'"
        return "抱歉，我没能理解你的意思。你可以试试：\n- 数学计算：3+5\n- 时间查询：现在几点\n- 添加功能：增加技能：计算器"