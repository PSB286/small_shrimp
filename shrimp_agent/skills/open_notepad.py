import os
import re
import subprocess
import tempfile

__skill_meta__ = {
    "description": "Windows 记事本管理：打开、写入、追加、读取、清空、打印文件路径",
    "params": {
        "param": {
            "type": "string",
            "description": "用户的完整请求（如'写入 你好'、'读取'、'清空'、'追加 xx'、'打印路径'、'打开'）"
        }
    },
    "tier": 2
}

# 固定的记忆文件：同一个记事本内容跨会话保留，所有操作都基于这个路径
_MEMO_FILE = os.path.join(tempfile.gettempdir(), "shrimp_notepad.txt")

# 位置/对象短语：先剥离（长短语优先，避免残留"中/在里面"）
_LOCATION_PHRASES = [
    "在这个记事本中", "在这个记事本里", "在这个记事本",
    "在记事本中", "在记事本里", "记事本里面", "记事本里",
    "在里面", "进去", "这个记事本", "当前记事本", "记事本", "当前",
]

# 动作词：后剥离（长优先，避免"写"误伤"写字"）
_WRITE_ACTIONS = ["写一下", "写入", "写上", "记下", "记录", "改成", "写"]
_APPEND_ACTIONS = ["在后面加", "接着写", "后面写", "加上", "追加"]


def _read_content():
    if not os.path.exists(_MEMO_FILE):
        return ""
    try:
        with open(_MEMO_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _write_content(content):
    with open(_MEMO_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(content)


def _append_content(content):
    """追加内容（自动换行分隔）"""
    existing = _read_content()
    if existing and not existing.endswith("\n"):
        existing += "\n"
    _write_content(existing + content)


def _strip_action(req, action_words):
    """提取内容：先剥位置短语，再按长度降序剥动作词，最后清理标点"""
    text = req
    for phrase in _LOCATION_PHRASES:
        text = text.replace(phrase, "")
    for w in sorted(action_words, key=len, reverse=True):
        text = text.replace(w, "")
    return text.strip(" ，。！!？?：:、\n\t")


# 创作类请求检测：写/做/作/创作 诗、文章等（内容需要 AI 创作，先确认是写内容还是写文字）
_CREATIVE_RES = [
    re.compile(r'(?:写|做|作|创作)(?:一|两|几)?[首篇段]\s*([^\s，。！!？?]+)'),  # 写一首静夜思 / 做一首诗 / 写一篇作文
    re.compile(r'(?:写|做|作|创作)(?:一|两|几)?(?:首|篇|段)?\s*(?:诗|古诗|诗词|文章|作文|词|诗篇|对联|祝福语|文案)'),  # 写诗/做诗/创作文章
]


def _detect_creative(req):
    """检测创作类请求，返回主题（如 静夜思）；不是创作类返回 None"""
    for rx in _CREATIVE_RES:
        m = rx.search(req)
        if m:
            rest = m.group(1) if m.lastindex else ""
            for phrase in _LOCATION_PHRASES:
                rest = rest.replace(phrase, "")
            rest = rest.strip(" ，。！!？?：:、\n\t")
            return rest or "一首诗"
    return None


def _open_memo():
    """打开记忆文件（复用同一个文件）"""
    if os.path.exists(_MEMO_FILE):
        subprocess.Popen(["notepad.exe", _MEMO_FILE])
    else:
        subprocess.Popen("notepad.exe")


def open_notepad(param: str = ''):
    """
    Windows 记事本管理：按请求关键词判断动作。
    每次操作都报告文件路径，后续操作基于同一路径。
    - 打印路径 → 直接返回文件路径
    - 读取 → 返回内容（不打开窗口）
    - 清空 → 清空内容（不打开窗口）
    - 追加 → 追加内容并打开窗口
    - 写入/写 → 覆盖写入并打开窗口
    - 打开/空 → 打开记事本（报告路径）
    - 其他 → 当作要写入的内容
    """
    req = (param or '').strip()

    # 0.5 原文写入协议：Agent 传入 __RAW__:内容 → 原样写入（不解析动作，防诗词含"写"字被误剥）
    if req.startswith("__RAW__:"):
        content = req[len("__RAW__:"):].strip()
        _write_content(content)
        _open_memo()
        return "记事本已打开，并成功写入：%s（文件路径：%s）" % (content, _MEMO_FILE)

    # 0.6 原文追加协议：__RAW_APPEND__:内容 → 原样追加到已有内容后面
    if req.startswith("__RAW_APPEND__:"):
        content = req[len("__RAW_APPEND__:"):].strip()
        _append_content(content)
        _open_memo()
        return "已追加到记事本：%s（文件路径：%s）" % (content, _MEMO_FILE)

    # 0.7 创作类请求（写/做一首诗、文章等）→ 先确认内容 vs 文字，并保留 写入/追加 意图
    creative = _detect_creative(req)
    if creative:
        action = "append" if any(k in req for k in ["追加", "接着", "后面", "加", "续"]) else "write"
        return "__ASK__:creative_poem|%s|%s" % (creative, action)

    # 0. 打印/显示文件路径（优先级最高，避免"打印路径"被当成其他动作）
    if "路径" in req and any(k in req for k in ["打印", "显示", "查看", "查", "告诉", "是什么", "在哪", "哪里"]):
        return "记事本文件路径：%s" % _MEMO_FILE

    # 1. 读取内容（不打开窗口，避免反复弹窗）
    if any(k in req for k in ["读取", "读一下", "看看", "查看", "看下", "瞧", "内容是什么", "读出来", "读一遍"]):
        content = _read_content()
        if content:
            return "记事本内容：\n%s\n（文件路径：%s）" % (content, _MEMO_FILE)
        return "记事本内容为空（文件路径：%s）" % _MEMO_FILE

    # 2. 清空内容（不打开窗口）
    if any(k in req for k in ["清空", "清除", "清掉", "清一下", "清空内容", "删除内容", "删掉内容", "删掉"]):
        _write_content("")
        return "记事本内容已清空（文件路径：%s）" % _MEMO_FILE

    # 3. 追加内容（打开窗口展示）
    if any(k in req for k in _APPEND_ACTIONS):
        content = _strip_action(req, _APPEND_ACTIONS + ["内容", "文字"])
        if not content:
            return "请告诉我要追加什么内容"
        _append_content(content)
        _open_memo()
        return "已追加到记事本：%s（文件路径：%s）" % (content, _MEMO_FILE)

    # 4. 写入内容（覆盖，打开窗口展示）
    if any(k in req for k in _WRITE_ACTIONS):
        content = _strip_action(req, _WRITE_ACTIONS + ["内容", "文字"])
        # 去掉"把《X》这首诗："这类包装（云端传入的诗可能带前缀）
        content = re.sub(r'^把《?[^》\n]+》?(?:这|那)?首?诗?[：:，,]?\s*', '', content)
        content = re.sub(r'^把[^\n]{1,12}?(?:这首|那首)?诗[：:，,]?\s*', '', content)
        if not content:
            return "请告诉我要写入什么内容"
        _write_content(content)
        _open_memo()
        return "记事本已打开，并成功写入：%s（文件路径：%s）" % (content, _MEMO_FILE)

    # 5. 打开记事本（报告路径）
    if not req or any(k in req for k in ["打开", "开一下", "启动", "开启"]):
        _open_memo()
        return "记事本已打开（文件路径：%s）" % _MEMO_FILE

    # 6. 默认：把请求当作要写入的内容
    _write_content(req)
    _open_memo()
    return "记事本已写入：%s（文件路径：%s）" % (req, _MEMO_FILE)
