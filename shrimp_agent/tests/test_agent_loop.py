import sys
sys.path.append('.')

from core.agent_loop import AgentLoop

def test_agent_loop():
    agent = AgentLoop()
    
    # 测试本地指令
    result = agent.run("现在几点", [])
    print(f"本地指令: {result}")
    assert "时间" in result
    
    # 测试数学计算
    result = agent.run("3+5等于多少", [])
    print(f"数学计算: {result}")
    assert "8" in result
    
    print("✅ Agent 循环测试通过")

if __name__ == "__main__":
    test_agent_loop()