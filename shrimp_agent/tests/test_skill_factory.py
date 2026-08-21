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


if __name__ == "__main__":
    test_templates_empty()
    test_available_templates_empty()
    test_render_template_none()
    test_template_available_false()
    test_generate_offline_returns_none()
    test_validate_code()
    test_extract_skill_info()
    test_sanitize_filename()
    print("✅ skill_factory 测试通过")
