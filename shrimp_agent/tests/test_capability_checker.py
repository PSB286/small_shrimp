# -*- coding: utf-8 -*-
"""能力约束校验测试：合法代码放行、越权代码拦截"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.capability_checker import CapabilityChecker

CAPS = {
    "actuators": [
        {"id": "tail", "type": "servo"},
        {"id": "leg_fl", "type": "servo"},
    ],
    "display": {"type": "ssd1306"},
    "libs": ["requests"],
}

GOOD = '''from hardware import hw

def wag():
    hw.servo("tail").set_angle(90)
    hw.display().show_emoji("😊")
    return "ok"

__skill_meta__ = {"description": "摇尾巴", "params": {}}
'''

BAD_SERVO = '''from hardware import hw

def x():
    hw.servo("unknown_leg").set_angle(90)
    return "ok"
'''

BAD_IMPORT = '''import flask

def x():
    return "ok"
'''

BAD_DISPLAY = '''from hardware import hw

def x():
    hw.display().show_emoji("x")
    return "ok"
'''

BAD_POSES = '''from hardware import hw

def x():
    hw.play_poses([{"ghost": 90}], interval=0.2)
    return "ok"
'''

SYNTAX_BAD = '''def x(:
    return "ok"
'''


def test_good_passes():
    r = CapabilityChecker(CAPS).check(GOOD)
    assert r["ok"], r


def test_unknown_servo_rejected():
    r = CapabilityChecker(CAPS).check(BAD_SERVO)
    assert not r["ok"]
    assert any("舵机" in v for v in r["violations"])


def test_forbidden_import_rejected():
    r = CapabilityChecker(CAPS).check(BAD_IMPORT)
    assert not r["ok"]
    assert any("导入" in v for v in r["violations"])


def test_display_requires_capability():
    caps_no_display = {"actuators": [{"id": "tail", "type": "servo"}]}
    r = CapabilityChecker(caps_no_display).check(BAD_DISPLAY)
    assert not r["ok"]
    assert any("屏幕" in v for v in r["violations"])


def test_pose_servo_rejected():
    r = CapabilityChecker(CAPS).check(BAD_POSES)
    assert not r["ok"]


def test_syntax_error():
    r = CapabilityChecker(CAPS).check(SYNTAX_BAD)
    assert not r["ok"]
    assert any("语法" in v for v in r["violations"])


if __name__ == "__main__":
    test_good_passes()
    test_unknown_servo_rejected()
    test_forbidden_import_rejected()
    test_display_requires_capability()
    test_pose_servo_rejected()
    test_syntax_error()
    print("✅ capability_checker 测试通过")
