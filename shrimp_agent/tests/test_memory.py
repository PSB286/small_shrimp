# -*- coding: utf-8 -*-
"""记忆测试：永久记忆 + 技能档案（skill_stats）"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_permanent_memory_basic():
    from memory.permanent_memory import PermanentMemory
    tmp = os.path.join(tempfile.mkdtemp(), "mem.json")
    try:
        mem = PermanentMemory(tmp)
        mem.set_user_name("小明")
        assert mem.get_user_name() == "小明"
        mem.set_preference("color", "蓝色")
        assert mem.get_preference("color") == "蓝色"
        mem.add_fact("主人每天7点起床")
        assert "主人每天7点起床" in mem.get_facts()
        # 技能档案
        mem.record_skill_result("walk", True)
        mem.record_skill_result("walk", True)
        mem.record_skill_result("walk", False, "舵机超时")
        stats = mem.get_skill_stats("walk")
        assert stats["count"] == 3
        assert stats["success"] == 2
        assert stats["failures"] == 1
        assert stats["consecutive_failures"] == 1
        assert "舵机超时" in stats["last_error"]
        # 持久化：重新加载
        mem2 = PermanentMemory(tmp)
        assert mem2.get_user_name() == "小明"
        assert mem2.get_skill_stats("walk")["count"] == 3
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)


def test_skill_stats_reset():
    from memory.permanent_memory import PermanentMemory
    tmp = os.path.join(tempfile.mkdtemp(), "mem.json")
    try:
        mem = PermanentMemory(tmp)
        mem.record_skill_result("dance", False, "x")
        mem.record_skill_result("dance", False, "x")
        assert mem.get_skill_stats("dance")["consecutive_failures"] == 2
        mem.reset_skill_stats("dance")
        assert mem.get_skill_stats("dance") == {}
    finally:
        shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)


def test_rule_preference_memorized():
    """'无需反复打开记事本' 这类规则要真正入库，不是口头说说"""
    from core.memory_integration import MemoryIntegration
    mem = MemoryIntegration()
    try:
        result = mem.process_user_input("无需反复打开记事本")
        assert result["memorized"] is True, result
        assert result["type"] == "preference"
        assert "反复打开记事本" in result["value"]
        prefs = mem.permanent.get_all_preferences()
        assert any("反复打开记事本" in v for v in prefs.values())
    finally:
        mem.permanent.clear_all()


if __name__ == "__main__":
    test_permanent_memory_basic()
    test_skill_stats_reset()
    test_rule_preference_memorized()
    print("✅ memory 测试通过")
