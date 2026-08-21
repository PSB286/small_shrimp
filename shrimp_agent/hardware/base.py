"""
硬件抽象层 - 设备接口定义（基类）

技能代码只依赖这些接口，不依赖具体硬件实现。
模拟后端与真实后端都实现同一接口，可以无缝切换。
"""


class ServoDevice:
    """舵机接口"""

    def set_angle(self, angle, speed=0):
        """设置目标角度（度）。speed=0 表示立即到位，否则按 deg/sec 匀速。"""
        raise NotImplementedError

    def get_angle(self):
        """获取当前角度（度）"""
        raise NotImplementedError


class DisplayDevice:
    """屏幕接口（当作"脸"）"""

    def text(self, lines):
        """显示多行文本，lines 为字符串列表"""
        raise NotImplementedError

    def show_emoji(self, emoji):
        """显示一个大表情符号"""
        raise NotImplementedError

    def clear(self):
        """清屏"""
        raise NotImplementedError


class MicrophoneDevice:
    """麦克风接口"""

    def listen(self, seconds=3):
        """录音 seconds 秒，返回音频字节；失败返回 None"""
        raise NotImplementedError


class SpeakerDevice:
    """喇叭接口（语音合成）"""

    def say(self, text):
        """把 text 合成语音播放，返回结果描述字符串"""
        raise NotImplementedError
