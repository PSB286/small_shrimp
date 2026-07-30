# 导入 FastAPI 核心类，用于创建 Web 应用
from fastapi import FastAPI, Request
# 导入静态文件挂载功能
from fastapi.staticfiles import StaticFiles
# 导入 HTML 和 JSON 响应类
from fastapi.responses import HTMLResponse, JSONResponse
# 导入跨域中间件，允许前端不同源访问
from fastapi.middleware.cors import CORSMiddleware
# 导入 ASGI 服务器启动器
import uvicorn
# 导入操作系统接口，用于文件路径操作
import os
# 导入正则表达式
import re

# 导入自定义的 Agent 主循环模块
from core.agent_loop import AgentLoop
# 导入技能管理器，负责加载、执行技能
from core.skill_manager import SkillManager
# 导入短期记忆模块，存储对话历史
from memory.short_term import ShortTermMemory
# 导入日志记录器，用于记录运行信息
from utils.logger import logger

# 创建 FastAPI 应用实例，并设置标题
app = FastAPI(title="GGB小虾米 · 智能助手")

# 添加跨域中间件，允许所有源（方便开发调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名访问
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 挂载静态文件目录，将 /static 路径映射到本地 static 文件夹
app.mount("/static", StaticFiles(directory="static"), name="static")

# 初始化 Agent 主循环实例
agent = AgentLoop()
# 初始化技能管理器实例
skill_mgr = SkillManager()
# 初始化短期记忆实例
memory = ShortTermMemory()


# 定义根路径 GET 处理函数
@app.get("/")
async def get():
    try:
        # 尝试打开 static/index.html 文件
        with open("static/index.html", "r", encoding="utf-8") as f:
            # 如果存在，返回文件内容作为 HTML 响应
            return HTMLResponse(f.read())
    except FileNotFoundError:
        # 如果文件不存在，返回提示信息
        return HTMLResponse("<h1>请创建 static/index.html</h1>")


# 定义 /chat 路径的 POST 处理函数，用于接收用户消息并返回回复
@app.post("/chat")
async def chat(request: Request):
    # 解析请求体中的 JSON 数据
    data = await request.json()
    # 提取 message 字段，如果没有则默认为空字符串
    user_input = data.get("message", "")
    # 如果用户输入为空，直接返回错误提示
    if not user_input:
        return JSONResponse({"reply": "请输入消息"})

    # 从短期记忆中获取对话历史
    history = memory.get_history()

    # 调用 Agent 循环处理用户输入，得到回复
    reply = agent.run(user_input, history)

    # 将本次对话存入短期记忆（用户输入 + 助手回复）
    memory.add(user_input, reply)

    # 记录日志，截取前 50 字符避免过长
    logger.info(f"User: {user_input[:50]}... | Reply: {reply[:50]}...")

    # 返回 JSON 格式的回复
    return JSONResponse({"reply": reply})


# 定义 /skills 路径的 GET 处理函数，返回当前所有技能信息
@app.get("/skills")
async def get_skills():
    # 从技能管理器获取所有技能信息（名称、描述等）
    skills_info = skill_mgr.get_skills_info()
    # 返回 JSON 格式的技能列表
    return JSONResponse({"skills": skills_info})


# 定义 /skills/toggle 路径的 POST 处理函数，用于切换技能启用状态
@app.post("/skills/toggle")
async def toggle_skill(request: Request):
    """切换技能启用/禁用状态"""
    try:
        data = await request.json()
        skill_name = data.get("skill_name")
        enabled = data.get("enabled", True)

        if not skill_name:
            return JSONResponse({"error": "缺少 skill_name"}, status_code=400)

        if not skill_mgr.skill_exists(skill_name):
            return JSONResponse({"error": f"技能 {skill_name} 不存在"}, status_code=404)

        result = skill_mgr.toggle_skill(skill_name, enabled)

        return JSONResponse({
            "success": True,
            "skill_name": skill_name,
            "enabled": enabled,
            "message": f"技能 {skill_name} 已{'启用' if enabled else '禁用'}"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 定义 /skills/create 路径的 POST 处理函数，手动创建新技能
@app.post("/skills/create")
async def create_skill(request: Request):
    data = await request.json()
    skill_name = data.get("skill_name")
    description = data.get("description")
    params = data.get("params", {})

    if not skill_name or not description:
        return JSONResponse({"error": "缺少 skill_name 或 description"}, status_code=400)

    from core.skill_creator import SkillCreator
    creator = SkillCreator()
    success, msg = creator.create_skill(skill_name, description, params)

    if success:
        skill_mgr.load_skills()
        return JSONResponse({"success": True, "message": msg})
    else:
        return JSONResponse({"success": False, "error": msg}, status_code=400)


# 定义 /skills/suggest 路径的 POST 处理函数，主动建议新技能
@app.post("/skills/suggest")
async def suggest_skill(request: Request):
    from core.skill_learner import SkillLearner
    learner = SkillLearner()
    history = memory.get_history()
    suggestion = learner.suggest_skill(history)

    if suggestion:
        return JSONResponse({"suggestion": suggestion})
    else:
        return JSONResponse({"suggestion": None, "message": "暂无合适的技能建议"})


# ==================== 助手名称管理接口 ====================

# 获取当前助手名称
@app.get("/agent/name")
async def get_agent_name():
    """获取当前助手名称"""
    return JSONResponse({
        "name": agent.agent_name,
        "default_name": "GGB小虾米"
    })


# 设置助手名称
@app.post("/agent/name")
async def set_agent_name(request: Request):
    """设置助手名称"""
    try:
        data = await request.json()
        new_name = data.get("name", "").strip()

        if not new_name:
            return JSONResponse({"error": "名称不能为空"}, status_code=400)

        if len(new_name) > 20:
            return JSONResponse({"error": "名称不能超过20个字"}, status_code=400)

        if re.search(r'[<>"\'/\\]', new_name):
            return JSONResponse({"error": "名称包含非法字符，请使用中文、英文或数字"}, status_code=400)

        old_name = agent.agent_name
        agent.agent_name = new_name
        agent.cloud.set_agent_name(new_name)
        agent.context["agent_name"] = new_name
        agent.permanent_memory.set_user_name(new_name)
        memory.add_system_message(f"助手名称已从 '{old_name}' 改为 '{new_name}'")

        logger.info(f"[API] 名称已更改: {old_name} → {new_name}")

        return JSONResponse({
            "success": True,
            "old_name": old_name,
            "new_name": new_name,
            "message": f"名称已从 '{old_name}' 改为 '{new_name}'"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 重置助手名称为默认名称
@app.post("/agent/name/reset")
async def reset_agent_name():
    """重置助手名称为默认名称"""
    try:
        old_name = agent.agent_name
        default_name = "GGB小虾米"

        agent.agent_name = default_name
        agent.cloud.set_agent_name(default_name)
        agent.context["agent_name"] = default_name
        agent.permanent_memory.set_user_name(default_name)
        memory.add_system_message(f"助手名称已重置: '{old_name}' → '{default_name}'")

        logger.info(f"[API] 名称已重置: {old_name} → {default_name}")

        return JSONResponse({
            "success": True,
            "old_name": old_name,
            "new_name": default_name,
            "message": f"名称已重置为 '{default_name}'"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 对话历史管理接口 ====================

# 获取对话历史
@app.get("/history")
async def get_history():
    """获取对话历史"""
    try:
        history = memory.get_history()
        return JSONResponse({
            "history": history,
            "count": len(history)
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 清空对话历史
@app.post("/history/clear")
async def clear_history():
    """清空对话历史"""
    try:
        memory.clear()
        return JSONResponse({
            "success": True,
            "message": "对话历史已清空"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 永久记忆管理接口 ====================

# 获取所有永久记忆
@app.get("/memory/permanent")
async def get_permanent_memory():
    """获取所有永久记忆"""
    try:
        memories = agent.permanent_memory.get_all_memories()
        return JSONResponse({
            "success": True,
            "data": memories
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 获取用户信息
@app.get("/memory/user")
async def get_user_info():
    """获取用户信息"""
    try:
        user_info = agent.permanent_memory.get_all_user_info()
        return JSONResponse({
            "success": True,
            "data": user_info
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 设置用户信息
@app.post("/memory/user")
async def set_user_info(request: Request):
    """设置用户信息"""
    try:
        data = await request.json()
        key = data.get("key")
        value = data.get("value")

        if not key:
            return JSONResponse({"error": "缺少 key"}, status_code=400)

        success = agent.permanent_memory.set_user_info(key, value)
        if success:
            agent._update_memory_context()
            return JSONResponse({
                "success": True,
                "message": f"用户信息 {key} 已更新"
            })
        else:
            return JSONResponse({"error": "设置失败"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 获取偏好
@app.get("/memory/preferences")
async def get_preferences():
    """获取用户偏好"""
    try:
        preferences = agent.permanent_memory.get_all_preferences()
        return JSONResponse({
            "success": True,
            "data": preferences
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 设置偏好
@app.post("/memory/preferences")
async def set_preference(request: Request):
    """设置用户偏好"""
    try:
        data = await request.json()
        key = data.get("key")
        value = data.get("value")

        if not key:
            return JSONResponse({"error": "缺少 key"}, status_code=400)

        success = agent.permanent_memory.set_preference(key, value)
        if success:
            agent._update_memory_context()
            return JSONResponse({
                "success": True,
                "message": f"偏好 {key} 已更新"
            })
        else:
            return JSONResponse({"error": "设置失败"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 获取重要事实
@app.get("/memory/facts")
async def get_facts():
    """获取重要事实"""
    try:
        facts = agent.permanent_memory.get_facts()
        return JSONResponse({
            "success": True,
            "data": facts
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 添加重要事实
@app.post("/memory/facts")
async def add_fact(request: Request):
    """添加重要事实"""
    try:
        data = await request.json()
        fact = data.get("fact")
        category = data.get("category", "general")

        if not fact:
            return JSONResponse({"error": "缺少 fact"}, status_code=400)

        success = agent.permanent_memory.add_fact(fact, category)
        if success:
            agent._update_memory_context()
            return JSONResponse({
                "success": True,
                "message": f"已记住：{fact}"
            })
        else:
            return JSONResponse({"error": "添加失败"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 删除重要事实
@app.delete("/memory/facts/{index}")
async def delete_fact(index: int):
    """删除指定事实"""
    try:
        success = agent.permanent_memory.delete_fact(index)
        if success:
            agent._update_memory_context()
            return JSONResponse({
                "success": True,
                "message": f"已删除第 {index + 1} 条事实"
            })
        else:
            return JSONResponse({"error": "删除失败"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 清空所有永久记忆
@app.post("/memory/clear")
async def clear_permanent_memory():
    """清空所有永久记忆"""
    try:
        success = agent.permanent_memory.clear_all()
        if success:
            agent._update_memory_context()
            return JSONResponse({
                "success": True,
                "message": "所有永久记忆已清空"
            })
        else:
            return JSONResponse({"error": "清空失败"}, status_code=500)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 获取记忆上下文提示
@app.get("/memory/context")
async def get_memory_context():
    """获取记忆上下文提示"""
    try:
        context = agent.memory_integration.get_memory_context()
        return JSONResponse({
            "success": True,
            "context": context
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 如果此文件作为主程序运行，则启动 Uvicorn 服务器
if __name__ == "__main__":
    # 启动服务，监听 127.0.0.1 的 8000 端口
    uvicorn.run(app, host="127.0.0.1", port=8000)