"""
能力约束校验器 - AST 静态检查

自优化/生成闭环的"第二道闸门"：技能代码只能使用能力清单里
声明过的硬件与库。代码调用清单之外的硬件/API 直接判违规，
防止 AI 生成的技能去操作本环境没有的东西。

校验规则：
1. 语法必须可编译
2. import 的模块必须是：标准库 ∪ 能力清单声明的库 ∪ hardware
3. hw.servo("xxx") / 动作序列里的舵机 id 必须存在于能力清单
4. hw.display() / hw.mic() / hw.speaker() 必须对应能力存在
"""

import ast
import json

from utils.logger import logger


# 常用标准库（Python 3.8 兼容，无 sys.stdlib_module_names）
STDLIB_MODULES = {
    "abc", "argparse", "array", "ast", "asyncio", "base64", "bisect", "builtins",
    "calendar", "cgi", "cmath", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal", "difflib", "dis",
    "email", "enum", "errno", "fcntl", "filecmp", "fnmatch", "fractions", "functools",
    "gc", "getopt", "getpass", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "importlib", "inspect", "io", "itertools", "json", "keyword", "linecache",
    "locale", "logging", "lzma", "math", "mimetypes", "mmap", "multiprocessing", "numbers",
    "operator", "os", "pathlib", "pickle", "pkgutil", "platform", "plistlib", "pprint",
    "profile", "pstats", "queue", "random", "re", "reprlib", "select", "selectors",
    "shelve", "shlex", "shutil", "signal", "site", "socket", "socketserver", "sqlite3",
    "ssl", "statistics", "string", "struct", "subprocess", "sys", "sysconfig", "tarfile",
    "tempfile", "textwrap", "threading", "time", "timeit", "token", "tokenize", "trace",
    "traceback", "tracemalloc", "types", "typing", "unicodedata", "unittest", "urllib",
    "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser", "winreg",
    "winsound", "wsgiref", "xml", "xmlrpc", "zipfile", "zipimport", "zlib",
}

# 额外允许的常用第三方小库（技能生成常见）
EXTRA_ALLOWED = {"pypinyin", "requests", "PIL"}


class CapabilityChecker:
    def __init__(self, capabilities=None):
        self.capabilities = capabilities or {}
        self._servo_ids = set()
        for a in self.capabilities.get("actuators") or []:
            if isinstance(a, dict) and a.get("id"):
                self._servo_ids.add(a["id"])
        self._has_display = bool(self.capabilities.get("display"))
        self._has_mic = bool(self.capabilities.get("audio_in"))
        self._has_speaker = bool(self.capabilities.get("audio_out"))

    # ---------- 对外接口 ----------

    def check(self, code):
        """
        校验技能代码。返回 {"ok": bool, "violations": [str], "warnings": [str]}
        """
        violations = []
        warnings = []

        # 1. 语法
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return {"ok": False, "violations": ["语法错误: %s" % e], "warnings": []}

        # 2. 导入检查
        allowed_imports = STDLIB_MODULES | EXTRA_ALLOWED | set(self.capabilities.get("libs") or []) | {"hardware"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top not in allowed_imports:
                        violations.append("导入 '%s' 不在允许列表内（标准库/能力库/hardware）" % alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:  # 相对导入
                    continue
                top = node.module.split(".")[0]
                if top not in allowed_imports:
                    violations.append("导入 '%s' 不在允许列表内（标准库/能力库/hardware）" % node.module)

        # 3. 硬件使用检查
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            # 只检查 hw.xxx(...) 形式
            if not (isinstance(func.value, ast.Name) and func.value.id == "hw"):
                continue
            attr = func.attr
            if attr == "servo":
                sid = self._arg_string(node)
                if sid is None:
                    warnings.append("hw.servo() 参数不是固定字符串，无法静态校验")
                elif sid not in self._servo_ids:
                    violations.append("使用了未声明的舵机 '%s'（本环境: %s）"
                                      % (sid, sorted(self._servo_ids) or "无"))
            elif attr == "play_poses":
                if not self._servo_ids:
                    violations.append("本环境没有任何舵机，无法播放动作序列")
                else:
                    for sid in self._pose_servo_ids(node):
                        if sid not in self._servo_ids:
                            violations.append("动作序列引用了未声明的舵机 '%s'" % sid)
            elif attr in ("display", "mic", "speaker"):
                # 调用方式检查：hw.display() 是取设备的方法，不能带参数
                if node.args or node.keywords:
                    violations.append(
                        "hw.%s() 不接受参数：应先取设备再调方法，如 hw.display().text([...]) / hw.display().show_emoji('😊')" % attr
                    )
                # 能力存在性检查
                if attr == "display" and not self._has_display:
                    violations.append("本环境没有屏幕设备，不能调用 hw.display()")
                elif attr == "mic" and not self._has_mic:
                    violations.append("本环境没有麦克风设备，不能调用 hw.mic()")
                elif attr == "speaker" and not self._has_speaker:
                    violations.append("本环境没有喇叭设备，不能调用 hw.speaker()")

        return {"ok": not violations, "violations": violations, "warnings": warnings}

    # ---------- 辅助 ----------

    def _arg_string(self, call_node):
        if call_node.args and isinstance(call_node.args[0], ast.Constant) and isinstance(call_node.args[0].value, str):
            return call_node.args[0].value
        return None

    def _pose_servo_ids(self, call_node):
        """提取 play_poses(poses, ...) 中姿态字典的舵机 id"""
        ids = []
        if not call_node.args:
            return ids
        first = call_node.args[0]
        if isinstance(first, ast.List):
            for item in first.elts:
                if isinstance(item, ast.Dict):
                    for key in item.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            ids.append(key.value)
        return ids


def check_skill_code(code, capabilities):
    """便捷函数"""
    return CapabilityChecker(capabilities).check(code)
