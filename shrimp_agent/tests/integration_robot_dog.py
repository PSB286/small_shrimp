# -*- coding: utf-8 -*-
"""
集成验证：模拟"部署到机器狗"
1. 提供 environment.json（主动提供硬件条件）
2. 启动 AgentLoop → 应自动引导生成基础技能（舵机测试/摇尾巴/走路/跳舞/表情）
3. 实际执行这些技能（模拟器模式）
4. 验证技能档案记录
5. 清理现场（不污染仓库）
"""
import os
import sys
import json

sys.path.insert(0, ".")

from config import settings

MANIFEST = os.path.join(settings.base_dir, "environment.json")
DOG_CAPS = {
    "actuators": [
        {"id": "leg_fl", "type": "servo", "channel": 0, "min": 0, "max": 180},
        {"id": "leg_fr", "type": "servo", "channel": 1, "min": 0, "max": 180},
        {"id": "leg_bl", "type": "servo", "channel": 2, "min": 0, "max": 180},
        {"id": "leg_br", "type": "servo", "channel": 3, "min": 0, "max": 180},
        {"id": "tail", "type": "servo", "channel": 4, "min": 0, "max": 180},
    ],
    "display": {"type": "ssd1306", "w": 128, "h": 64},
    "audio_in": {"type": "mic"},
    "network": True,
}

GENERATED = ["servo_test", "wag_tail", "walk", "dance", "show_face", "listen"]


def main():
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(DOG_CAPS, f, ensure_ascii=False, indent=2)
    print("[1] 已提供环境清单（5舵机+屏幕+麦克风）")

    try:
        from core.agent_loop import AgentLoop
        agent = AgentLoop()
        # 重置技能档案，保证测试确定性
        agent.permanent_memory.reset_skill_stats()

        print("[2] 引导生成的技能:", sorted(agent.skills.skills.keys()))
        for name in GENERATED:
            assert name in agent.skills.skills, "缺少技能: %s" % name

        # 执行（模拟器）
        print("[3] 执行 wag_tail →", agent._execute_skill("wag_tail"))
        print("[4] 执行 walk →", agent._execute_skill("walk"))
        print("[5] 执行 dance →", agent._execute_skill("dance"))
        print("[6] 执行 show_face →", agent._execute_skill("show_face"))
        print("[7] 执行 listen →", agent._execute_skill("listen"))

        # 技能档案
        stats = agent.permanent_memory.get_all_skill_stats()
        print("[8] 技能档案:", {k: {"count": v["count"], "success": v["success"]} for k, v in stats.items()})
        assert stats["walk"]["success"] == 1, stats
        assert stats["dance"]["success"] == 1, stats

        # 硬件状态（模拟器）
        from hardware import get_hardware
        state = get_hardware().state()
        print("[9] 模拟硬件状态: 舵机角度 =", {k: v["angle"] for k, v in state["servos"].items()})
        # 所有舵机都被动作序列驱动过，角度应在量程内
        for sid, s in state["servos"].items():
            assert s["angle"] is not None and 0 <= s["angle"] <= 180, (sid, s)

        # 触发一次技能失败 → 自优化闭环（T2 无 LLM → 修复失败但留痕）
        print("[10] 触发自优化（故意让 skill 报错）...")
        from core.self_optimizer import SelfOptimizer
        opt = SelfOptimizer(agent.skills, agent.capabilities)
        result = opt.optimize_skill("walk", "模拟错误: 舵机卡死", force=True)
        print("     自优化结果:", result)
        audit = opt.audit_log()
        assert any(e["skill"] == "walk" for e in audit["entries"]), "审计未留痕"

        print("\n✅✅ 集成验证通过：机器狗环境 → 自动生成技能 → 可执行 → 有档案 → 可自优化")
    finally:
        if os.path.exists(MANIFEST):
            os.remove(MANIFEST)
        # 清理生成的技能文件
        for name in GENERATED:
            p = os.path.join(settings.skills_dir, name + ".py")
            if os.path.exists(p):
                os.remove(p)
        # 能力清单复位为纯探测结果
        caps_file = settings.capabilities_file
        if os.path.exists(caps_file):
            os.remove(caps_file)
        print("\n[清理] 已移除环境清单/生成的技能/能力清单")


if __name__ == "__main__":
    main()
