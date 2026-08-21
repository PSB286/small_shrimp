"""
技能工厂 - 按能力清单生成/引导技能

生成路径：
LLM 路径（迭代生成）：生成 → 校验 → 失败则把原因喂回去重试
   （最多 max_generate_rounds 轮），校验 = 语法编译 + 能力约束检查。

模板路径（离线兜底）：能力模板库 templates/skill_templates.py 当前为空
   （最简状态，不预置任何技能模板）；将来需要离线基础技能时往库里加即可。

启动引导 bootstrap_skills()：当前模板库为空，不会预生成任何技能；
   技能全部由用户对话触发 LLM 按需生成。
"""

import ast
import json
import os
import re

from config import settings
from utils.logger import logger
from core.capability_checker import CapabilityChecker
from templates.skill_templates import TEMPLATES, list_templates

try:
    from llm.cloud_engine import CloudEngine
except Exception:  # pragma: no cover
    CloudEngine = None


# ==================== 模板渲染 ====================

def _servo_ids(capabilities):
    ids = []
    for a in capabilities.get("actuators") or []:
        if isinstance(a, dict) and a.get("id"):
            ids.append(a["id"])
    return ids


def _pick_tail(servo_ids):
    for sid in servo_ids:
        if "tail" in sid.lower() or "尾" in sid:
            return sid
    return servo_ids[0] if servo_ids else ""


def _pick_legs(servo_ids):
    legs = [s for s in servo_ids if "leg" in s.lower() or "腿" in s]
    if len(legs) < 4:
        for s in servo_ids:
            if s not in legs:
                legs.append(s)
            if len(legs) >= 4:
                break
    return legs


def render_template(template_name, capabilities, description=None):
    """把模板占位符按能力清单填充成可运行的技能代码"""
    template = TEMPLATES.get(template_name)
    if not template:
        return None
    ids = _servo_ids(capabilities)
    legs = _pick_legs(ids)
    desc = description or template["description"]

    tokens = {
        "@SERVO_IDS@": "', '".join(ids),
        "@TAIL_SERVO@": _pick_tail(ids),
        "@LEG0@": legs[0] if len(legs) > 0 else (ids[0] if ids else ""),
        "@LEG1@": legs[1] if len(legs) > 1 else (ids[0] if ids else ""),
        "@LEG2@": legs[2] if len(legs) > 2 else (ids[0] if ids else ""),
        "@LEG3@": legs[3] if len(legs) > 3 else (ids[0] if ids else ""),
        "@SERVO0@": ids[0] if len(ids) > 0 else "",
        "@SERVO1@": ids[1] if len(ids) > 1 else (ids[0] if ids else ""),
        "@SERVO2@": ids[2] if len(ids) > 2 else (ids[0] if ids else ""),
        "@SERVO3@": ids[3] if len(ids) > 3 else (ids[0] if ids else ""),
        "@SERVO4@": ids[4] if len(ids) > 4 else (ids[0] if ids else ""),
        "@DESC@": desc,
    }
    code = template["code"]
    for token, value in tokens.items():
        code = code.replace(token, value)
    return code


def template_available(template_name, capabilities):
    """判断模板要求的能力是否满足"""
    template = TEMPLATES.get(template_name)
    if not template:
        return False
    n_servos = len(_servo_ids(capabilities))
    for req in template["requires"]:
        if req == "actuators" and n_servos < 1:
            return False
        if req == "actuators>=4" and n_servos < 4:
            return False
        if req == "actuators>=3" and n_servos < 3:
            return False
        if req == "display" and not capabilities.get("display"):
            return False
        if req == "audio_in" and not capabilities.get("audio_in"):
            return False
        if req == "network" and not capabilities.get("network"):
            return False
    return True


def list_available_templates(capabilities):
    """
    返回模板列表（含可用状态），供"新增技能"界面使用。
    返回 [{"name", "description", "requires", "available"}]
    """
    result = []
    for name, template in TEMPLATES.items():
        result.append({
            "name": name,
            "description": template.get("description", ""),
            "requires": template.get("requires", []),
            "available": template_available(name, capabilities),
        })
    return result


def available_templates(capabilities):
    """返回当前能力清单下可用的模板名列表"""
    return [name for name in TEMPLATES if template_available(name, capabilities)]


# ==================== 校验 ====================

def validate_code(code, capabilities):
    """综合校验：语法 + 能力约束。返回 {"ok": bool, "violations": [str]}"""
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {"ok": False, "violations": ["语法错误: %s" % e]}
    result = CapabilityChecker(capabilities).check(code)
    return {"ok": result["ok"], "violations": result["violations"]}


def extract_skill_info(code):
    """从代码中提取技能名与描述"""
    name = None
    desc = ""
    m = re.search(r'def\s+(\w+)\s*\(', code)
    if m:
        name = m.group(1)
    m = re.search(r'"description":\s*"([^"]+)"', code)
    if m:
        desc = m.group(1)
    return name, desc


def sanitize_filename(name, fallback="new_skill"):
    """保证文件名合法"""
    if not name or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        clean = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff]', '_', name or "")
        if clean and re.search(r'[\u4e00-\u9fff]', clean):
            try:
                from pypinyin import pinyin, Style
                clean = ''.join(p[0] for p in pinyin(clean, style=Style.NORMAL)).lower()
            except Exception:
                clean = re.sub(r'[\u4e00-\u9fff]', '', clean)
        name = re.sub(r'[^a-zA-Z0-9_]', '', clean).strip('_').lower() or fallback
        if name[0].isdigit():
            name = "skill_" + name
    return name


# ==================== 技能成熟度保障：沙箱冒烟测试 + 自打磨 ====================

def sandbox_test(code, capabilities=None, timeout=5):
    """
    沙箱冒烟测试：加载技能函数，把外部调用（os.system/os.startfile/subprocess/网络）
    打桩（sys.modules + os 属性临时替换），验证技能能正常返回字符串、不抛异常、不死循环。
    返回 {"ok": bool, "error": str, "returns": [str], "calls": [str]}
    """
    import sys
    import types
    import threading

    calls = []

    def _stub(name):
        def fn(*a, **k):
            calls.append(name)
            return "模拟结果"
        return fn

    class _FakePopen:
        def __init__(self, *a, **k):
            calls.append("subprocess.Popen")
        def communicate(self, *a, **k):
            calls.append("subprocess.communicate")
            return (b"", b"")
        def wait(self, *a, **k):
            return 0
        def poll(self, *a, **k):
            return 0

    class _FakeSubprocess:
        Popen = _FakePopen
        def run(self, *a, **k):
            calls.append("subprocess.run")
            return _FakePopen()
        def call(self, *a, **k):
            calls.append("subprocess.call")
            return 0
        def check_call(self, *a, **k):
            calls.append("subprocess.check_call")
            return 0

    class _FakeRequests:
        def get(self, *a, **k):
            calls.append("requests.get")
            return types.SimpleNamespace(status_code=200, text="模拟响应",
                                         json=lambda: {"ok": True})
        def post(self, *a, **k):
            calls.append("requests.post")
            return types.SimpleNamespace(status_code=200, text="模拟响应",
                                         json=lambda: {"ok": True})

    class _FakeSocket:
        def create_connection(self, *a, **k):
            calls.append("socket.create_connection")
            return _FakePopen()
        def socket(self, *a, **k):
            calls.append("socket.socket")
            return _FakePopen()

    import os as _real_os

    # ---- 临时打桩（try/finally 保证恢复）----
    saved_modules = {}
    for name, fake in [("subprocess", _FakeSubprocess()),
                       ("requests", _FakeRequests()),
                       ("socket", _FakeSocket())]:
        saved_modules[name] = sys.modules.get(name)
        sys.modules[name] = fake

    saved_os_fns = {}
    for fn in ("system", "startfile", "popen"):
        if hasattr(_real_os, fn):
            saved_os_fns[fn] = getattr(_real_os, fn)
            setattr(_real_os, fn, _stub("os." + fn))

    try:
        namespace = {"__name__": "_sandbox_skill", "time": __import__("time")}
        exec(compile(code, "<sandbox>", "exec"), namespace)
    except Exception as e:
        result = {"ok": False, "error": "加载失败: %s" % e, "returns": [], "calls": calls}
    else:
        # 找到技能函数（第一个定义在沙箱里的函数）
        func = None
        for name, obj in namespace.items():
            if isinstance(obj, type(lambda: 0)) and getattr(obj, "__module__", "") == "_sandbox_skill":
                func = obj
                break
        if func is None:
            result = {"ok": False, "error": "未找到技能函数", "returns": [], "calls": calls}
        else:
            returns = []
            result = None
            for p in ["", "沙箱测试内容"]:
                box = {}

                def _run():
                    try:
                        box["value"] = func(p)
                    except Exception as e:
                        box["error"] = str(e)
                    finally:
                        box["done"] = True

                t = threading.Thread(target=_run, daemon=True)
                t.start()
                t.join(timeout)
                if not box.get("done"):
                    result = {"ok": False, "error": "执行超时（可能死循环），参数=%r" % p,
                              "returns": returns, "calls": calls}
                    break
                if "error" in box:
                    result = {"ok": False, "error": "执行报错: %s（参数=%r）" % (box["error"], p),
                              "returns": returns, "calls": calls}
                    break
                value = box.get("value")
                if not isinstance(value, str):
                    result = {"ok": False, "error": "返回值不是字符串: %r（参数=%r）" % (value, p),
                              "returns": returns, "calls": calls}
                    break
                returns.append(value)
            if result is None:
                result = {"ok": True, "error": "", "returns": returns, "calls": calls}
    finally:
        for name, saved in saved_modules.items():
            if saved is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved
        for fn, saved in saved_os_fns.items():
            setattr(_real_os, fn, saved)

    return result


def polish_skill_code(code, description, capabilities, max_rounds=2):
    """
    技能自打磨：静态校验 + 沙箱冒烟测试，失败则 LLM 修复并重测。
    返回 (final_code, rounds_used, log) ；彻底失败返回 (None, rounds, log)
    """
    check = validate_code(code, capabilities)
    if not check["ok"]:
        errors = check["violations"]
    else:
        test = sandbox_test(code, capabilities)
        errors = [test["error"]] if not test["ok"] else []

    if not errors:
        return code, 0, ["静态校验与冒烟测试全部通过"]

    if not _llm_available():
        return None, 0, ["无 LLM 可用，无法自修复"] + errors

    cloud = CloudEngine()
    log = []
    current = code
    for round_no in range(1, max_rounds + 1):
        log.append("第 %d 轮修复: %s" % (round_no, errors[0][:120]))
        system = (
            "你是小虾米的技能打磨器。技能代码有问题，请修复并输出完整代码。\n\n"
            "【环境能力清单】\n%s\n\n"
            "规则：\n"
            "1. 保持函数名和功能不变\n"
            "2. 修复列出的问题，并让技能更成熟：处理空参数、try/except 捕获异常、"
            "返回清晰的中文结果、不要死循环、不要 eval/exec\n"
            "3. 只输出 Python 代码，不要解释，不要 markdown 代码块"
            % json.dumps(capabilities, ensure_ascii=False, indent=2)
        )
        user = "【技能代码】\n%s\n\n【发现的问题】\n%s\n\n请输出修复后的完整代码。" % (
            current, "\n".join(errors[:8]))
        try:
            result = cloud.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            text = ""
            if isinstance(result, dict):
                text = result.get("answer", "")
            elif isinstance(result, str):
                text = result
            fixed = _strip_code_fence(text)
            if not fixed or len(fixed) < 30:
                errors = ["修复输出为空"]
                continue
            current = fixed
            check = validate_code(current, capabilities)
            if not check["ok"]:
                errors = check["violations"]
                continue
            test = sandbox_test(current, capabilities)
            if test["ok"]:
                log.append("第 %d 轮修复后通过 ✅" % round_no)
                return current, round_no, log
            errors = [test["error"]]
        except Exception as e:
            errors = ["修复调用异常: %s" % e]

    log.append("多次修复仍未通过: %s" % errors[0])
    return None, max_rounds, log


# ==================== 学习技能三要素 ====================

# 学习程度 → 生成要求（决定技能的完整度）
LEVEL_REQUIREMENTS = {
    "了解": "实现最基本的功能即可，能完成核心操作",
    "基本使用": "实现核心常用功能，覆盖主要操作",
    "熟练": "覆盖全部常见使用场景，处理好常见边界情况",
    "完全掌握": "尽可能覆盖该材料的全部常见使用方式、所有主要功能、边界情况与异常处理，做到开箱即用",
}


def parse_learning_fields(user_input):
    """
    从用户话中解析学习技能三要素：材料 / 学习内容 / 学习程度。
    返回 {"material", "content", "level"}（缺失的字段不存在）。
    """
    result = {}
    patterns = [
        (r'材料[:：]?\s*([^，,。;；\n]+)', "material"),
        (r'(?:学习内容|学什么|要学什么|内容)[:：]?\s*([^，,。;；\n]+)', "content"),
        (r'(?:要学习到|学习程度|程度|学到什么程度|学到)[:：]?\s*([^，,。;；\n]+)', "level"),
    ]
    for pat, key in patterns:
        m = re.search(pat, user_input)
        if m and m.group(1).strip():
            result[key] = m.group(1).strip()
    return result


def build_learning_description(material, content, level):
    """把三要素组合成技能生成描述（含完整度要求）"""
    req = LEVEL_REQUIREMENTS.get(level, LEVEL_REQUIREMENTS["完全掌握"])
    return "目标材料：%s。学习内容：%s。学习程度：%s（要求：%s）" % (material, content, level, req)


# ==================== 相似技能整合 ====================

# 常见动作词/修饰词：去掉它们后剩下的就是"目标物"（如 记事本）
_MERGE_NOISE_WORDS = [
    "打开", "运行", "启动", "执行", "写入", "读取", "删除", "创建", "关闭",
    "指定", "文字", "内容", "程序", "应用", "系统", "Windows", "并", "和",
    "与", "或", "的", "在", "中", "里", "到", "进", "把", "将", "请", "帮我",
    "管理", "支持", "功能", "操作", "可以选择", "可选择", "以及", "同时",
    "追加", "清空", "清除", "选择", "当前", "指定", "相应", "对应",
    "打印", "文件", "路径", "显示", "查看", "日期", "时间", "信息",
    "电脑", "计算机", "目标", "学习", "掌握", "使用", "程度", "材料",
    "完全", "要求", "方式",
    "实现", "基本", "功能", "即可", "完成", "核心", "常用", "覆盖",
    "主要", "全部", "常见", "场景", "处理", "边界", "情况", "尽可能",
    "所有", "异常", "做到", "开箱即用",
]


def extract_target(description):
    """从描述中提取目标名词（去动作词与修饰词后的核心词）"""
    target = description or ""
    # 先去掉括号内的补充内容（如"（要求：...）"），避免污染目标词
    target = re.sub(r'[（(][^)）]*[)）]', '', target)
    for w in _MERGE_NOISE_WORDS:
        target = target.replace(w, "")
    # 去掉标点与空白
    target = re.sub(r'[：:，,。.、；;！!？?（）()\[\]【】\s]+', '', target)
    # 去重（如"记事本记事本"→"记事本"），保证目标词干净
    target = ''.join(dict.fromkeys(target))
    return target.strip()


def find_similar_skills(description, existing_skills):
    """
    找出与需求相似的已有技能（基于目标名词重叠）。
    返回相似技能名列表。
    """
    target = extract_target(description)
    if len(target) < 2:
        return []
    similar = []
    for name, info in existing_skills.items():
        desc = info.get("description", "") or ""
        if target in desc or (target and target in extract_target(desc)):
            similar.append(name)
    return similar


def merge_skills(existing_name, existing_code, new_desc, new_code, capabilities):
    """
    把新技能整合进已有相似技能（LLM 合并 + 校验）。
    返回 (merged_code, merged_desc) 或 None（失败）。
    """
    if not _llm_available():
        return None
    caps_json = json.dumps(capabilities, ensure_ascii=False, indent=2)
    system = (
        "你是小虾米的技能整合器。用户已有技能【%s】，又生成了新技能【%s】。\n"
        "请把两者的功能合并成一个增强版技能，只输出合并后的完整 Python 代码。\n\n"
        "【环境能力清单】\n%s\n\n"
        "规则：\n"
        "1. 函数名保持 %s 不变（沿用已有技能名）\n"
        "2. 保留已有技能的全部功能，并支持新技能的功能（用 param 参数区分，param 为空走原有逻辑）\n"
        "3. 只能使用环境能力清单内真实存在的能力；本环境没有的能力不要用（如无屏幕就别用 hw.display）\n"
        "4. import 只能用标准库/清单库/hardware\n"
        "5. 函数接收 param: str = ''（param 是用户的完整请求文本，技能内部用关键词判断动作并提取内容）\n"
        "6. 保留 __skill_meta__，description 更新为能同时覆盖两个功能\n"
        "7. 写入文本建议：写到临时文件后 os.startfile 打开，不要用 SendKeys/COM 模拟键盘\n"
        "8. 已有技能中以下划线开头（_xxx）的辅助函数：保持原样，不要改它们的签名和调用方式\n"
        "9. 只输出 Python 代码，不要解释，不要 markdown 代码块"
        % (existing_name, new_desc, caps_json, existing_name)
    )
    user = (
        "【已有技能代码】\n%s\n\n"
        "【新技能代码】\n%s\n\n"
        "请输出合并后的完整代码。" % (existing_code, new_code)
    )
    # 合并最多尝试 2 轮：失败把校验/冒烟测试错误喂回重试
    errors = []
    for attempt in range(1, 3):
        try:
            if errors:
                user = (
                    "【已有技能代码】\n%s\n\n【新技能代码】\n%s\n\n"
                    "【上一轮合并结果的问题】\n%s\n\n请修复并输出合并后的完整代码。"
                    % (existing_code, new_code, "\n".join(errors))
                )
            cloud = CloudEngine()
            result = cloud.chat([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            code = ""
            if isinstance(result, dict):
                code = result.get("answer", "")
            elif isinstance(result, str):
                code = result
            code = _strip_code_fence(code)
            if not code or len(code) < 30:
                errors = ["合并输出为空"]
                continue
            # 校验合并结果：静态校验 + 沙箱冒烟测试
            check = validate_code(code, capabilities)
            if not check["ok"]:
                logger.info("[Factory] 合并第 %d 轮未通过校验: %s", attempt, check["violations"][:3])
                errors = check["violations"]
                continue
            test = sandbox_test(code, capabilities)
            if not test["ok"]:
                logger.info("[Factory] 合并第 %d 轮冒烟测试失败: %s", attempt, test["error"][:120])
                errors = [test["error"]]
                continue
            # 确认函数名仍是原技能名
            func_name = extract_skill_info(code)[0]
            if func_name != existing_name:
                logger.info("[Factory] 合并后函数名变了 (%s -> %s)，拒绝", existing_name, func_name)
                errors = ["函数名必须是 %s" % existing_name]
                continue
            desc = extract_skill_info(code)[1] or new_desc
            return code, desc
        except Exception as e:
            logger.warning("[Factory] 合并调用失败: %s", e)
            errors = ["合并调用异常: %s" % e]
    return None


# ==================== 技能能力推荐与增强 ====================

def suggest_skill_upgrades(skill_name, description, code, capabilities):
    """
    LLM 分析技能，推荐还可以补充哪些能力（参数/功能/边界情况）。
    返回 [{"title": str, "detail": str}]（最多5条）；LLM 不可用时返回 []。
    """
    if not _llm_available():
        return []
    caps_json = json.dumps(capabilities, ensure_ascii=False, indent=2)
    system = (
        "你是小虾米的技能评估器。分析一个技能，推荐它还可以补充哪些能力，"
        "让技能更完整、更好用（如额外的参数、常见场景、边界情况）。\n\n"
        "【环境能力清单】\n%s\n\n"
        "只输出 JSON 数组，不要任何其他内容：\n"
        '[{"title": "简短标题", "detail": "一句话说明"}]，最多5条' % caps_json
    )
    user = "技能名：%s\n描述：%s\n代码：\n%s" % (skill_name, description, code)
    try:
        cloud = CloudEngine()
        result = cloud.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        text = ""
        if isinstance(result, dict):
            text = result.get("answer", "")
        elif isinstance(result, str):
            text = result
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
        if not isinstance(data, list):
            return []
        return [
            {"title": str(x.get("title", "")), "detail": str(x.get("detail", ""))}
            for x in data[:5] if isinstance(x, dict) and x.get("title")
        ]
    except Exception as e:
        logger.warning("[Factory] 能力推荐失败: %s", e)
        return []


def enhance_skill(existing_name, existing_code, instructions, capabilities):
    """
    LLM 按指令增强已有技能（保留原功能 + 新增能力）。
    返回 (new_code, new_desc) 或 None（失败/校验不过）。
    """
    if not _llm_available():
        return None
    caps_json = json.dumps(capabilities, ensure_ascii=False, indent=2)
    system = (
        "你是小虾米的技能增强器。根据【增强指令】升级已有技能代码，"
        "保留原有全部功能，只输出增强后的完整 Python 代码。\n\n"
        "【环境能力清单】\n%s\n\n"
        "规则：\n"
        "1. 函数名保持 %s 不变\n"
        "2. 保留原有功能，新增指令要求的能力\n"
        "3. 只能使用环境清单里真实存在的能力；本环境没有的不要用\n"
        "4. import 只能用标准库/清单库/hardware\n"
        "5. 函数接收 param: str = ''（param 是用户的完整请求文本，技能内部用关键词判断动作并提取内容）\n"
        "6. 保留并更新 __skill_meta__ 的 description\n"
        "7. 只输出 Python 代码，不要解释，不要 markdown 代码块"
        % (caps_json, existing_name)
    )
    user = "【已有技能代码】\n%s\n\n【增强指令】\n%s\n\n请输出增强后的完整代码。" % (existing_code, instructions)
    try:
        cloud = CloudEngine()
        result = cloud.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        code = ""
        if isinstance(result, dict):
            code = result.get("answer", "")
        elif isinstance(result, str):
            code = result
        code = _strip_code_fence(code)
        if not code or len(code) < 30:
            return None
        check = validate_code(code, capabilities)
        if not check["ok"]:
            logger.info("[Factory] 增强结果未通过校验: %s", check["violations"][:3])
            return None
        test = sandbox_test(code, capabilities)
        if not test["ok"]:
            logger.info("[Factory] 增强结果冒烟测试失败: %s", test["error"][:120])
            return None
        func_name = extract_skill_info(code)[0]
        if func_name != existing_name:
            logger.info("[Factory] 增强后函数名变了 (%s -> %s)，拒绝", existing_name, func_name)
            return None
        desc = extract_skill_info(code)[1] or ""
        return code, desc
    except Exception as e:
        logger.warning("[Factory] 增强调用失败: %s", e)
        return None


# ==================== LLM 迭代生成 ====================

def _llm_available():
    return CloudEngine is not None and settings.api_key and settings.api_key != "sk-xxx"


def _build_generation_prompt(capabilities, description, history=None, round_no=1, previous_errors=None):
    caps_json = json.dumps(capabilities, ensure_ascii=False, indent=2)
    guide = _environment_guide(capabilities)
    lines = [
        "你是小虾米的技能生成器。根据【环境能力清单】和【用户需求】生成一个完整的 Python 技能文件。",
        "",
        "【环境能力清单】",
        caps_json,
        "",
        "【环境理解（先理解环境再写代码）】",
        guide,
        "",
        "【生成规则】",
        "1. 函数名用英文小写+下划线，如 open_notepad",
        "2. 只能使用环境里真实存在的能力：",
        "   - Windows 桌面能力: os.startfile / subprocess / PIL（若已安装）",
        "   - 硬件能力（仅在清单声明时）: hw.servo / hw.display / hw.mic / hw.speaker",
        "3. 舵机角度默认在 0~180 之间，动作间隔不小于 0.1 秒，步数有限",
        "4. import 只能使用标准库、清单内声明的库、以及 hardware",
        "5. 函数接收 param: str = '' 参数。param 是用户的【完整请求文本】，"
        "技能内部用关键词判断动作（如写入/读取/清空/打开）并提取内容，返回字符串结果",
        "6. 必须包含 __skill_meta__ = {\"description\": \"...\", \"params\": {...}}",
        "7. 只输出 Python 代码，不要解释，不要用 markdown 代码块",
        "",
        "【成熟度要求（让初版就能用）】",
        "8. 处理 param 为空/无内容的情况（给出友好提示）",
        "9. 用 try/except 捕获异常，失败返回清晰的中文错误信息",
        "10. 不要写死循环（while True 必须有 break/return）",
        "11. 不要用 eval/exec；尽量用 subprocess 而非 os.system",
        "12. 返回结果必须是字符串，且对用户有明确意义",
    ]
    if previous_errors:
        lines.append("")
        lines.append("【上一次生成的校验失败原因，请修复】")
        for err in previous_errors[:10]:
            lines.append("- " + err)
    lines.append("")
    lines.append("【用户需求】")
    lines.append(description)

    messages = [{"role": "system", "content": "\n".join(lines)}]
    if history:
        messages.extend(history[-3:])
    messages.append({"role": "user", "content": description})
    return messages


def generate_skill(description, capabilities, history=None, max_rounds=None):
    """
    迭代生成技能代码。
    先做环境可行性预检（理解环境 → 判断是否可行），
    返回 (code, name, desc, messages) 或 None（多次失败/无可用途径）
    """
    max_rounds = max_rounds or settings.max_generate_rounds
    messages = []

    # 0. 环境可行性预检：需求需要的能力，本环境是否有
    pre = precheck_feasibility(description, capabilities)
    if not pre["feasible"]:
        logger.info("[Factory] 可行性预检拦截: %s", pre["reason"])
        return None

    # 优先 LLM 迭代生成
    if _llm_available():
        cloud = CloudEngine()
        previous_errors = []
        for round_no in range(1, max_rounds + 1):
            try:
                prompt_messages = _build_generation_prompt(
                    capabilities, description, history, round_no, previous_errors
                )
                result = cloud.chat(prompt_messages)
                code = ""
                if isinstance(result, dict):
                    code = result.get("answer", "")
                elif isinstance(result, str):
                    code = result
                code = _strip_code_fence(code)
                if not code or len(code) < 30:
                    previous_errors.append("第 %d 轮: 返回内容过短或为空" % round_no)
                    continue

                check = validate_code(code, capabilities)
                if check["ok"]:
                    name, desc = extract_skill_info(code)
                    if not name:
                        name = sanitize_filename(description)
                    if not desc:
                        desc = description
                    return code, name, desc, ["LLM 生成，第 %d 轮通过" % round_no]
                previous_errors.extend(check["violations"])
                logger.info("[Factory] 第 %d 轮校验失败: %s", round_no, check["violations"][:3])
            except Exception as e:
                logger.warning("[Factory] LLM 生成异常: %s", e)
                previous_errors.append("调用异常: %s" % e)
        messages = previous_errors

    # LLM 不可用或失败 → 模板路径：按关键词匹配模板
    code = _generate_from_template_match(description, capabilities)
    if code:
        name, desc = extract_skill_info(code)
        return code, sanitize_filename(name, "new_skill"), desc or description, \
            ["模板生成"]

    return None


def _strip_code_fence(code):
    """
    从 LLM 输出中稳健提取 Python 代码。
    兼容：有/无围栏、围栏前有解释文字、语言标签(python/python3/py)、
    多个围栏片段等情况。提取不到返回 ""。
    """
    code = code.strip()
    if not code:
        return ""

    # 情况1：存在 ``` 围栏 —— 取第一对围栏之间的内容
    if "```" in code:
        parts = code.split("```")
        # parts 以 ``` 为界交替切分：文本/代码/文本/代码...
        for i in range(1, len(parts), 2):
            chunk = parts[i].lstrip("\n")
            lines = chunk.split("\n")
            # 去掉首行可能的语言标签（python / python3 / py 等）
            if len(lines) > 1 and re.match(r'^[a-zA-Z0-9_+-]*\s*$', lines[0]):
                lines = lines[1:]
            candidate = "\n".join(lines).strip()
            if candidate:
                return candidate
        return ""

    # 情况2：没有围栏 —— 去掉开头的解释文字，从第一行代码开始
    lines = code.split("\n")
    start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(("def ", "import ", "from ", "class ", "#", "__skill_meta__", "@")):
            start = i
            break
    return "\n".join(lines[start:]).strip()


# ==================== 环境可行性预检 ====================

# 需求关键词 → 需要的能力；缺失即判定"本环境做不了"
HARDWARE_KEYWORDS = [
    (["舵机", "伺服", "走路", "跑步", "奔跑", "跳舞", "跳个舞", "跳支舞", "舞蹈", "摇尾巴", "尾巴", "迈步", "动作序列", "servo", "pose"],
     "actuators", "舵机/动作硬件"),
    (["点亮屏幕", "屏幕显示", "显示表情", "oled", "lcd", "点阵屏", "屏幕表情"],
     "display", "屏幕"),
    (["收音", "录音", "麦克风", "听声音", "语音输入", "拾音", "听我说话"],
     "audio_in", "麦克风"),
    (["说话", "朗读", "语音播报", "语音输出", "tts", "喇叭", "开口说话"],
     "audio_out", "喇叭"),
    (["拍照", "摄像", "摄像头", "录像", "拍照片"],
     "camera", "摄像头"),
]


def precheck_feasibility(description, capabilities):
    """
    生成前可行性预检：先理解环境，再判断需求是否可行。
    返回 {"feasible": bool, "reason": str, "missing": [能力名]}
    """
    missing = []
    for keywords, cap_key, label in HARDWARE_KEYWORDS:
        if any(k in description for k in keywords) and not capabilities.get(cap_key):
            missing.append(label)
    if missing:
        return {
            "feasible": False,
            "missing": missing,
            "reason": "当前环境没有%s，无法生成这个技能" % "、".join(missing),
        }
    return {"feasible": True, "missing": [], "reason": ""}


def _environment_guide(capabilities):
    """
    把能力清单翻译成 LLM 能理解的环境说明：
    让生成器"先理解环境"，再写对应平台的代码。
    """
    lines = []
    platform = capabilities.get("platform", "")
    if "Windows" in platform:
        lines.append("- 系统: Windows，可用 os.startfile()/subprocess 打开程序、PIL 截图等")
    elif "Linux" in platform:
        lines.append("- 系统: Linux，可用 subprocess 执行系统命令")
    elif "Darwin" in platform or "mac" in platform.lower():
        lines.append("- 系统: macOS，可用 subprocess/os 打开程序")
    if capabilities.get("network"):
        lines.append("- 可联网: 可用 requests 请求网络")
    if capabilities.get("libs"):
        lines.append("- 已安装库: %s" % ", ".join(capabilities["libs"]))
    if capabilities.get("display"):
        lines.append("- 有屏幕: 可用 hw.display()")
    if capabilities.get("actuators"):
        lines.append("- 有舵机: 可用 hw.servo('id') / hw.play_poses([...])")
    if capabilities.get("audio_in"):
        lines.append("- 有麦克风: 可用 hw.mic()")
    if capabilities.get("audio_out"):
        lines.append("- 有喇叭: 可用 hw.speaker()")
    if capabilities.get("camera"):
        lines.append("- 有摄像头: 可用相应库")
    if not capabilities.get("actuators"):
        lines.append("- 无舵机/动作硬件，不要生成跳舞/走路/摇尾巴等动作类技能")
    if not capabilities.get("display"):
        lines.append("- 无硬件屏幕，不要生成 hw.display() 相关代码")
    return "\n".join(lines) if lines else "- 无特殊能力（纯文本环境）"


def _generate_from_template_match(description, capabilities):
    """按需求关键词匹配模板（离线兜底）：模板名或其简称（"（"前）出现在需求中即命中"""
    if not TEMPLATES:
        return None
    for name, template in TEMPLATES.items():
        if not template_available(name, capabilities):
            continue
        desc = template.get("description", "")
        short = desc.split("（")[0].strip() or desc
        if name in description or (short and short in description):
            return render_template(name, capabilities, description)
    return None


# ==================== 启动引导 ====================

def load_capabilities():
    """读取能力清单；不存在则先探测生成"""
    if os.path.exists(settings.capabilities_file):
        try:
            with open(settings.capabilities_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("[Factory] 能力清单读取失败: %s", e)
    from core.environment_probe import EnvironmentProbe
    probe = EnvironmentProbe()
    return probe.ensure_capabilities()


def bootstrap_skills(skill_manager=None, capabilities=None):
    """
    按能力清单自动生成本环境缺失的基础技能。
    只引导显式声明 "bootstrap": true 的模板（如未来硬件环境的基础动作），
    通用模板不会自动创建——统一走"新增技能 → 预览 → 确认"流程。
    返回新创建的技能文件名列表。
    """
    caps = capabilities if capabilities is not None else load_capabilities()
    created = []
    for name, template in TEMPLATES.items():
        if not template.get("bootstrap"):
            continue  # 未声明 bootstrap 的模板不自动创建
        if not template_available(name, caps):
            continue
        filepath = os.path.join(settings.skills_dir, name + ".py")
        if os.path.exists(filepath):
            continue
        code = render_template(name, caps)
        if not code:
            continue
        try:
            os.makedirs(settings.skills_dir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)
            logger.info("[Factory] 引导创建技能: %s", filepath)
            created.append(name)
        except Exception as e:
            logger.error("[Factory] 引导创建 %s 失败: %s", name, e)

    if created and skill_manager is not None:
        skill_manager.reload_skills()
    if created:
        from hardware import reload_hardware
        reload_hardware()
    return created
