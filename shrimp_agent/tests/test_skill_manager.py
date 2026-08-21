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
        # 坏文件被跳过，不崩溃
        assert mgr.skill_exists("broken") is False
    finally:
        settings.skills_dir = old
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_load_and_execute()
    test_load_skips_bad_file()
    print("✅ skill_manager 测试通过")
