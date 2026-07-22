import sys
sys.path.append('.')

from core.skill_creator import SkillCreator
from core.skill_learner import SkillLearner

def test_create_skill():
    creator = SkillCreator()
    success, msg = creator.create_skill(
        "greet_user",
        "向用户打招呼",
        {"name": "用户名称"}
    )
    print(f"创建结果: {msg}")
    assert success

def test_skill_learner():
    learner = SkillLearner()
    history = [
        {"role": "user", "content": "帮我算一下 3+5"},
        {"role": "assistant", "content": "8"},
        {"role": "user", "content": "再算一下 10+20"},
        {"role": "assistant", "content": "30"},
        {"role": "user", "content": "能帮我算 100+200 吗"},
    ]
    suggestion = learner.suggest_skill(history)
    print(f"建议: {suggestion}")
    assert suggestion is not None

if __name__ == "__main__":
    test_create_skill()
    test_skill_learner()
    print("✅ 所有测试通过")