"""
技能创建器 - 主动生成并注册新技能插件
"""

import os
import re
import json
import inspect
import importlib.util
from datetime import datetime
from typing import Dict, Optional, Tuple
from config import settings
from utils.logger import logger
from llm.cloud_engine import CloudEngine


class SkillCreator:
    """主动创建技能插件"""
    
    def __init__(self):
        self.skills_dir = settings.skills_dir
        self.templates_file = os.path.join(settings.skills_dir, "..", "data", "skill_templates.json")
        self.cloud = CloudEngine()
        self._ensure_templates()
        
    def _ensure_templates(self):
        """确保模板库存在"""
        os.makedirs(os.path.dirname(self.templates_file), exist_ok=True)
        if not os.path.exists(self.templates_file):
            default_templates = {
                "common": {
                    "description": "通用技能模板",
                    "code": """def {name}({params}):
    \"\"\"{description}\"\"\"
    return "{description} 已执行"
"""
                },
                "screenshot": {
                    "description": "截图技能",
                    "code": """from PIL import ImageGrab
import datetime
import os

def {name}():
    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'screenshot_{{now}}.png'
    ImageGrab.grab().save(filename)
    try:
        os.startfile(filename)
    except AttributeError:
        import subprocess
        if os.name == 'posix':
            subprocess.run(['open', filename])
        else:
            subprocess.run(['xdg-open', filename])
    return f'截图已保存并打开: {{filename}}'
"""
                },
                "web_search": {
                    "description": "网页搜索",
                    "code": """import requests
from urllib.parse import quote

def {name}(query):
    \"\"\"搜索关键词\"\"\"
    encoded = quote(query)
    url = f'https://api.duckduckgo.com/?q={encoded}&format=json'
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        return f'搜索结果: {data.get("Abstract", "未找到相关信息")}'
    except Exception as e:
        return f'搜索失败: {str(e)}'
"""
                },
                "file_operation": {
                    "description": "文件操作",
                    "code": """import os
import json
from datetime import datetime

def {name}(action, path, content=None):
    \"\"\"文件操作: read/write/list\"
    try:
        if action == 'read':
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()[:500]
        elif action == 'write' and content:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            return f'已写入: {path}'
        elif action == 'list':
            files = os.listdir(path) if os.path.exists(path) else []
            return f'文件列表: {", ".join(files[:10])}'
        else:
            return f'不支持的操作: {action}'
    except Exception as e:
        return f'操作失败: {str(e)}'
"""
                }
            }
            with open(self.templates_file, 'w', encoding='utf-8') as f:
                json.dump(default_templates, f, ensure_ascii=False, indent=2)
            logger.info(f"[SkillCreator] 已创建模板库: {self.templates_file}")
    
    def analyze_need(self, conversation: list) -> Optional[Dict]:
        """
        分析对话，识别需要新增技能的场景
        """
        # 提取最近10轮对话
        recent = conversation[-10:] if len(conversation) > 10 else conversation
        context = "\n".join([
            f"{'用户' if msg.get('role') == 'user' else '助手'}: {msg.get('content', '')[:100]}"
            for msg in recent
        ])
        
        prompt = f"""
分析以下对话，判断用户是否反复提出类似的需求，这些需求可以通过一个自动化技能来解决。

对话历史：
{context}

请分析：
1. 用户是否多次提到类似的操作或需求？
2. 这些操作是否可以封装成一个固定的技能？
3. 如果是，请给出技能名称（英文、小写、下划线分隔）、功能描述和参数说明。

输出格式（JSON）：
{{
    "should_create": true/false,
    "skill_name": "技能名",
    "description": "功能描述",
    "params": {{"参数名": "参数类型说明"}},
    "reason": "为什么要创建这个技能"
}}

如果不需要创建新技能，返回 {{"should_create": false, "reason": "原因"}}
"""
        try:
            response = self.cloud.chat(prompt)
            # 解析响应
            if isinstance(response, dict):
                return response
            return None
        except Exception as e:
            logger.error(f"[SkillCreator] 分析需求失败: {e}")
            return None
    
    def generate_skill_code(self, skill_name: str, description: str, params: dict) -> str:
        """
        生成技能插件代码
        """
        # 构造参数列表
        param_str = ", ".join([f"{k}={repr(v)}" for k, v in params.items()]) if params else ""
        param_list = ", ".join(params.keys()) if params else ""
        
        # 使用模板或调用 AI 生成
        prompt = f"""
请为以下需求生成一个 Python 函数代码：

技能名称: {skill_name}
功能描述: {description}
参数: {params}

要求：
1. 函数名必须是 {skill_name}
2. 函数必须包含所有参数
3. 必须返回字符串结果
4. 包含必要的 import 语句
5. 添加完整的函数文档字符串
6. 包含 __skill_meta__ 元数据

输出格式：只输出 Python 代码，不要有其他内容。
"""
        try:
            # 尝试从模板生成
            code = self._generate_from_template(skill_name, description, params)
            if code:
                # 添加元数据
                code = self._add_metadata(code, skill_name, description, params)
                return code
        except Exception as e:
            logger.warning(f"[SkillCreator] 模板生成失败: {e}")
        
        # 使用 AI 生成
        try:
            response = self.cloud.chat(prompt)
            if isinstance(response, str):
                # 清理代码
                code = response.strip()
                if code.startswith("```python"):
                    code = code[9:]
                if code.endswith("```"):
                    code = code[:-3]
                code = code.strip()
                # 确保包含元数据
                if "__skill_meta__" not in code:
                    code = self._add_metadata(code, skill_name, description, params)
                return code
        except Exception as e:
            logger.error(f"[SkillCreator] AI 生成失败: {e}")
        
        # 使用默认模板
        return self._generate_default(skill_name, description, params)
    
    def _generate_from_template(self, name: str, desc: str, params: dict) -> Optional[str]:
        """从模板生成"""
        with open(self.templates_file, 'r', encoding='utf-8') as f:
            templates = json.load(f)
        
        # 根据描述匹配模板
        desc_lower = desc.lower()
        for template_name, template in templates.items():
            if template_name in desc_lower or desc_lower in template_name:
                code = template["code"]
                # 替换变量
                code = code.replace("{name}", name)
                code = code.replace("{description}", desc)
                params_str = ", ".join([f"{k}: {v}" for k, v in params.items()])
                code = code.replace("{params}", params_str)
                return code
        return None
    
    def _add_metadata(self, code: str, name: str, desc: str, params: dict) -> str:
        """添加技能元数据"""
        meta = f'''
__skill_meta__ = {{
    "description": "{desc}",
    "params": {params}
}}
'''
        return code + "\n\n" + meta
    
    def _generate_default(self, name: str, desc: str, params: dict) -> str:
        """生成默认技能"""
        params_str = ", ".join([f"{k}={repr(v)}" for k, v in params.items()]) if params else ""
        return f'''
def {name}({params_str}):
    """{desc}"""
    return "{desc} 已执行，参数: {params_str}"

__skill_meta__ = {{
    "description": "{desc}",
    "params": {params}
}}
'''
    
    def create_skill(self, skill_name: str, description: str, params: dict) -> Tuple[bool, str]:
        """
        创建并注册新技能插件
        Returns: (success, message)
        """
        # 验证技能名称
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', skill_name):
            return False, f"无效的技能名称: {skill_name}，请使用英文和下划线"
        
        # 检查是否已存在
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        if os.path.exists(filepath):
            return False, f"技能 {skill_name} 已存在"
        
        # 生成代码
        code = self.generate_skill_code(skill_name, description, params)
        
        # 验证代码（编译检查）
        try:
            compile(code, '<string>', 'exec')
        except SyntaxError as e:
            return False, f"生成的代码有语法错误: {e}"
        
        # 写入文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(code)
            logger.info(f"[SkillCreator] 已创建技能: {filepath}")
            
            # 返回成功，由 SkillManager 热加载
            return True, f"技能 {skill_name} 已创建，文件: {filepath}"
        except Exception as e:
            return False, f"创建失败: {str(e)}"
    
    def get_templates(self) -> dict:
        """获取所有模板"""
        with open(self.templates_file, 'r', encoding='utf-8') as f:
            return json.load(f)