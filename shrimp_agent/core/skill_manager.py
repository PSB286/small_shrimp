"""
技能管理器 - 加载、执行、管理技能
"""

import os
import importlib.util
import inspect
import json
import shutil
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

        self.skills = {}
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
                            "params": params,
                            "filepath": filepath
                        }
                        print(f"[SkillManager] 已加载: {skill_name}")
                except Exception as e:
                    print(f"[SkillManager] 加载 {skill_name} 失败: {e}")

    def reload_skills(self):
        """重新加载所有技能"""
        self.load_skills()

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

    def get_skill_code(self, skill_name: str) -> str:
        """获取技能源码"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def skill_exists(self, skill_name: str) -> bool:
        """检查技能是否存在"""
        return skill_name in self.skills

    def modify_skill(self, skill_name: str, new_code: str) -> str:
        """修改技能代码并重新加载"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")

        if not os.path.exists(filepath):
            return f"[错误] 技能 {skill_name} 不存在"

        try:
            backup_path = filepath + ".backup"
            shutil.copy2(filepath, backup_path)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_code)

            self.reload_skills()
            return f"[成功] 技能 {skill_name} 已修改并重新加载"
        except Exception as e:
            return f"[错误] 修改技能失败: {str(e)}"

    def delete_skill(self, skill_name: str) -> str:
        """删除技能"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")

        if not os.path.exists(filepath):
            return f"[错误] 技能 {skill_name} 不存在"

        try:
            os.remove(filepath)
            self.reload_skills()
            return f"[成功] 技能 {skill_name} 已删除"
        except Exception as e:
            return f"[错误] 删除技能失败: {str(e)}"

    def list_skills_formatted(self) -> str:
        """格式化输出技能列表"""
        if not self.skills:
            return "当前没有任何技能"

        lines = ["【当前技能列表】"]
        for name, info in self.skills.items():
            lines.append(f"  📦 {name} : {info['description']}")
        return "\n".join(lines)

    def toggle_skill(self, skill_name: str, enabled: bool) -> bool:
        """切换技能启用状态"""
        # 这里可以实现更复杂的启用/禁用逻辑
        # 目前简单实现：重命名文件或添加禁用标记
        if skill_name not in self.skills:
            return False

        # 简单实现：如果禁用，重命名为 .disabled
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        disabled_path = os.path.join(self.skills_dir, f"{skill_name}.py.disabled")

        if enabled:
            if os.path.exists(disabled_path):
                os.rename(disabled_path, filepath)
                self.reload_skills()
        else:
            if os.path.exists(filepath):
                os.rename(filepath, disabled_path)
                self.reload_skills()

        return True