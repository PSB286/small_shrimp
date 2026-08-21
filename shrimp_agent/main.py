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
# 环境感知与自优化
from core.environment_probe import EnvironmentProbe
from core.skill_factory import bootstrap_skills
from core.self_optimizer import SelfOptimizer
from config import settings

# ==================== 启动初始化 ====================
# 1. 环境探测：平台驱动，生成/读取能力清单（技能生成与硬件抽象的唯一依据）
probe = EnvironmentProbe()
capabilities = probe.ensure_capabilities()
_caps_parts = []
if capabilities.get("actuators"):
    _caps_parts.append(f"舵机x{len(capabilities['actuators'])}")
if capabilities.get("display"):
    _caps_parts.append("屏幕")
if capabilities.get("audio_in"):
    _caps_parts.append("麦克风")
if capabilities.get("audio_out"):
    _caps_parts.append("喇叭")
if capabilities.get("camera"):
    _caps_parts.append("摄像头")
if capabilities.get("network"):
    _caps_parts.append("联网")
logger.info(f"[Main] 环境能力: {capabilities.get('platform', '未知')} | "
            + (", ".join(_caps_parts) if _caps_parts else "无特殊硬件（纯聊天+记忆）"))

# 2. 创建 FastAPI 应用实例
app = FastAPI(title="GGB小虾米 · 环境自适应智能助手")

# 添加跨域中间件，允许所有源（方便开发调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有域名访问
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# 挂载静态文件目录（绝对路径，摆脱 cwd 依赖）
app.mount("/static", StaticFiles(directory=os.path.join(settings.base_dir, "static")), name="static")

# 3. 初始化 Agent 主循环实例（内部会按能力清单引导创建基础技能）
agent = AgentLoop()
# 4. 初始化技能管理器实例（与 agent 共享同一技能目录）
skill_mgr = SkillManager()
# 5. 确保基础技能已引导（agent 引导后这里再同步一次）
if settings.auto_bootstrap:
    created = bootstrap_skills(skill_mgr, capabilities)
    if created:
        logger.info(f"[Main] 引导创建基础技能: {created}")
# 6. 自优化器（修复失败技能）
optimizer = SelfOptimizer(skill_mgr, capabilities)
# 7. 初始化短期记忆实例
memory = ShortTermMemory()


# 定义根路径 GET 处理函数
@app.get("/")
async def get():
    try:
        # 尝试打开 static/index.html 文件
        with open(os.path.join(settings.base_dir, "static", "index.html"), "r", encoding="utf-8") as f:
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

    # 支持引用：前端传来的 quote = {"role": "user"/"bot", "content": "被引用的消息"}
    quote = data.get("quote")
    agent_input = user_input
    if isinstance(quote, dict) and quote.get("content"):
        quoted = str(quote.get("content"))
        role_label = "你" if quote.get("role") == "user" else "小虾米"
        agent_input = f"【我引用了{role_label}的这段话】\n{quoted}\n\n{user_input}"

    # 从短期记忆中获取对话历史
    history = memory.get_history()

    # 调用 Agent 循环处理用户输入，得到回复
    reply = agent.run(agent_input, history)

    # 将本次对话存入短期记忆（用户输入 + 助手回复）
    memory.add(user_input, reply)

    # 记录日志，截取前 50 字符避免过长
    logger.info(f"User: {user_input[:50]}... | Reply: {reply[:50]}...")

    # 返回 JSON 格式的回复
    return JSONResponse({"reply": reply})


# ==================== 环境能力管理接口 ====================

# 查看当前环境能力清单与探测结果
@app.get("/environment")
async def get_environment():
    """查看环境探测结果与能力清单"""
    if not probe.probes:
        probe.run_probes()
    caps = capabilities
    return JSONResponse({
        "success": True,
        "capabilities": caps,
        "probes": probe.probes
    })


# 手动修正环境能力（通道③：界面修正）
@app.post("/environment")
async def update_environment(request: Request):
    """修改能力清单（如声明舵机布局/屏幕/麦克风）"""
    try:
        data = await request.json()
        ok, msg = probe.update(data)
        if not ok:
            return JSONResponse({"error": msg}, status_code=400)
        # 能力变化 → 重建硬件 + 重新引导技能
        from hardware import reload_hardware
        reload_hardware()
        agent.capabilities = probe.get_capabilities()
        global capabilities
        capabilities = agent.capabilities
        bootstrap_skills(skill_mgr, capabilities)
        agent.skills.reload_skills()
        agent.cloud.set_skills_info(agent.skills.get_skills_info())
        return JSONResponse({"success": True, "message": msg})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ==================== 技能管理接口 ====================

# 定义 /skills 路径的 GET 处理函数，返回所有技能（含已禁用，带开关状态）
@app.get("/skills")
async def get_skills():
    # 从技能管理器获取所有技能信息（含 enabled 标记）
    skills_info = skill_mgr.get_all_skills_info()
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

        success, message = skill_mgr.toggle_skill(skill_name, enabled)

        if not success:
            return JSONResponse({"error": message}, status_code=400)

        return JSONResponse({
            "success": True,
            "skill_name": skill_name,
            "enabled": enabled,
            "message": message
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 定义 /skills/create 路径的 POST 处理函数，手动创建新技能（走能力感知工厂）
@app.post("/skills/create")
async def create_skill(request: Request):
    data = await request.json()
    skill_name = data.get("skill_name")
    description = data.get("description")
    params = data.get("params", {})

    if not description:
        return JSONResponse({"error": "缺少 description"}, status_code=400)

    from core.skill_factory import generate_skill, sanitize_filename
    caps = agent.capabilities or capabilities
    history = memory.get_history()
    result = generate_skill(description, caps, history)
    if not result:
        return JSONResponse({
            "error": "生成失败：需求不明确或本环境能力不足（可先通过 /environment 声明硬件）"
        }, status_code=400)

    code, name, desc, msgs = result
    name = sanitize_filename(name or skill_name, "new_skill")
    filepath = os.path.join(skill_mgr.skills_dir, f"{name}.py")
    if os.path.exists(filepath):
        return JSONResponse({"error": f"技能 {name} 已存在"}, status_code=400)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(code)
    skill_mgr.reload_skills()
    return JSONResponse({"success": True, "message": f"技能 {name} 已创建（{msgs[0] if msgs else ''}）"})


# 手动触发技能自修复
@app.post("/skills/fix")
async def fix_skill(request: Request):
    """修复一个执行失败的技能（走五步验证链）"""
    try:
        data = await request.json()
        skill_name = data.get("skill_name")
        if not skill_name:
            return JSONResponse({"error": "缺少 skill_name"}, status_code=400)
        stats = agent.permanent_memory.get_skill_stats(skill_name)
        error = data.get("error") or stats.get("last_error", "") or "手动修复"
        result = optimizer.optimize_skill(skill_name, error, force=True)
        return JSONResponse(result, status_code=200 if result["success"] else 400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# 技能学习档案（成功率/连续失败）
@app.get("/skills/stats")
async def get_skill_stats():
    """查看每个技能的执行统计（自优化经验库）"""
    return JSONResponse({
        "success": True,
        "stats": agent.permanent_memory.get_all_skill_stats(),
        "audit": optimizer.audit_log()
    })


# 定义 /skills/suggest 路径的 POST 处理函数，主动建议新技能（能力感知）
@app.post("/skills/suggest")
async def suggest_skill(request: Request):
    from core.skill_learner import SkillLearner
    learner = SkillLearner()
    history = memory.get_history()
    caps = agent.capabilities or capabilities
    suggestion = learner.suggest_skill(history, caps)

    if suggestion:
        return JSONResponse({"suggestion": suggestion})
    else:
        return JSONResponse({"suggestion": None, "message": "暂无合适的技能建议"})


# 硬件状态（模拟器状态，调试用）
@app.get("/hardware/state")
async def get_hardware_state():
    """查看当前硬件状态（模拟后端返回完整状态）"""
    try:
        from hardware import get_hardware
        hw = get_hardware()
        return JSONResponse({"success": True, "state": hw.state()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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
        agent._set_agent_name(new_name)
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

        agent._set_agent_name(default_name)
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
    # 启动服务，监听 0.0.0.0 的 8000 端口（便于局域网设备访问）
    uvicorn.run(app, host="0.0.0.0", port=8000)
