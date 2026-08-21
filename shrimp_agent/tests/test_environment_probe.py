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
    # 声明一个"机器狗"能力，验证三通道中的主动提供
    ok, msg = probe.update({
        "actuators": [
            {"id": "leg_fl", "type": "servo", "channel": 0},
            {"id": "leg_fr", "type": "servo", "channel": 1},
            {"id": "leg_bl", "type": "servo", "channel": 2},
            {"id": "leg_br", "type": "servo", "channel": 3},
            {"id": "tail", "type": "servo", "channel": 4},
        ],
        "display": {"type": "ssd1306"},
        "audio_in": {"type": "mic"},
    })
    assert ok, msg
    caps = probe.get_capabilities()
    assert len(caps.get("actuators", [])) == 5
    assert caps.get("display")
    assert caps.get("audio_in")


if __name__ == "__main__":
    test_probe_runs()
    test_capabilities_generated()
    test_update_roundtrip()
    print("✅ environment_probe 测试通过")
