# -*- coding: utf-8 -*-
"""
能力模板库 - 无 LLM 也能生成基础技能

模板代码使用 @TOKEN@ 占位符，由 skill_factory 按能力清单填充：
  @SERVO_IDS@  全部舵机 id 列表，如 ['leg_fl','tail']
  @TAIL_SERVO@ 尾巴舵机 id（id 含 tail/尾，否则取第一个舵机）
  @LEG0@~@LEG3@ 按顺序取 4 个舵机 id（腿/全部舵机）
  @DESC@       技能描述

每份模板声明 requires：满足才可用。
代码全部走 hardware 抽象层，因此同时可跑在模拟器与真实硬件上。
"""

SERVO_TEST = """from hardware import hw
import time

def servo_test(param: str = ''):
    \"\"\"@DESC@\"\"\"
    servos = ['@SERVO_IDS@']
    if not servos:
        return '本环境没有任何舵机'
    result = []
    for sid in servos:
        servo = hw.servo(sid)
        servo.set_angle(0)
        time.sleep(0.2)
        servo.set_angle(90)
        time.sleep(0.2)
        servo.set_angle(180)
        time.sleep(0.2)
        servo.set_angle(90)
        time.sleep(0.2)
        result.append('%s 测试完成' % sid)
    return '舵机测试完成: ' + ', '.join(result)

__skill_meta__ = {
    "description": "@DESC@",
    "params": {},
    "tier": 1,
    "safe": True
}
"""

SHOW_FACE = """from hardware import hw

def show_face(param: str = ''):
    \"\"\"@DESC@\"\"\"
    face = param or '😊'
    hw.display().show_emoji(face)
    return '屏幕上显示了 %s' % face

__skill_meta__ = {
    "description": "@DESC@",
    "params": {"param": "要显示的表情，如 😊 🐶"},
    "tier": 1,
    "safe": True
}
"""

WAG_TAIL = """from hardware import hw
import time

def wag_tail(param: str = ''):
    \"\"\"@DESC@\"\"\"
    tail = hw.servo('@TAIL_SERVO@')
    times = 4
    for i in range(times):
        tail.set_angle(30)
        time.sleep(0.2)
        tail.set_angle(120)
        time.sleep(0.2)
    return '尾巴摇了 %d 下' % times

__skill_meta__ = {
    "description": "@DESC@",
    "params": {},
    "tier": 1,
    "safe": True
}
"""

WALK = """from hardware import hw
import time

def walk(param: str = ''):
    \"\"\"@DESC@\"\"\"
    # 四足对角小跑步态：对角腿同起同落
    poses = [
        {'@LEG0@': 60, '@LEG2@': 60, '@LEG1@': 30, '@LEG3@': 30},
        {'@LEG0@': 30, '@LEG2@': 30, '@LEG1@': 60, '@LEG3@': 60},
        {'@LEG0@': 60, '@LEG2@': 60, '@LEG1@': 30, '@LEG3@': 30},
        {'@LEG0@': 30, '@LEG2@': 30, '@LEG1@': 60, '@LEG3@': 60},
    ]
    steps = hw.play_poses(poses, interval=0.25)
    return '向前走了 %d 步' % (steps * 2)

__skill_meta__ = {
    "description": "@DESC@",
    "params": {},
    "tier": 1,
    "safe": True
}
"""

DANCE = """from hardware import hw
import time

def dance(param: str = ''):
    \"\"\"@DESC@\"\"\"
    poses = [
        {'@SERVO0@': 90, '@SERVO1@': 90, '@SERVO2@': 90, '@SERVO3@': 90, '@SERVO4@': 90},
        {'@SERVO0@': 45, '@SERVO1@': 135, '@SERVO2@': 45, '@SERVO3@': 135, '@SERVO4@': 45},
        {'@SERVO0@': 135, '@SERVO1@': 45, '@SERVO2@': 135, '@SERVO3@': 45, '@SERVO4@': 135},
        {'@SERVO0@': 90, '@SERVO1@': 90, '@SERVO2@': 90, '@SERVO3@': 90, '@SERVO4@': 90},
        {'@SERVO0@': 60, '@SERVO1@': 120, '@SERVO2@': 60, '@SERVO3@': 120, '@SERVO4@': 60},
        {'@SERVO0@': 120, '@SERVO1@': 60, '@SERVO2@': 120, '@SERVO3@': 60, '@SERVO4@': 120},
        {'@SERVO0@': 90, '@SERVO1@': 90, '@SERVO2@': 90, '@SERVO3@': 90, '@SERVO4@': 90},
    ]
    hw.play_poses(poses, interval=0.3)
    return '跳了一支舞 💃'

__skill_meta__ = {
    "description": "@DESC@",
    "params": {},
    "tier": 1,
    "safe": True
}
"""

LISTEN = """from hardware import hw

def listen(param: str = ''):
    \"\"\"@DESC@\"\"\"
    seconds = 3
    audio = hw.mic().listen(seconds)
    if audio is None:
        return '已开始收音 %d 秒（当前环境未配置语音识别，暂时无法转成文字）' % seconds
    return '已录音 %d 秒，音频长度 %d 字节' % (seconds, len(audio))

__skill_meta__ = {
    "description": "@DESC@",
    "params": {},
    "tier": 1,
    "safe": True
}
"""


TEMPLATES = {
    "servo_test": {
        "description": "测试所有舵机：逐个从0°到180°转动",
        "requires": ["actuators"],
        "code": SERVO_TEST,
    },
    "show_face": {
        "description": "在屏幕上显示表情",
        "requires": ["display"],
        "code": SHOW_FACE,
    },
    "wag_tail": {
        "description": "摇尾巴：左右摆动尾巴舵机",
        "requires": ["actuators"],
        "code": WAG_TAIL,
    },
    "walk": {
        "description": "向前行走：四足对角小跑步态",
        "requires": ["actuators>=4"],
        "code": WALK,
    },
    "dance": {
        "description": "跳舞：播放一组姿态序列",
        "requires": ["actuators>=3"],
        "code": DANCE,
    },
    "listen": {
        "description": "收音：录制环境声音",
        "requires": ["audio_in"],
        "code": LISTEN,
    },
}


def list_templates():
    """返回模板名+描述"""
    return {name: t["description"] for name, t in TEMPLATES.items()}


def get_template(name):
    return TEMPLATES.get(name)
