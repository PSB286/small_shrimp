# -*- coding: utf-8 -*-
"""技能管理器测试：加载/执行/tier 读取"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings


def test_load_and_execute():
    tmp = tempfile.mkdtemp()
    old = settings.skills_dir
    settings.skills_dir = tmp
    try:
        with open(os.path.join(tmp, "hello.py"), "w", encoding="utf-8") as f:
            f.write('''def hello(param=""):
    return "你好 " + param

__skill_meta__ = {"description": "打招呼", "params": {}, "tier": 2}
''')
        from core.skill_manager import SkillManager
        mgr = SkillManager()
        assert mgr.skill_exists("hello")
        assert mgr.get_skill_tier("hello") == 2
        result = mgr.execute("hello", {"param": "小虾米"})
        assert "你好 小虾米" in result
        assert "hello" in mgr.get_skills_info()
        assert mgr.skill_exists("not_exist") is False
    finally:
        settings.skills_dir = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_load_skips_bad_file():
    tmp = tempfile.mkdtemp()
    old = settings.skills_dir
    settings.skills_dir = tmp
    try:
        with open(os.path.join(tmp, "broken.py"), "w", encoding="utf-8") as f:
            f.write("这是非法 Python 代码 ((((")
        from core.skill_manager import SkillManager
        mgr = SkillManager()
        # 坏文件被跳过，不崩溃（文件仍在磁盘上，但未加载进技能字典）
        assert "broken" not in mgr.skills
        assert mgr.execute("broken", {}) != None  # 执行时明确报不存在
        assert mgr.skill_exists("broken") is True  # 文件存在即算存在（便于开关/删除）
    finally:
        settings.skills_dir = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_toggle_skill_roundtrip():
    """开关技能：禁用后能从列表看到 enabled=False，再启用可恢复"""
    tmp = tempfile.mkdtemp()
    old = settings.skills_dir
    settings.skills_dir = tmp
    try:
        with open(os.path.join(tmp, "demo.py"), "w", encoding="utf-8") as f:
            f.write('''def demo(param=""):
    return "demo"

__skill_meta__ = {"description": "演示技能", "params": {}, "tier": 2}
''')
        from core.skill_manager import SkillManager
        mgr = SkillManager()
        assert mgr.skill_exists("demo")

        # 禁用
        ok, msg = mgr.toggle_skill("demo", False)
        assert ok, msg
        assert not os.path.exists(os.path.join(tmp, "demo.py"))
        all_info = mgr.get_all_skills_info()
        assert "demo" in all_info
        assert all_info["demo"]["enabled"] is False

        # 启用（Windows 上重复切换也能成功：os.replace 覆盖）
        ok, msg = mgr.toggle_skill("demo", True)
        assert ok, msg
        assert os.path.exists(os.path.join(tmp, "demo.py"))
        all_info = mgr.get_all_skills_info()
        assert all_info["demo"]["enabled"] is True
    finally:
        settings.skills_dir = old
        shutil.rmtree(tmp, ignore_errors=True)


def test_toggle_idempotent():
    """重复禁用不抛 WinError183（明确返回失败消息而不是异常）"""
    tmp = tempfile.mkdtemp()
    old = settings.skills_dir
    settings.skills_dir = tmp
    try:
        with open(os.path.join(tmp, "x.py"), "w", encoding="utf-8") as f:
            f.write('def x():\n    return "x"\n')
        from core.skill_manager import SkillManager
        mgr = SkillManager()
        ok, _ = mgr.toggle_skill("x", False)
        assert ok
        ok2, msg2 = mgr.toggle_skill("x", False)
        assert ok2 is False
        assert "禁用" in msg2
    finally:
        settings.skills_dir = old
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_load_and_execute()
    test_load_skips_bad_file()
    test_toggle_skill_roundtrip()
    test_toggle_idempotent()
    print("✅ skill_manager 测试通过")
