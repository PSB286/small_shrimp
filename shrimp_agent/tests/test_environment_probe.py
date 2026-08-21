# -*- coding: utf-8 -*-
"""环境探测测试：探测器、能力清单生成、手动修正"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.environment_probe import EnvironmentProbe


def test_probe_runs():
    probe = EnvironmentProbe()
    result = probe.run_probes()
    assert "platform" in result
    assert result["platform"]["available"] is True
    assert "network" in result
    assert isinstance(result["network"]["available"], bool)
    assert isinstance(result["libs"]["detail"], dict)


def test_platform_driven_probes():
    """平台驱动：Windows/macOS 不探测 I2C/GPIO/OLED，Linux 才探测"""
    import platform as _platform
    probe = EnvironmentProbe()
    result = probe.run_probes()
    if _platform.system() == "Linux":
        assert "i2c" in result
        assert "gpio" in result
        assert "servo_board" in result
        assert "display" in result
    else:
        assert "i2c" not in result
        assert "gpio" not in result
        assert "servo_board" not in result
        assert "display" not in result
    # 通用能力任何平台都要探测
    assert "mic" in result
    assert "camera" in result


def test_capabilities_generated():
    probe = EnvironmentProbe()
    caps = probe.get_capabilities()
    assert isinstance(caps, dict)
    assert "source" in caps
    assert "network" in caps
    assert "libs" in caps
    assert isinstance(caps.get("actuators", []), list)


def test_update_roundtrip():
    probe = EnvironmentProbe()
    ok, msg = probe.update({"network": True})
    assert ok, msg
    caps = probe.get_capabilities()
    assert caps.get("network") is True
    # 通道③ 界面修正：声明环境能力（如"有一块屏幕"）
    ok, msg = probe.update({"display": {"type": "display"}})
    assert ok, msg
    caps = probe.get_capabilities()
    assert caps.get("display")


if __name__ == "__main__":
    test_probe_runs()
    test_platform_driven_probes()
    test_capabilities_generated()
    test_update_roundtrip()
    print("✅ environment_probe 测试通过")
