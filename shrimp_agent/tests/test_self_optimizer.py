# -*- coding: utf-8 -*-
"""自优化器测试：验证链、dry-run、审计、无 LLM 时的失败路径"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import settings


def test_dry_run_safe():
    from core.self_optimizer import SelfOptimizer
    opt = SelfOptimizer(skill_manager=None, capabilities={})
    code = '''def hi():
    return "ok"

__skill_meta__ = {"safe": True}
'''
    r = opt._dry_run(code)
    assert r["ok"], r


def test_dry_run_unsafe_skipped():
    from core.self_optimizer import SelfOptimizer
    opt = SelfOptimizer(skill_manager=None, capabilities={})
    code = '''def hi():
    return "ok"

__skill_meta__ = {"safe": False}
'''
    r = opt._dry_run(code)
    assert r["ok"]
    assert "跳过" in r["note"]


def test_dry_run_failure_caught():
    from core.self_optimizer import SelfOptimizer
    opt = SelfOptimizer(skill_manager=None, capabilities={})
    code = '''def boom():
    raise RuntimeError("模拟崩溃")

__skill_meta__ = {"safe": True}
'''
    r = opt._dry_run(code)
    assert not r["ok"]
    assert "模拟崩溃" in r["error"]


def test_validate_chain():
    from core.self_optimizer import SelfOptimizer
    caps = {"actuators": [{"id": "tail", "type": "servo"}]}
    opt = SelfOptimizer(skill_manager=None, capabilities=caps)
    bad = '''from hardware import hw

def x():
    hw.servo("nope").set_angle(90)
    return "ok"
'''
    r = opt._validate(bad)
    assert not r["ok"]


def test_optimize_fails_without_llm():
    """无 LLM 时修复必然失败，且审计留痕"""
    from core.self_optimizer import SelfOptimizer
    from core.skill_manager import SkillManager

    tmp = tempfile.mkdtemp()
    old_dir = settings.skills_dir
    old_key = settings.api_key
    settings.skills_dir = tmp
    settings.api_key = "sk-xxx"
    try:
        with open(os.path.join(tmp, "bad_skill.py"), "w", encoding="utf-8") as f:
            f.write('''def bad_skill(param=""):
    return "[错误] 测试失败"

__skill_meta__ = {"description": "测试技能", "params": {}, "tier": 2}
''')
        mgr = SkillManager()
        opt = SelfOptimizer(mgr, {})
        result = opt.optimize_skill("bad_skill", "测试错误", force=True)
        assert result["success"] is False
        # 技能原样保留
        assert mgr.skill_exists("bad_skill")
        # 审计已写入
        audit = opt.audit_log()
        assert any(e["skill"] == "bad_skill" for e in audit["entries"])
    finally:
        settings.skills_dir = old_dir
        settings.api_key = old_key
        shutil.rmtree(tmp, ignore_errors=True)


def test_tier0_protected():
    from core.self_optimizer import SelfOptimizer
    from core.skill_manager import SkillManager

    tmp = tempfile.mkdtemp()
    old_dir = settings.skills_dir
    settings.skills_dir = tmp
    try:
        with open(os.path.join(tmp, "core_skill.py"), "w", encoding="utf-8") as f:
            f.write('''def core_skill(param=""):
    return "core"

__skill_meta__ = {"description": "核心", "params": {}, "tier": 0}
''')
        mgr = SkillManager()
        opt = SelfOptimizer(mgr, {})
        result = opt.optimize_skill("core_skill", "err", force=True)
        assert result["success"] is False
        assert "禁止" in result["message"]
    finally:
        settings.skills_dir = old_dir
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_dry_run_safe()
    test_dry_run_unsafe_skipped()
    test_dry_run_failure_caught()
    test_validate_chain()
    test_optimize_fails_without_llm()
    test_tier0_protected()
    print("✅ self_optimizer 测试通过")
