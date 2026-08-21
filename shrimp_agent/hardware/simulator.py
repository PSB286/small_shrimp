"""
硬件抽象层 - PC 模拟后端

没有真实硬件时使用：虚拟舵机/虚拟屏幕/虚拟麦克风。
所有状态存在 SIM_STATE 里，可通过 /hardware/state 接口查看，
也可以被自优化循环当作"dry-run 场地"。
"""

import time
from datetime import datetime

from hardware.base import ServoDevice, DisplayDevice, MicrophoneDevice, SpeakerDevice

# 模拟状态存储（模块级，便于 UI/测试读取）
SIM_STATE = {
    "servos": {},        # id -> {"angle": float, "history": [{"angle":..,"t":..}]}
    "display": [],       # 当前显示的行
    "emoji": "",
    "mic": [],           # 录音记录
    "speaker": [],       # 合成过的文本
    "motion_log": [],    # 动作序列日志
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


class SimServo(ServoDevice):
    def __init__(self, servo_id, spec):
        self.id = servo_id
        self.spec = spec or {}
        self.min = self.spec.get("min", 0)
        self.max = self.spec.get("max", 180)
        SIM_STATE["servos"].setdefault(self.id, {"angle": None, "history": []})

    def set_angle(self, angle, speed=0):
        angle = float(angle)
        # 超量程直接拒绝，模拟真实舵机的保护
        if not (self.min <= angle <= self.max):
            raise ValueError(
                "角度 %.1f 超出 %s 的量程 [%s, %s]" % (angle, self.id, self.min, self.max)
            )
        state = SIM_STATE["servos"][self.id]
        if speed and speed > 0:
            cur = state["angle"]
            if cur is not None:
                # 模拟匀速转动耗时
                duration = abs(angle - cur) / float(speed)
                time.sleep(min(duration, 2.0))  # 上限 2 秒，避免卡死
        state["angle"] = angle
        state["history"].append({"angle": angle, "t": _now()})
        return angle

    def get_angle(self):
        return SIM_STATE["servos"][self.id]["angle"]


class SimDisplay(DisplayDevice):
    def __init__(self, spec):
        self.spec = spec or {}

    def text(self, lines):
        SIM_STATE["display"] = list(lines)
        SIM_STATE["emoji"] = ""
        return lines

    def show_emoji(self, emoji):
        SIM_STATE["emoji"] = emoji
        SIM_STATE["display"] = [emoji]
        return emoji

    def clear(self):
        SIM_STATE["display"] = []
        SIM_STATE["emoji"] = ""
        return True


class SimMicrophone(MicrophoneDevice):
    def __init__(self, spec):
        self.spec = spec or {}

    def listen(self, seconds=3):
        SIM_STATE["mic"].append({"seconds": seconds, "t": _now()})
        # 模拟环境没有真实音频，返回空
        return None


class SimSpeaker(SpeakerDevice):
    def __init__(self, spec):
        self.spec = spec or {}

    def say(self, text):
        SIM_STATE["speaker"].append({"text": text, "t": _now()})
        return "[模拟语音] %s" % text


def get_state():
    """返回模拟状态（供调试/UI）"""
    return {
        "mode": "sim",
        "servos": {k: {"angle": v["angle"]} for k, v in SIM_STATE["servos"].items()},
        "display": list(SIM_STATE["display"]),
        "emoji": SIM_STATE["emoji"],
        "mic_recordings": len(SIM_STATE["mic"]),
        "spoken": list(SIM_STATE["speaker"]),
        "motion_log": list(SIM_STATE["motion_log"]),
    }
