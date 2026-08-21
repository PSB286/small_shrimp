# -*- coding: utf-8 -*-
"""硬件抽象层测试：模拟舵机/屏幕/动作序列"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hardware import simulator
from hardware.simulator import SimServo, SimDisplay


def test_servo_basic():
    servo = SimServo("test_tail", {"min": 0, "max": 180})
    servo.set_angle(90)
    assert servo.get_angle() == 90
    # 超量程必须拒绝
    try:
        servo.set_angle(200)
        assert False, "超量程应该抛异常"
    except ValueError:
        pass
    try:
        servo.set_angle(-10)
        assert False, "低于量程应该抛异常"
    except ValueError:
        pass


def test_servo_speed_no_crash():
    servo = SimServo("test_leg", {"min": 0, "max": 180})
    servo.set_angle(0)
    servo.set_angle(90, speed=360)  # 0.25 秒模拟耗时
    assert servo.get_angle() == 90


def test_display_emoji():
    d = SimDisplay({})
    d.show_emoji("😊")
    assert simulator.SIM_STATE["emoji"] == "😊"
    d.text(["line1", "line2"])
    assert simulator.SIM_STATE["display"] == ["line1", "line2"]
    assert simulator.SIM_STATE["emoji"] == ""
    d.clear()
    assert simulator.SIM_STATE["display"] == []


def test_play_poses():
    from hardware import Hardware
    caps = {
        "actuators": [
            {"id": "leg_fl", "type": "servo"},
            {"id": "leg_fr", "type": "servo"},
        ],
    }
    hw = Hardware(caps, mode="sim")
    poses = [
        {"leg_fl": 45, "leg_fr": 90},
        {"leg_fl": 90, "leg_fr": 45},
    ]
    steps = hw.play_poses(poses, interval=0)
    assert steps == 2
    assert hw.servo("leg_fl").get_angle() == 90

    # 未知舵机必须报错
    try:
        hw.play_poses([{"ghost": 90}], interval=0)
        assert False, "未知舵机应该报错"
    except ValueError:
        pass


if __name__ == "__main__":
    test_servo_basic()
    test_servo_speed_no_crash()
    test_display_emoji()
    test_play_poses()
    print("✅ hardware 测试通过")
