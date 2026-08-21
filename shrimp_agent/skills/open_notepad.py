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

    # 0. 打印/显示文件路径（优先级最高，避免"打印路径"被当成其他动作）
    if "路径" in req and any(k in req for k in ["打印", "显示", "查看", "查", "告诉", "是什么", "在哪", "哪里"]):
        return "记事本文件路径：%s" % _MEMO_FILE

    # 1. 读取内容（不打开窗口，避免反复弹窗）
    if any(k in req for k in ["读取", "读一下", "看看内容", "内容是什么", "读出来", "读一遍"]):
        content = _read_content()
        if content:
            return "记事本内容：\n%s\n（文件路径：%s）" % (content, _MEMO_FILE)
        return "记事本内容为空（文件路径：%s）" % _MEMO_FILE

    # 2. 清空内容（不打开窗口）
    if any(k in req for k in ["清空", "清除", "清掉", "清一下", "清空内容", "删除内容", "删掉内容", "删掉"]):
        _write_content("")
        return "记事本内容已清空（文件路径：%s）" % _MEMO_FILE

    # 3. 追加内容（打开窗口展示）
    if any(k in req for k in ["追加", "在后面加", "接着写", "后面写", "加上"]):
        content = _strip_action(req, r"在这个记事本|在记事本中|在记事本里|记事本|追加|在后面加|接着写|后面写|加上|内容|文字")
        if not content:
            return "请告诉我要追加什么内容"
        _write_content(_read_content() + content)
        _open_memo()
        return "已追加到记事本：%s（文件路径：%s）" % (content, _MEMO_FILE)

    # 4. 写入内容（覆盖，打开窗口展示）
    if any(k in req for k in ["写入", "写上", "写", "记下", "记录", "改成"]):
        content = _strip_action(req, r"在这个记事本|在记事本中|在记事本里|记事本|写入|写上|写|记下|记录|改成|内容|文字")
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
