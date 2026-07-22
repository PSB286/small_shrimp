from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

from core.agent_loop import AgentLoop
from core.skill_manager import SkillManager
from memory.short_term import ShortTermMemory
from utils.logger import logger

app = FastAPI(title="GGB小虾米 · 智能助手")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")

# 初始化核心组件
agent = AgentLoop()
skill_mgr = SkillManager()
memory = ShortTermMemory()

@app.get("/")
async def get():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>请创建 static/index.html</h1>")

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_input = data.get("message", "")
    if not user_input:
        return JSONResponse({"reply": "请输入消息"})
    
    # 获取历史
    history = memory.get_history()
    
    # 运行 Agent
    reply = agent.run(user_input, history)
    
    # 保存对话
    memory.add(user_input, reply)
    
    # 记录日志
    logger.info(f"User: {user_input[:50]}... | Reply: {reply[:50]}...")
    
    return JSONResponse({"reply": reply})

@app.get("/skills")
async def get_skills():
    """获取所有技能列表"""
    skills_info = skill_mgr.get_skills_info()
    return JSONResponse({"skills": skills_info})

@app.post("/skills/toggle")
async def toggle_skill(request: Request):
    """切换技能启用状态（预留）"""
    data = await request.json()
    return JSONResponse({"success": True})

@app.post("/skills/create")
async def create_skill(request: Request):
    """手动创建新技能"""
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
        # 重新加载技能
        skill_mgr.load_skills()
        return JSONResponse({"success": True, "message": msg})
    else:
        return JSONResponse({"success": False, "error": msg}, status_code=400)

@app.post("/skills/suggest")
async def suggest_skill(request: Request):
    """主动建议新技能"""
    from core.skill_learner import SkillLearner
    learner = SkillLearner()
    history = memory.get_history()
    suggestion = learner.suggest_skill(history)
    
    if suggestion:
        return JSONResponse({"suggestion": suggestion})
    else:
        return JSONResponse({"suggestion": None, "message": "暂无合适的技能建议"})

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)