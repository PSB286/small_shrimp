import os
import re
import subprocess
import tempfile

__skill_meta__ = {
    "description": "Windows 记事本管理：打开、写入、追加、读取、清空内容",
    "params": {
        "param": {
            "type": "string",
            "description": "用户的完整请求（如'写入 你好'、'读取'、'清空'、'追加 xx'、'打开'）"
        }
    },
    "tier": 2
}

# 固定的记忆文件：同一个记事本内容跨会话保留，不反复新建文件
_MEMO_FILE = os.path.join(tempfile.gettempdir(), "shrimp_notepad.txt")


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


def _strip_action(req, pattern):
    """去掉动作词，提取要写入的内容"""
    text = re.sub(pattern, "", req)
    return text.strip(" ，。！!？?：:、\n\t")


def _open_memo():
    """打开记忆文件（复用同一个文件，不反复新建）"""
    if os.path.exists(_MEMO_FILE):
        subprocess.Popen(["notepad.exe", _MEMO_FILE])
    else:
        subprocess.Popen("notepad.exe")


def open_notepad(param: str = ''):
    """
    Windows 记事本管理：根据请求关键词判断动作
    - 读取 → 直接返回内容，不打开窗口
    - 清空 → 清空内容，不打开窗口
    - 追加 → 追加内容并打开窗口
    - 写入/写 → 覆盖写入并打开窗口
    - 打开/空 → 打开记事本
    - 其他 → 当作要写入的内容
    """
    req = (param or '').strip()

    # 1. 读取内容（不打开窗口，避免反复弹窗）
    if any(k in req for k in ["读取", "读一下", "看看内容", "内容是什么", "读出来", "读一遍"]):
        content = _read_content()
        return "记事本内容：\n%s" % content if content else "记事本内容为空"

    # 2. 清空内容（不打开窗口）
    if any(k in req for k in ["清空", "清除", "清掉", "清一下", "清空内容", "删除内容", "删掉内容", "删掉"]):
        _write_content("")
        return "记事本内容已清空"

    # 3. 追加内容（打开窗口展示）
    if "追加" in req or "在后面加" in req or "接着写" in req or "后面写" in req:
        content = _strip_action(req, r"在这个记事本|在记事本中|在记事本里|记事本|追加|在后面加|接着写|后面写|内容|文字")
        if not content:
            return "请告诉我要追加什么内容"
        _write_content(_read_content() + content)
        _open_memo()
        return "已追加到记事本：%s" % content

    # 4. 写入内容（覆盖，打开窗口展示）
    if any(k in req for k in ["写入", "写上", "写", "记下", "记录"]):
        content = _strip_action(req, r"在这个记事本|在记事本中|在记事本里|记事本|写入|写上|写|记下|记录|内容|文字")
        if not content:
            return "请告诉我要写入什么内容"
        _write_content(content)
        _open_memo()
        return "记事本已打开，并成功写入：%s" % content

    # 5. 打开记事本
    if not req or any(k in req for k in ["打开", "开一下", "启动", "开启"]):
        _open_memo()
        return "记事本已打开"

    # 6. 默认：把请求当作要写入的内容
    _write_content(req)
    _open_memo()
    return "记事本已打开，并成功写入：%s" % req
