"""
硬件抽象层 - 真实驱动后端（按需加载）

所有真实驱动都是"懒加载 + 缺失降级"：
- 对应库未安装 → available() 返回 False，Hardware 自动退回模拟后端
- 对应库已安装但硬件不在 → 构造/调用时抛异常，由上层捕获

当前支持：
- 舵机: PCA9685 (smbus2)
- 屏幕: SSD1306 OLED (luma.oled)
- 麦克风: pyaudio
- 喇叭: 预留接口（TTS 引擎可插拔）
"""

import importlib.util


REAL_MODULES = {
    "servo": "smbus2",
    "display": "luma.oled",
    "mic": "pyaudio",
    "speaker": None,  # 喇叭暂无真实后端，始终用模拟
}


def available(kind):
    """检查某类硬件的驱动库是否可用（find_spec 对带父包的模块可能抛异常，必须兜底）"""
    mod = REAL_MODULES.get(kind)
    if not mod:
        return False
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


class RealServo:
    """PCA9685 舵机驱动（16 通道 PWM 板）"""

    def __init__(self, servo_id, spec):
        self.id = servo_id
        self.spec = spec or {}
        self.channel = int(self.spec.get("channel", 0))
        self.min = float(self.spec.get("min", 0))
        self.max = float(self.spec.get("max", 180))
        self._angle = None
        self._board = None
        self._open()

    def _open(self):
        import smbus2
        bus = smbus2.SMBus(1)
        # PCA9685 默认地址 0x40
        self._board = _PCA9685(bus, 0x40)
        self._board.set_pwm_freq(50)

    def set_angle(self, angle, speed=0):
        angle = float(angle)
        if not (self.min <= self.max):
            raise ValueError("量程配置错误")
        # 把 0-180 度映射到 0.5ms-2.5ms 脉宽（50Hz 下 0-4096）
        pulse = 102 + int((angle / 180.0) * 410)
        self._board.set_pwm(self.channel, 0, pulse)
        self._angle = angle
        return angle

    def get_angle(self):
        return self._angle


class _PCA9685:
    """PCA9685 最小实现（模式1 + 频率 + PWM）"""

    def __init__(self, bus, addr):
        self.bus = bus
        self.addr = addr
        self._write(0x00, 0x00)  # 模式1: 睡眠关闭，启用自动递增

    def _write(self, reg, value):
        self.bus.write_byte_data(self.addr, reg, value)

    def set_pwm_freq(self, freq_hz):
        prescale = int(round(25000000.0 / (4096 * freq_hz))) - 1
        oldmode = self.bus.read_byte_data(self.addr, 0x00)
        self._write(0x00, (oldmode & 0x7F) | 0x10)  # 睡眠
        self._write(0xFE, prescale)
        self._write(0x00, oldmode)
        self._write(0x00, oldmode | 0x80)  # 重启

    def set_pwm(self, channel, on, off):
        reg = 0x06 + channel * 4
        self._write(reg, on & 0xFF)
        self._write(reg + 1, (on >> 8) & 0xFF)
        self._write(reg + 2, off & 0xFF)
        self._write(reg + 3, (off >> 8) & 0xFF)


class RealDisplay:
    """SSD1306 OLED 屏幕驱动（luma.oled）"""

    def __init__(self, spec):
        self.spec = spec or {}
        from luma.core.interface.serial import i2c
        from luma.oled.device import ssd1306
        self.device = ssd1306(i2c(port=1, address=0x3C))
        self.font_size = 16

    def text(self, lines):
        from PIL import Image, ImageDraw, ImageFont
        image = Image.new("1", (self.device.width, self.device.height))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        y = 0
        for line in lines:
            draw.text((0, y), line, fill=255, font=font)
            y += self.font_size
        self.device.display(image)
        return lines

    def show_emoji(self, emoji):
        # OLED 无彩色表情支持，转成文本
        return self.text([emoji])

    def clear(self):
        self.device.clear()
        return True


class RealMicrophone:
    """麦克风录音驱动（pyaudio）"""

    def __init__(self, spec):
        self.spec = spec or {}
        import pyaudio
        self.audio = pyaudio.PyAudio()

    def listen(self, seconds=3):
        import pyaudio
        stream = self.audio.open(
            format=pyaudio.paInt16, channels=1, rate=16000,
            input=True, frames_per_buffer=1024,
        )
        frames = []
        for _ in range(int(16000 / 1024 * seconds)):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
        stream.stop_stream()
        stream.close()
        return b"".join(frames)


class RealSpeaker:
    """喇叭驱动（预留：TTS 引擎可插拔）"""

    def __init__(self, spec):
        self.spec = spec or {}

    def say(self, text):
        return "[未配置TTS引擎] %s" % text


def make(kind, spec):
    """按类型构造真实设备；驱动缺失时抛 ImportError"""
    if kind == "servo":
        return RealServo(spec.get("id", "servo"), spec)
    if kind == "display":
        return RealDisplay(spec)
    if kind == "mic":
        return RealMicrophone(spec)
    if kind == "speaker":
        return RealSpeaker(spec)
    raise ValueError("未知硬件类型: %s" % kind)
