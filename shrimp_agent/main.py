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
    allow_origins=["*"],      # 允许所有域名访问
    allow_methods=["*"],      # 允许所有 HTTP 方法
    allow_headers=["*"],      # 允许所有请求头
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

# 定义 /skills/toggle 路径的 POST 处理函数，用于切换技能启用状态（预留功能）
@app.post("/skills/toggle")
async def toggle_skill(request: Request):
    # 解析请求体（当前未使用，仅做示例）
    data = await request.json()
    # 返回成功标志（实际功能尚未实现）
    return JSONResponse({"success": True})

# 定义 /skills/create 路径的 POST 处理函数，手动创建新技能
@app.post("/skills/create")
async def create_skill(request: Request):
    # 解析请求体
    data = await request.json()
    # 提取技能名称
    skill_name = data.get("skill_name")
    # 提取技能描述
    description = data.get("description")
    # 提取参数定义（默认为空字典）
    params = data.get("params", {})
    
    # 校验必须字段是否存在
    if not skill_name or not description:
        return JSONResponse({"error": "缺少 skill_name 或 description"}, status_code=400)
    
    # 导入技能创建器模块
    from core.skill_creator import SkillCreator
    # 实例化技能创建器
    creator = SkillCreator()
    # 调用创建方法，返回成功标志和消息
    success, msg = creator.create_skill(skill_name, description, params)
    
    if success:
        # 如果创建成功，重新加载所有技能使新技能生效
        skill_mgr.load_skills()
        return JSONResponse({"success": True, "message": msg})
    else:
        # 如果失败，返回错误信息
        return JSONResponse({"success": False, "error": msg}, status_code=400)

# 定义 /skills/suggest 路径的 POST 处理函数，主动建议新技能
@app.post("/skills/suggest")
async def suggest_skill(request: Request):
    # 导入技能学习建议模块
    from core.skill_learner import SkillLearner
    # 实例化技能学习器
    learner = SkillLearner()
    # 获取当前对话历史，用于分析可能需要的技能
    history = memory.get_history()
    # 调用建议方法，返回建议的技能描述（或 None）
    suggestion = learner.suggest_skill(history)
    
    if suggestion:
        # 如果有建议，返回建议内容
        return JSONResponse({"suggestion": suggestion})
    else:
        # 否则返回无建议消息
        return JSONResponse({"suggestion": None, "message": "暂无合适的技能建议"})

# 如果此文件作为主程序运行，则启动 Uvicorn 服务器
if __name__ == "__main__":
    # 启动服务，监听 127.0.0.1 的 8000 端口
    uvicorn.run(app, host="127.0.0.1", port=8000)