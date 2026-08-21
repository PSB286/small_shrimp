"""
环境探测 - 三通道合一（平台驱动）

通道① 主动提供: environment.json（部署者声明硬件，优先级最高）
通道② 自动探测: 先探测平台，再按平台选择"必要能力"探测器
                （Windows/macOS 不查 I2C/GPIO/OLED；Linux 才查硬件接口）
通道③ 界面修正: /environment 接口查看/修改后写回

所有探测结果汇总为 data/capabilities.json —— 技能生成、
能力校验、硬件抽象层全部以它为唯一事实来源。

降级原则：探测到什么算什么，绝不因探测失败崩溃。
最小能力集 = 纯文本聊天 + 记忆。
"""

import importlib.util
import json
import os
import platform
import socket
from datetime import datetime

from config import settings
from utils.logger import logger


# ==================== 简单探测器 ====================

def _importable(module_name):
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def probe_platform():
    return {"available": True, "detail": "%s / Python %s" % (platform.system(), platform.python_version())}


def probe_network():
    try:
        sock = socket.create_connection(("8.8.8.8", 53), timeout=2)
        sock.close()
        return {"available": True, "detail": "可联网"}
    except Exception:
        return {"available": False, "detail": "离线环境"}


def probe_i2c():
    if os.name != "posix":
        return {"available": False, "detail": "非Linux，无I2C总线"}
    try:
        import glob
        devices = glob.glob("/dev/i2c-*")
        return {"available": bool(devices), "detail": "I2C总线: %s" % (devices or "无")}
    except Exception as e:
        return {"available": False, "detail": str(e)}


def probe_gpio():
    if _importable("RPi.GPIO"):
        return {"available": True, "detail": "RPi.GPIO 可用"}
    return {"available": False, "detail": "未安装 RPi.GPIO"}


def probe_servo_board():
    if _importable("smbus2") and probe_i2c()["available"]:
        return {"available": True, "detail": "PCA9685 舵机板可用 (smbus2 + I2C)"}
    return {"available": False, "detail": "无舵机板驱动 (smbus2/I2C)"}


def probe_display():
    if _importable("luma.oled"):
        return {"available": True, "detail": "SSD1306 OLED (luma.oled)"}
    return {"available": False, "detail": "未安装 luma.oled"}


def probe_mic():
    if _importable("pyaudio"):
        return {"available": True, "detail": "pyaudio 可用"}
    if os.name == "posix" and os.path.exists("/dev/snd"):
        return {"available": True, "detail": "检测到 /dev/snd 音频设备"}
    return {"available": False, "detail": "未安装 pyaudio"}


def probe_camera():
    if _importable("picamera") or _importable("cv2"):
        return {"available": True, "detail": "摄像头库可用"}
    return {"available": False, "detail": "无摄像头库"}


def probe_libs():
    """探测对技能生成有意义的第三方库（随平台自动适配）"""
    names = ["requests", "PIL", "numpy", "cv2", "pygame", "pypinyin"]
    if os.name == "posix":
        # Linux/树莓派相关的硬件库
        names += ["smbus2", "luma.oled", "pyaudio", "RPi.GPIO", "picamera"]
    else:
        # Windows/macOS 桌面相关
        names += ["pyaudio", "pyautogui", "psutil"]
    return {name: _importable(name) for name in names}


# ==================== 平台驱动的探测器清单 ====================

# 各探测器适用的平台；不在列表中的探测器 = 全平台通用
PROBE_PLATFORMS = {
    "i2c": ["Linux"],          # I2C 总线只有 Linux 才有
    "gpio": ["Linux"],         # RPi.GPIO 仅树莓派
    "servo_board": ["Linux"],  # PCA9685 舵机板走 I2C
    "display": ["Linux"],      # SSD1306 OLED 走 I2C
}

PROBES = {
    "platform": probe_platform,
    "network": probe_network,
    "i2c": probe_i2c,
    "gpio": probe_gpio,
    "servo_board": probe_servo_board,
    "display": probe_display,
    "mic": probe_mic,
    "camera": probe_camera,
}


def applicable_probes():
    """根据当前平台返回应运行的探测器名列表"""
    system = platform.system()
    return [
        name for name in PROBES
        if name not in PROBE_PLATFORMS or system in PROBE_PLATFORMS[name]
    ]


# ==================== 探测 → 能力清单 ====================

def _capabilities_from_probes(probes, libs):
    """
    由探测结果生成能力清单（最简状态）：
    只保留探测到的通用能力，不做任何默认硬件假设。
    需要舵机/屏幕等具体硬件时，通过 environment.json 主动提供。
    """
    caps = {
        "source": "probe",
        "platform": probes.get("platform", {}).get("detail", platform.system()),
        "python": platform.python_version(),
        "network": probes.get("network", {}).get("available", False),
        "libs": [name for name, ok in libs.items() if ok],
        "probed_at": datetime.now().isoformat(timespec="seconds"),
    }
    if probes.get("display", {}).get("available"):
        caps["display"] = {"type": "display"}
    if probes.get("mic", {}).get("available"):
        caps["audio_in"] = {"type": "mic"}
    if probes.get("camera", {}).get("available"):
        caps["camera"] = {"type": "camera"}
    return caps


# ==================== 环境探测类 ====================

class EnvironmentProbe:
    def __init__(self, capabilities_file=None, manifest_file=None):
        self.capabilities_file = capabilities_file or settings.capabilities_file
        self.manifest_file = manifest_file or settings.environment_manifest
        self.probes = {}

    # ---- 通道②: 自动探测 ----

    def run_probes(self):
        """
        平台驱动的自动探测：
        先探平台，再按平台只跑"必要能力"探测器（见 applicable_probes）
        """
        self.probes = {}
        names = applicable_probes()
        logger.info("[Probe] 平台=%s，运行探测器: %s", platform.system(), names)
        for name in names:
            fn = PROBES[name]
            try:
                self.probes[name] = fn()
            except Exception as e:
                self.probes[name] = {"available": False, "detail": "探测异常: %s" % e}
        self.probes["libs"] = {"available": True, "detail": probe_libs()}
        return self.probes

    # ---- 通道①: 主动提供 ----

    def load_manifest(self):
        """读取部署者提供的 environment.json（存在则优先）"""
        if not os.path.exists(self.manifest_file):
            return None
        try:
            with open(self.manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            if isinstance(manifest, dict) and manifest:
                logger.info("[Probe] 使用主动提供的环境清单: %s", self.manifest_file)
                return manifest
        except Exception as e:
            logger.warning("[Probe] 环境清单解析失败: %s", e)
        return None

    # ---- 汇总 ----

    def get_capabilities(self):
        """三通道合一，返回能力清单 dict"""
        manifest = self.load_manifest()
        if manifest:
            caps = dict(manifest)
            caps.setdefault("source", "manifest")
            caps.setdefault("probed_at", datetime.now().isoformat(timespec="seconds"))
            if "libs" not in caps:
                caps["libs"] = probe_libs()
            return caps

        if not self.probes:
            self.run_probes()
        libs = self.probes.get("libs", {}).get("detail", {})
        if isinstance(libs, dict):
            libs = probe_libs() if not libs else libs
        caps = _capabilities_from_probes(self.probes, libs)
        # 兼容旧文件：若已有 capabilities.json，保留其中的手动配置
        caps = self._merge_saved(caps)
        return caps

    def _merge_saved(self, caps):
        """把已保存能力清单中的手动配置合入（以已保存的为准）"""
        if not os.path.exists(self.capabilities_file):
            return caps
        try:
            with open(self.capabilities_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for key in ("actuators", "display", "audio_in", "audio_out"):
                if key in saved:
                    caps[key] = saved[key]
        except Exception:
            pass
        return caps

    def ensure_capabilities(self):
        """探测并保存能力清单，返回 caps。首次运行必调。"""
        caps = self.get_capabilities()
        self.save(caps)
        return caps

    def save(self, caps):
        os.makedirs(os.path.dirname(self.capabilities_file), exist_ok=True)
        with open(self.capabilities_file, "w", encoding="utf-8") as f:
            json.dump(caps, f, ensure_ascii=False, indent=2)
        logger.info("[Probe] 能力清单已保存: %s", self.capabilities_file)
        return True

    def update(self, partial):
        """通道③: 界面修正。partial 中的字段覆盖保存，非法字段忽略。"""
        if not isinstance(partial, dict):
            return False, "参数必须是对象"
        try:
            if os.path.exists(self.capabilities_file):
                with open(self.capabilities_file, "r", encoding="utf-8") as f:
                    caps = json.load(f)
            else:
                caps = self.get_capabilities()
        except Exception:
            caps = self.get_capabilities()

        allowed = {"actuators", "display", "audio_in", "audio_out", "network", "platform"}
        changed = []
        for key in allowed:
            if key in partial:
                caps[key] = partial[key]
                changed.append(key)
        caps["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.save(caps)
        return True, "已更新: %s" % (", ".join(changed) if changed else "无有效字段")
