# -*- coding: utf-8 -*-
"""技能工厂测试（最简状态）：模板库为空、LLM 路径、校验、名称清洗"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import skill_factory
from config import settings
from templates.skill_templates import TEMPLATES, list_templates


def test_templates_empty():
    """最简状态：不预置任何技能模板"""
    assert TEMPLATES == {}
    assert list_templates() == {}


def test_available_templates_empty():
    names = skill_factory.available_templates({})
    assert names == []


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


if __name__ == "__main__":
    test_templates_empty()
    test_available_templates_empty()
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
    print("✅ skill_factory 测试通过")
