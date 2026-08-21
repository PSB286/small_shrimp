"""
硬件抽象层 - 统一入口

技能代码统一这样使用：

    from hardware import hw

    hw.servo("tail").set_angle(90)      # 转动尾巴舵机
    hw.play_poses([...], interval=0.3)  # 播放动作序列
    hw.display().show_emoji("😊")       # 屏幕上做表情
    hw.mic().listen(3)                  # 收音
    hw.speaker().say("你好")            # 说话

hw 根据 data/capabilities.json 决定有哪些设备，以及使用
模拟后端还是真实后端（settings.hardware_mode: auto/sim/real）。
"""

import os

from config import settings
from utils.logger import logger

from hardware import simulator
from hardware import real
from hardware import motion


class Hardware:
    """按能力清单暴露硬件设备"""

    def __init__(self, capabilities=None, mode=None):
        self.capabilities = capabilities if capabilities is not None else self._load_capabilities()
        self.mode = mode or settings.hardware_mode
        self._servos = {}
        self._display = None
        self._mic = None
        self._speaker = None
        self.servo_ids = []
        self._build()

    # ---------- 构造 ----------

    def _load_capabilities(self):
        try:
            if os.path.exists(settings.capabilities_file):
                import json
                with open(settings.capabilities_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning("[Hardware] 读取能力清单失败: %s", e)
        return {}

    def _build(self):
        actuators = self.capabilities.get("actuators") or []
        for spec in actuators:
            if not isinstance(spec, dict) or not spec.get("id"):
                continue
            sid = spec["id"]
            self.servo_ids.append(sid)
            self._servos[sid] = self._make("servo", sid, spec)

        if self.capabilities.get("display"):
            self._display = self._make("display", "display", self.capabilities["display"])
        if self.capabilities.get("audio_in"):
            self._mic = self._make("mic", "mic", self.capabilities["audio_in"])
        if self.capabilities.get("audio_out"):
            self._speaker = self._make("speaker", "speaker", self.capabilities["audio_out"])

        logger.info(
            "[Hardware] 模式=%s 舵机=%s 屏幕=%s 麦克风=%s 喇叭=%s",
            self.mode, self.servo_ids,
            self._display is not None,
            self._mic is not None,
            self._speaker is not None,
        )

    def _make(self, kind, device_id, spec):
        use_real = self.mode == "real" or (
            self.mode == "auto" and real.available(kind)
        )
        if use_real:
            try:
                dev = real.make(kind, spec)
                logger.info("[Hardware] %s '%s' 使用真实驱动", kind, device_id)
                return dev
            except Exception as e:
                logger.warning("[Hardware] %s '%s' 真实驱动初始化失败，退回模拟: %s",
                               kind, device_id, e)
        return simulator.SimServo(device_id, spec) if kind == "servo" else \
               simulator.SimDisplay(spec) if kind == "display" else \
               simulator.SimMicrophone(spec) if kind == "mic" else \
               simulator.SimSpeaker(spec)

    # ---------- 设备访问 ----------

    def servo(self, servo_id):
        dev = self._servos.get(servo_id)
        if dev is None:
            raise ValueError(
                "未知舵机 '%s'，本环境可用舵机: %s" % (servo_id, self.servo_ids or "无")
            )
        return dev

    def display(self):
        if self._display is None:
            raise ValueError("本环境没有屏幕设备")
        return self._display

    def mic(self):
        if self._mic is None:
            raise ValueError("本环境没有麦克风设备")
        return self._mic

    def speaker(self):
        if self._speaker is None:
            raise ValueError("本环境没有喇叭设备")
        return self._speaker

    # ---------- 动作 ----------

    def play_poses(self, poses, interval=0.3):
        """播放姿态序列（跑/跳舞/摇尾巴 都是它）"""
        return motion.play_poses(self, poses, interval)

    # ---------- 状态 ----------

    def state(self):
        """返回当前硬件状态（模拟后端有完整状态，真实后端尽量返回）"""
        return simulator.get_state()


# ---------- 单例 ----------

_hw = None


def get_hardware():
    """获取硬件单例（按能力清单构建）"""
    global _hw
    if _hw is None:
        _hw = Hardware()
    return _hw


def reload_hardware():
    """能力清单变化后重建硬件单例"""
    global _hw
    _hw = Hardware()
    return _hw


# 模块导入即构建（技能模块 import hardware 时 hw 必须可用）
hw = get_hardware()
