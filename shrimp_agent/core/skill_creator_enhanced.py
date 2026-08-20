"""
增强版技能创建器 - 融合旧架构的自修改优点
支持：AI自动生成代码、中文名称映射、备份恢复
"""

import os
import re
import json
import shutil
from datetime import datetime
from typing import Tuple, Optional
from config import settings
from utils.logger import logger
from llm.cloud_engine import CloudEngine


class EnhancedSkillCreator:
    """增强版技能创建器"""
    
    def __init__(self):
        self.skills_dir = settings.skills_dir
        self.backup_dir = os.path.join(settings.skills_dir, ".backups")
        self.cloud = CloudEngine()
        self._ensure_dirs()
        
    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(self.skills_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def normalize_name(self, name: str) -> str:
        """
        中文名称映射（从旧架构迁移）
        支持：除法→divide, 加法→add, 乘法→multiply 等
        """
        name_map = {
            "除法": "divide", "加法": "add", "减法": "subtract",
            "乘法": "multiply", "取余": "mod", "幂": "power",
            "平方": "square", "开方": "sqrt", "截图": "screenshot",
            "记事本": "notepad", "计算器": "calculator"
        }
        
        if name in name_map:
            return name_map[name]
        
        # 如果是英文，直接返回
        if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            return name
        
        # 其他中文，用时间戳
        return f"skill_{datetime.now().strftime('%H%M%S')}"
    
    def create_backup(self, skill_name: str) -> str:
        """创建技能备份（从旧架构迁移）"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        if not os.path.exists(filepath):
            return None
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(self.backup_dir, f"{skill_name}_{timestamp}.py")
        shutil.copy2(filepath, backup_path)
        logger.info(f"[Backup] 已备份: {backup_path}")
        return backup_path
    
    def generate_skill_code(self, skill_name: str, description: str, params: dict = None) -> str:
        """
        AI 生成技能代码（从旧架构迁移）
        包含：函数定义、文档字符串、元数据
        """
        if params is None:
            params = {}
        
        # 构建参数列表
        params_str = ", ".join([f"{k}" for k in params.keys()]) if params else ""
        params_doc = ", ".join([f"{k}: {v}" for k, v in params.items()]) if params else "无参数"
        
        # 调用 AI 生成代码（如果配置了 API）
        if settings.api_key and settings.api_key != "sk-xxx":
            try:
                prompt = f"""
请根据以下需求生成一个 Python 函数代码：
技能名称: {skill_name}
功能描述: {description}
参数: {params_doc}
                
要求：
1. 函数名使用 {skill_name}
2. 包含完整的文档字符串
3. 返回字符串结果
4. 包含 __skill_meta__ 元数据
5. 只输出代码，不要解释
"""
response = self.cloud.chat(prompt)
                if isinstance(response, str):
                    code = response.strip()
                    # 提取代码块
                    if code.startswith("```python"):
                        code = code[9:]
                    if code.endswith("```"):
                        code = code[:-3]
                    code = code.strip()
                    if 'def ' in code:
                        return code
            except Exception as e:
                logger.warning(f"[Creator] AI 生成失败，使用模板: {e}")
        
        # 使用模板生成（兜底）
        return self._generate_from_template(skill_name, description, params)
    
    def _generate_from_template(self, skill_name: str, description: str, params: dict) -> str:
        """从模板生成"""
        params_list = ", ".join(params.keys()) if params else ""
        params_doc = ", ".join([f"{k}: {v}" for k, v in params.items()]) if params else "无参数"
        meta_params = {k: "any" for k in params.keys()}

        return f'''
def {skill_name}({params_list}):
    """
    {description}
    
    参数:
        {params_doc}
    
    返回:
        str: 执行结果
    """
    return f"{description} 已执行，参数: {params_list}"

__skill_meta__ = {{
    "description": "{description}",
    "params": {json.dumps(meta_params, ensure_ascii=False)}
}}
'''
    
    def create_skill(self, skill_name: str, description: str, params: dict = None) -> Tuple[bool, str]:
        """
        创建技能（增强版）
        包含：名称规范化、备份、AI生成、自动加载
        """
        if params is None:
            params = {}
        
        # 1. 规范化名称
        skill_name = self.normalize_name(skill_name)
        
        # 2. 检查是否已存在
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        if os.path.exists(filepath):
            # 创建备份
            self.create_backup(skill_name)
        
        # 3. 生成代码
        code = self.generate_skill_code(skill_name, description, params)
        
        # 4. 验证语法
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            return False, f"生成的代码有语法错误: {e}"
        
        # 5. 写入文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)
            logger.info(f"[Creator] 已创建/更新: {skill_name}")
            return True, f"技能 {skill_name} 已成功{'更新' if os.path.exists(filepath + '.bak') else '创建'}"
        except Exception as e:
            return False, f"创建失败: {str(e)}"