"""
增强版技能管理器 - 融合保护技能和自动加载
"""

import os
import importlib.util
import inspect
from typing import Dict, List
from config import settings
from utils.logger import logger


class EnhancedSkillManager:
    """增强版技能管理器 - 带保护技能"""
    
    # 系统保护技能（不可删除）
    PROTECTED_SKILLS = [
        "learn_preference",
        "get_current_skills", 
        "skill_manager",
        "create_skill"
    ]
    
    def __init__(self):
        self.skills_dir = settings.skills_dir
        self.skills = {}
        self._load_builtin_skills()
        self.load_skills()
    
    def _load_builtin_skills(self):
        """加载内置系统技能"""
        # 这些技能在运行时动态注入
        self.skills.update({
            "learn_preference": {
                "description": "学习用户偏好或名字",
                "params": {"pref_text": "偏好描述"}
            },
            "get_current_skills": {
                "description": "获取所有可用技能列表",
                "params": {}
            },
            "skill_manager": {
                "description": "技能管理（增删改查）",
                "params": {
                    "action": "'list' 或 'add' 或 'remove' 或 'update'",
                    "skill_name": "技能名称",
                    "func_code": "函数代码（可选）",
                    "description": "技能描述（可选）"
                }
            }
        })
    
    def load_skills(self):
        """加载 skills/ 目录下的所有技能"""
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            self._create_default_skills()
            return
        
        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                skill_name = filename[:-3]
                
                # 跳过保护技能（由内置系统提供）
                if skill_name in self.PROTECTED_SKILLS:
                    continue
                
                self._load_single_skill(skill_name)
    
    def _load_single_skill(self, skill_name: str):
        """加载单个技能"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
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
                logger.info(f"[SkillManager] 已加载: {skill_name}")
        except Exception as e:
            logger.error(f"[SkillManager] 加载 {skill_name} 失败: {e}")
    
    def _create_default_skills(self):
        """创建默认技能"""
        # 从旧架构迁移默认技能
        default_skills = {
            "add.py": '''
def add(a, b):
    """加法运算"""
    return str(a + b)

__skill_meta__ = {
    "description": "加法运算",
    "params": {"a": "数字", "b": "数字"}
}
''',
            "multiply.py": '''
def multiply(a, b):
    """乘法运算"""
    return str(a * b)

__skill_meta__ = {
    "description": "乘法运算",
    "params": {"a": "数字", "b": "数字"}
}
''',
            "open_notepad.py": '''
import subprocess
import os

def open_notepad():
    """打开记事本"""
    try:
        if os.name == 'nt':
            subprocess.Popen(['notepad.exe'])
            return "记事本已成功打开"
        else:
            return "错误：此功能仅支持Windows系统"
    except Exception as e:
        return f"打开记事本失败：{str(e)}"
''',
            "screenshot.py": '''
try:
    from PIL import ImageGrab
    import datetime
    
    def screenshot():
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{now}.png'
        ImageGrab.grab().save(filename)
        return f'截图已保存: {filename}'
except ImportError:
    def screenshot():
        return "错误：未安装 Pillow，请执行 'pip install pillow'"
'''
        }
        
        for name, code in default_skills.items():
            filepath = os.path.join(self.skills_dir, name)
            if not os.path.exists(filepath):
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(code)
                logger.info(f"[SkillManager] 已创建默认技能: {name}")
    
    def execute(self, skill_name: str, params: dict):
        """执行技能"""
        if skill_name not in self.skills:
            return f"[错误] 技能 {skill_name} 不存在"
        
        # 如果是保护技能，检查是否有实现
        if skill_name in self.PROTECTED_SKILLS:
            # 由外部注入实现
            return f"[提示] 系统技能 {skill_name} 需要外部实现"
        
        try:
            result = self.skills[skill_name]["func"](**params)
            return result
        except Exception as e:
            return f"[错误] 执行 {skill_name} 失败: {str(e)}"
    
    def get_skills_info(self) -> Dict:
        """获取所有技能信息"""
        return {
            name: {
                "description": info["description"],
                "params": info["params"],
                "protected": name in self.PROTECTED_SKILLS
            }
            for name, info in self.skills.items()
        }
    
    def list_skills(self) -> List[str]:
        """列出所有技能名称"""
        return list(self.skills.keys())
    
    def is_protected(self, skill_name: str) -> bool:
        """检查是否为保护技能"""
        return skill_name in self.PROTECTED_SKILLS