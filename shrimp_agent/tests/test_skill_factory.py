# -*- coding: utf-8 -*-
"""技能工厂测试：模板可用性、占位符渲染、离线兜底生成"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import skill_factory
from config import settings

# 机器狗能力：4腿+1尾+屏幕
DOG_CAPS = {
    "actuators": [
        {"id": "leg_fl", "type": "servo"},
        {"id": "leg_fr", "type": "servo"},
        {"id": "leg_bl", "type": "servo"},
        {"id": "leg_br", "type": "servo"},
        {"id": "tail", "type": "servo"},
    ],
    "display": {"type": "ssd1306"},
}

# 仅一个舵机的简化环境
MINI_CAPS = {"actuators": [{"id": "tail", "type": "servo"}]}


def test_template_availability():
    names = skill_factory.available_templates(DOG_CAPS)
    assert "servo_test" in names
    assert "wag_tail" in names
    assert "walk" in names
    assert "dance" in names
    assert "show_face" in names
    assert "listen" not in names  # 没有麦克风


def test_mini_env_no_walk():
    names = skill_factory.available_templates(MINI_CAPS)
    assert "walk" not in names  # 舵机不足 4 个不能走
    assert "wag_tail" in names


def test_render_wag_tail():
    code = skill_factory.render_template("wag_tail", DOG_CAPS)
    assert "hw.servo('tail')" in code
    assert "set_angle(120)" in code
    # 渲染结果必须能通过校验
    check = skill_factory.validate_code(code, DOG_CAPS)
    assert check["ok"], check


def test_render_walk():
    code = skill_factory.render_template("walk", DOG_CAPS)
    for leg in ("leg_fl", "leg_fr", "leg_bl", "leg_br"):
        assert leg in code
    check = skill_factory.validate_code(code, DOG_CAPS)
    assert check["ok"], check


def test_generate_fallback_template():
    """无 LLM 时按关键词走模板路径"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        result = skill_factory.generate_skill("摇尾巴", DOG_CAPS, max_rounds=1)
        assert result is not None
        code, name, desc, msgs = result
        assert name == "wag_tail"
        assert "wag" in code
    finally:
        settings.api_key = old


def test_generate_fallback_default():
    """无匹配关键词 → 兜底生成 servo_test"""
    old = settings.api_key
    settings.api_key = "sk-xxx"
    try:
        result = skill_factory.generate_skill("随便什么不匹配的需求", MINI_CAPS, max_rounds=1)
        assert result is not None
        assert result[1] == "servo_test"
    finally:
        settings.api_key = old


def test_validate_rejects_bad():
    bad = "def x(:\n    return"
    check = skill_factory.validate_code(bad, DOG_CAPS)
    assert not check["ok"]


if __name__ == "__main__":
    test_template_availability()
    test_mini_env_no_walk()
    test_render_wag_tail()
    test_render_walk()
    test_generate_fallback_template()
    test_generate_fallback_default()
    test_validate_rejects_bad()
    print("✅ skill_factory 测试通过")
