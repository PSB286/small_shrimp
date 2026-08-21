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
    return True


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


# ==================== LLM 迭代生成 ====================

def _llm_available():
    return CloudEngine is not None and settings.api_key and settings.api_key != "sk-xxx"


def _build_generation_prompt(capabilities, description, history=None, round_no=1, previous_errors=None):
    caps_json = json.dumps(capabilities, ensure_ascii=False, indent=2)
    lines = [
        "你是小虾米的技能生成器。根据【环境能力清单】和【用户需求】生成一个完整的 Python 技能文件。",
        "",
        "【环境能力清单】",
        caps_json,
        "",
        "【生成规则】",
        "1. 函数名用英文小写+下划线，如 walk_forward",
        "2. 只能使用能力清单里声明过的硬件：",
        "   from hardware import hw",
        "   hw.servo('舵机id').set_angle(角度, speed=速度)   # 角度必须在舵机量程内",
        "   hw.play_poses([{舵机id: 角度, ...}, ...], interval=秒)  # 动作序列",
        "   hw.display().show_emoji('😊') / hw.display().text([...])",
        "   hw.mic().listen(秒) / hw.speaker().say('文本')",
        "3. 舵机角度默认在 0~180 之间，动作间隔不小于 0.1 秒，步数有限",
        "4. import 只能使用标准库、清单内声明的库、以及 hardware",
        "5. 函数接收 param: str = '' 参数，返回字符串结果",
        "6. 必须包含 __skill_meta__ = {\"description\": \"...\", \"params\": {...}}",
        "7. 只输出 Python 代码，不要解释，不要用 markdown 代码块",
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
    返回 (code, name, desc, messages) 或 None（多次失败/无可用途径）
    """
    max_rounds = max_rounds or settings.max_generate_rounds
    messages = []

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
    code = code.strip()
    m = re.search(r'```(?:python)?\s*(.*?)```', code, re.DOTALL)
    if m:
        code = m.group(1).strip()
    return code


def _generate_from_template_match(description, capabilities):
    """按需求关键词匹配模板（离线兜底）。

    当前模板库为空（最简状态），直接返回 None；
    将来在 templates/skill_templates.py 添加模板后，此函数按关键词匹配生成。
    """
    if not TEMPLATES:
        return None
    for name, template in TEMPLATES.items():
        if template_available(name, capabilities):
            desc = template.get("description", "")
            if any(k in description for k in [name, desc]):
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
    返回新创建的技能文件名列表。
    """
    caps = capabilities if capabilities is not None else load_capabilities()
    created = []
    for name in available_templates(caps):
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
