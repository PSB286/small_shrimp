# -*- coding: utf-8 -*-
"""
能力模板库 - 通用技能模板

模板用于"新增技能"界面的一键添加（点选 → 预览 → 确认）。
当前全部为跨平台通用技能（不需要特定硬件）：
时间 / 计算 / 文件操作 / 目录列表 / 系统信息 / 网络搜索 / 备忘记录

每份模板声明 requires：不满足的环境模板不可用（界面置灰显示原因）。
代码全部走标准库 + 打桩可测，保证初版可用。
"""

SHOW_TIME = """import datetime

def show_time(param: str = ''):
    \"\"\"@DESC@\"\"\"
    now = datetime.datetime.now()
    return f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M:%S')}"

__skill_meta__ = {"description": "@DESC@", "params": {}, "tier": 1}
"""

CALC = """import re

def calc(param: str = ''):
    \"\"\"@DESC@\"\"\"
    if not param:
        return "请提供算式，例如：3+5*2"
    expr = param.replace("×", "*").replace("x", "*").replace("÷", "/").replace("X", "*")
    if not re.match(r'^[\\d\\s+\\-*/%.()]+$', expr):
        return "算式包含不支持的字符"
    try:
        result = eval(expr)
        return f"计算结果：{result}"
    except Exception as e:
        return f"计算失败：{e}"

__skill_meta__ = {"description": "@DESC@", "params": {"param": "算式，如 3+5*2"}, "tier": 1}
"""

FILE_OPS = """import os

def file_ops(param: str = ''):
    \"\"\"@DESC@\"\"\"
    if not param:
        return "请说明要做什么，例如：读取 C:/a.txt、写入 C:/a.txt 内容、列出 C:/目录"
    try:
        if param.startswith("读取") or param.startswith("读"):
            path = param.replace("读取", "").replace("读", "").strip()
            if not os.path.exists(path):
                return f"文件不存在：{path}"
            with open(path, "r", encoding="utf-8") as f:
                return f"文件内容：\\n{f.read()[:500]}"
        if param.startswith("写入") or param.startswith("写"):
            rest = param.replace("写入", "").replace("写", "").strip()
            if " 内容 " in rest or " 内容:" in rest:
                path, _, content = rest.partition(" 内容 ")
                path = path.strip()
                if not content:
                    _, _, content = rest.partition(" 内容:")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content.strip())
                return f"已写入：{path}"
            return "写入格式：写入 路径 内容:xxx"
        if param.startswith("列出") or param.startswith("列"):
            path = param.replace("列出", "").replace("列", "").strip() or "."
            names = os.listdir(path) if os.path.exists(path) else []
            return f"目录 {path} 共 {len(names)} 项：{', '.join(names[:20])}"
        return "支持：读取 路径 / 写入 路径 内容:xxx / 列出 路径"
    except Exception as e:
        return f"操作失败：{e}"

__skill_meta__ = {"description": "@DESC@", "params": {"param": "如：读取 C:/a.txt"}, "tier": 1}
"""

SYSTEM_INFO = """import platform
import os

def system_info(param: str = ''):
    \"\"\"@DESC@\"\"\"
    try:
        lines = [
            f"系统：{platform.system()} {platform.release()}",
            f"Python：{platform.python_version()}",
            f"处理器：{platform.processor() or '未知'}",
            f"架构：{platform.machine()}",
            f"当前目录：{os.getcwd()}",
        ]
        return "\\n".join(lines)
    except Exception as e:
        return f"获取失败：{e}"

__skill_meta__ = {"description": "@DESC@", "params": {}, "tier": 1}
"""

WEB_SEARCH = """import requests

def web_search(param: str = ''):
    \"\"\"@DESC@\"\"\"
    if not param:
        return "请提供搜索关键词"
    try:
        url = f"https://api.duckduckgo.com/?q={param}&format=json&no_html=1"
        data = requests.get(url, timeout=8).json()
        abstract = data.get("Abstract", "")
        if abstract:
            return f"搜索结果：{abstract[:200]}"
        topics = data.get("RelatedTopics", [])
        for t in topics[:3]:
            if isinstance(t, dict) and t.get("Text"):
                return f"搜索结果：{t['Text'][:200]}"
        return f"没有找到「{param}」的摘要信息"
    except Exception as e:
        return f"搜索失败：{e}"

__skill_meta__ = {"description": "@DESC@", "params": {"param": "搜索关键词"}, "tier": 1}
"""

MEMO = """import os

_MEMO_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "shrimp_memo.txt")

def memo(param: str = ''):
    \"\"\"@DESC@\"\"\"
    req = (param or "").strip()
    if not req:
        return "请告诉我记什么，例如：记住 明天开会"
    if req.startswith("记住") or req.startswith("记"):
        content = req.replace("记住", "").replace("记", "").strip()
        with open(_MEMO_FILE, "a", encoding="utf-8") as f:
            f.write(content + "\\n")
        return f"已记录：{content}"
    if "读" in req or "看看" in req:
        if not os.path.exists(_MEMO_FILE):
            return "备忘还是空的"
        with open(_MEMO_FILE, "r", encoding="utf-8") as f:
            return f"我的备忘：\\n{f.read()}"
    if "清空" in req or "清除" in req:
        with open(_MEMO_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return "备忘已清空"
    return f"已记录：{req}"

__skill_meta__ = {"description": "@DESC@", "params": {"param": "如：记住 明天开会"}, "tier": 1}
"""


TEMPLATES = {
    "show_time": {
        "description": "显示当前日期和时间",
        "requires": [],
        "code": SHOW_TIME,
    },
    "calc": {
        "description": "数学计算（支持 + - * / % 和括号）",
        "requires": [],
        "code": CALC,
    },
    "file_ops": {
        "description": "文件操作：读取 / 写入 / 列出目录",
        "requires": [],
        "code": FILE_OPS,
    },
    "system_info": {
        "description": "查看系统信息（系统/Python/处理器/目录）",
        "requires": [],
        "code": SYSTEM_INFO,
    },
    "web_search": {
        "description": "联网搜索并返回摘要",
        "requires": ["network"],
        "code": WEB_SEARCH,
    },
    "memo": {
        "description": "备忘记录：记住 / 查看 / 清空",
        "requires": [],
        "code": MEMO,
    },
}


def list_templates():
    """返回模板名+描述"""
    return {name: t["description"] for name, t in TEMPLATES.items()}


def get_template(name):
    return TEMPLATES.get(name)
