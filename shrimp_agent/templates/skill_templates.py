# -*- coding: utf-8 -*-
"""
能力模板库 - 最简状态

当前不预置任何技能模板：技能全部由 LLM 按能力清单按需生成
（core/skill_factory.generate_skill）。

此模块保留模板机制作为扩展点：将来某个环境需要"离线也能生成
基础技能"时，往 TEMPLATES 里加模板即可。模板格式参考 git 历史
（占位符 @TOKEN@ + requires 能力声明 + 走 hardware 抽象层）。
"""

TEMPLATES = {}


def list_templates():
    """返回模板名+描述"""
    return {name: t["description"] for name, t in TEMPLATES.items()}


def get_template(name):
    return TEMPLATES.get(name)
