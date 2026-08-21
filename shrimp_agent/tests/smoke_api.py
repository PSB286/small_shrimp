# -*- coding: utf-8 -*-
"""HTTP 冒烟测试：以正确 UTF-8 编码调用各接口"""
import json
import urllib.request

BASE = "http://127.0.0.1:8765"


def post(path, data):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


print("[1] 执行跳舞 →", post("/chat", {"message": "执行跳舞"})["reply"][:80])
print("[2] 执行摇尾巴 →", post("/chat", {"message": "执行摇尾巴"})["reply"][:80])
print("[3] 新增技能:打招呼 →", post("/chat", {"message": "新增技能：跟我打招呼"})["reply"][:80])
print("[4] 记住我叫小明 →", post("/chat", {"message": "我叫小明"})["reply"][:60])
print("[5] 我是谁 →", post("/chat", {"message": "我是谁"})["reply"][:60])
print("[6] 查看记忆 →", post("/chat", {"message": "查看记忆"})["reply"][:100])
print("[7] 列出技能 →", post("/chat", {"message": "列出技能"})["reply"][:100])
print("[8] 技能统计 →", json.dumps(get("/skills/stats")["stats"].get("dance", {}), ensure_ascii=False))
