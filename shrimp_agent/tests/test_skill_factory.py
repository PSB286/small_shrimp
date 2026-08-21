# -*- coding: utf-8 -*-
"""技能工厂测试（最简状态）：模板库为空、LLM 路径、校验、名称清洗"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import skill_factory
from config import settings
from templates.skill_templates import TEMPLATES, list_templates


def test_templates_present():
    """通用模板库非空，且 web_search 需要 network 能力"""
    assert len(TEMPLATES) >= 5
    assert "calc" in TEMPLATES
    assert "web_search" in TEMPLATES
    assert "network" in TEMPLATES["web_search"]["requires"]


def test_available_templates_by_capability():
    """无网络能力时 web_search 不可用，其余通用模板可用"""
    names = skill_factory.available_templates({})
    assert "calc" in names
    assert "show_time" in names
    assert "web_search" not in names  # 需要 network
    names2 = skill_factory.available_templates({"network": True})
    assert "web_search" in names2


def test_render_template_none():
    code = skill_factory.render_template("walk", {})
    assert code is None


def test_template_available_false():
    assert skill_factory.template_available("walk", {}) is False


def test_generate_offline_returns_none():
    """无 LLM + 无模板 → 无法生成，返回 None（不会硬造）"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        result = skill_factory.generate_skill("随便什么需求", {}, max_rounds=1)
        assert result is None
    finally:
        settings.api_key = old


def test_validate_code():
    good = '''def hello(param=""):
    return "你好 " + param

__skill_meta__ = {"description": "打招呼", "params": {}}
'''
    check = skill_factory.validate_code(good, {})
    assert check["ok"], check

    bad = "def x(:\n    return"
    check = skill_factory.validate_code(bad, {})
    assert not check["ok"]


def test_extract_skill_info():
    code = '''def greet(param=""):
    return "hi"

__skill_meta__ = {"description": "打招呼", "params": {}}
'''
    name, desc = skill_factory.extract_skill_info(code)
    assert name == "greet"
    assert desc == "打招呼"


def test_sanitize_filename():
    assert skill_factory.sanitize_filename("greet") == "greet"
    assert skill_factory.sanitize_filename("bad name!") == "bad_name"
    assert skill_factory.sanitize_filename("") == "new_skill"
    assert skill_factory.sanitize_filename("123abc") == "skill_123abc"


def test_precheck_feasibility():
    """生成前可行性预检：先理解环境再判断"""
    # Windows 无硬件：打开记事本可行
    win = {"platform": "Windows / Python 3.8.10", "network": True, "libs": ["PIL"]}
    r = skill_factory.precheck_feasibility("打开记事本", win)
    assert r["feasible"] is True

    # 无舵机：跳舞不可行，并说明缺什么
    r = skill_factory.precheck_feasibility("跳舞", win)
    assert r["feasible"] is False
    assert "舵机" in r["reason"]

    # 无麦克风：收音不可行
    r = skill_factory.precheck_feasibility("帮我收音", win)
    assert r["feasible"] is False
    assert "麦克风" in r["reason"]

    # 声明了舵机后：跳舞可行
    dog = {"actuators": [{"id": "leg_fl", "type": "servo"}]}
    r = skill_factory.precheck_feasibility("跳一支舞", dog)
    assert r["feasible"] is True


def test_extract_target():
    """目标名词提取：去掉动作词后得到核心目标"""
    assert "记事本" in skill_factory.extract_target("打开记事本并写入指定文字")
    assert "记事本" in skill_factory.extract_target("打开 Windows 记事本程序")
    assert "浏览器" in skill_factory.extract_target("用浏览器打开网页")


def test_find_similar_skills():
    """相似技能检测：同一目标物的技能应被识别"""
    existing = {
        "open_notepad": {"description": "打开 Windows 记事本程序"},
        "calc": {"description": "数学计算"},
    }
    similar = skill_factory.find_similar_skills("打开记事本并写入文字", existing)
    assert "open_notepad" in similar
    assert "calc" not in similar
    # 无相似
    assert skill_factory.find_similar_skills("查天气", existing) == []


def test_strip_code_fence():
    """健壮提取：带解释文字+围栏 / 无围栏 / 语言标签"""
    # 围栏前有解释文字（之前失败的场景）
    raw = '根据您的需求，我为您生成了技能：\n\n```python\nimport subprocess\n\ndef open_notepad():\n    return "ok"\n```'
    code = skill_factory._strip_code_fence(raw)
    assert code.startswith("import subprocess")
    assert "def open_notepad" in code
    assert "根据您的需求" not in code

    # 无围栏，带语言标签行
    raw2 = 'python\nimport os\n\ndef x():\n    return "ok"'
    code2 = skill_factory._strip_code_fence(raw2)
    assert code2.startswith("import os")

    # 无围栏，开头是解释文字
    raw3 = '这是代码：\ndef hello():\n    return "hi"'
    code3 = skill_factory._strip_code_fence(raw3)
    assert code3.startswith("def hello")

    # 空输入
    assert skill_factory._strip_code_fence("") == ""


def test_suggest_upgrades_offline():
    """无 LLM 时能力推荐返回空列表（不阻塞创建）"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        r = skill_factory.suggest_skill_upgrades("open_notepad", "打开记事本", 'def open_notepad():\n    pass', {})
        assert r == []
        r = skill_factory.enhance_skill("open_notepad", 'def open_notepad():\n    pass', "追加写入", {})
        assert r is None
    finally:
        settings.api_key = old


def test_sandbox_test_good():
    """沙箱冒烟测试：正常技能通过，且外部调用被打桩不真正执行"""
    code = '''import subprocess

def demo(param: str = ''):
    try:
        subprocess.Popen(['notepad.exe'])
        return "已打开" + param
    except Exception as e:
        return "失败" + str(e)
'''
    r = skill_factory.sandbox_test(code)
    assert r["ok"], r
    assert len(r["returns"]) == 2
    assert "已打开" in r["returns"][0]
    assert "subprocess.Popen" in r["calls"]  # 打桩记录，未真正执行


def test_sandbox_test_broken():
    """沙箱冒烟测试：运行时错误被捕获"""
    code = '''def bad(param: str = ''):
    raise RuntimeError("模拟崩溃")
'''
    r = skill_factory.sandbox_test(code)
    assert not r["ok"]
    assert "模拟崩溃" in r["error"]


def test_sandbox_test_non_string_return():
    """返回值必须是字符串"""
    code = '''def bad(param: str = ''):
    return 123
'''
    r = skill_factory.sandbox_test(code)
    assert not r["ok"]
    assert "不是字符串" in r["error"]


def test_polish_offline():
    """无 LLM 且代码有问题 → polish 返回 None（不硬造）"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        bad = '''def broken(param: str = ''):
    raise RuntimeError("x")
'''
        code, rounds, log = skill_factory.polish_skill_code(bad, "测试", {}, max_rounds=1)
        assert code is None
        assert rounds == 0
    finally:
        settings.api_key = old


def test_polish_good_no_llm_needed():
    """代码本来就健康 → 不需要 LLM，直接通过"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        good = '''def ok(param: str = ''):
    return "结果" + param
'''
        code, rounds, log = skill_factory.polish_skill_code(good, "测试", {}, max_rounds=1)
        assert code is not None
        assert rounds == 0
    finally:
        settings.api_key = old


def test_parse_learning_fields():
    """学习技能三要素解析"""
    msg = "学习技能：材料：电脑记事本，学习内容：使用记事本，要学习到：完全掌握"
    fields = skill_factory.parse_learning_fields(msg)
    assert fields.get("material") == "电脑记事本"
    assert fields.get("content") == "使用记事本"
    assert fields.get("level") == "完全掌握"
    # 缺失字段不返回
    partial = skill_factory.parse_learning_fields("材料：电脑记事本")
    assert "material" in partial
    assert "content" not in partial
    assert "level" not in partial


def test_build_learning_description():
    """三要素 → 生成描述（含完整度要求）"""
    desc = skill_factory.build_learning_description("电脑记事本", "使用记事本", "完全掌握")
    assert "电脑记事本" in desc
    assert "使用记事本" in desc
    assert "完全掌握" in desc
    assert "开箱即用" in desc  # 完全掌握的要求
    # 未知名程度 → 默认完全掌握
    desc2 = skill_factory.build_learning_description("a", "b", "随便")
    assert "开箱即用" in desc2
    # 目标词提取：学习描述中能提取出"记事本"（用于相似技能检测）
    from core.skill_factory import extract_target
    assert extract_target(desc) == "记事本"


if __name__ == "__main__":
    test_templates_present()
    test_available_templates_by_capability()
    test_render_template_none()
    test_template_available_false()
    test_generate_offline_returns_none()
    test_validate_code()
    test_extract_skill_info()
    test_sanitize_filename()
    test_precheck_feasibility()
    test_extract_target()
    test_find_similar_skills()
    test_strip_code_fence()
    test_suggest_upgrades_offline()
    test_sandbox_test_good()
    test_sandbox_test_broken()
    test_sandbox_test_non_string_return()
    test_polish_offline()
    test_polish_good_no_llm_needed()
    test_parse_learning_fields()
    test_build_learning_description()
    print("✅ skill_factory 测试通过")
