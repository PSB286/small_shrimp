import os
import importlib.util
import inspect
import json
from config import settings

class SkillManager:
    def __init__(self):
        self.skills_dir = settings.skills_dir
        self.skills = {}
        self.load_skills()
        
    def load_skills(self):
        """加载 skills/ 目录下的所有技能"""
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            return
        
        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                skill_name = filename[:-3]
                filepath = os.path.join(self.skills_dir, filename)
                try:
                    spec = importlib.util.spec_from_file_location(skill_name, filepath)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, skill_name) and callable(getattr(module, skill_name)):
                        func = getattr(module, skill_name)
                        sig = inspect.signature(func)
                        params = {p: "any" for p in sig.parameters}
                        meta = getattr(module, "__skill_meta__", {})
                        description = meta.get("description", f"技能 {skill_name}")
                        
                        self.skills[skill_name] = {
                            "func": func,
                            "description": description,
                            "params": params
                        }
                        print(f"[SkillManager] 已加载: {skill_name}")
                except Exception as e:
                    print(f"[SkillManager] 加载 {skill_name} 失败: {e}")

    def execute(self, skill_name: str, params: dict):
        """执行技能"""
        if skill_name not in self.skills:
            return f"[错误] 技能 {skill_name} 不存在"
        
        try:
            result = self.skills[skill_name]["func"](**params)
            return result
        except Exception as e:
            return f"[错误] 执行 {skill_name} 失败: {str(e)}"

    def get_skills_info(self):
        """获取所有技能信息（供 API 使用）"""
        return {name: {
            "description": info["description"],
            "params": info["params"]
        } for name, info in self.skills.items()}