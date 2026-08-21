import requests

def web_search(param: str = ''):
    """联网搜索并返回摘要"""
    if not param:
        return "请提供搜索关键词"
    try:
        url = f"https://api.duckduckgo.com/?q={param}&format=json&no_html=1"
        data = requests.get(url, timeout=8).json()
        abstract = data.get("Abstract", "")
        if abstract:
            return f"搜索结果：{abstract[:200]}"
        topics = data.get("RelatedTopics", [])
        for t in topics[:3]:
            if isinstance(t, dict) and t.get("Text"):
                return f"搜索结果：{t['Text'][:200]}"
        return f"没有找到「{param}」的摘要信息"
    except Exception as e:
        return f"搜索失败：{e}"

__skill_meta__ = {"description": "联网搜索并返回摘要", "params": {"param": "搜索关键词"}, "tier": 1}
