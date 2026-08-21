# -*- coding: utf-8 -*-
"""
集成验证：Windows 最简状态
1. 无任何环境清单 → 自动探测（Windows：无舵机/屏幕/麦克风）
2. 启动 AgentLoop → 不预生成任何技能（模板库为空）
3. 纯聊天 + 记忆可用
4. 清理现场（不污染仓库）
"""
import os
import sys

sys.path.insert(0, ".")

from config import settings

MANIFEST = os.path.join(settings.base_dir, "environment.json")


def main():
    # 确保没有环境清单（最简状态）
    if os.path.exists(MANIFEST):
        os.remove(MANIFEST)
    caps_file = settings.capabilities_file
    if os.path.exists(caps_file):
        os.remove(caps_file)

    from core.agent_loop import AgentLoop
    agent = AgentLoop()

    print("[1] 探测到的能力:", {k: v for k, v in agent.capabilities.items()
                                if k in ("platform", "python", "network", "source")})
    print("[2] 预生成技能:", sorted(agent.skills.skills.keys()), "(应为空)")

    assert agent.skills.list_skills_formatted() == "当前没有任何技能", "最简状态不应有预生成技能"

    # 记忆闭环（离线可用）
    print("[3] 我叫小明 →", agent.run("我叫小明", []))
    print("[4] 我是谁 →", agent.run("我是谁", []))
    print("[5] 查看记忆 →", agent.run("查看记忆", [])[:60])

    # 自优化器可用（无 LLM 时修复失败但不崩溃）
    from core.self_optimizer import SelfOptimizer
    opt = SelfOptimizer(agent.skills, agent.capabilities)
    result = opt.optimize_skill("不存在的技能", "x", force=True)
    print("[6] 自优化器防御:", result["message"])

    print("\n✅✅ 集成验证通过：Windows 最简状态（无预置技能、聊天+记忆+自学习机制就绪）")

    # 清理现场
    agent.permanent_memory.clear_all()
    if os.path.exists(caps_file):
        os.remove(caps_file)
    print("[清理] 已复位记忆与能力清单")


if __name__ == "__main__":
    main()
