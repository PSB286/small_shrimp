import requests

def web_search(param: str = ''):
    """联网搜索并返回摘要（必应搜索，带超时重试）"""
    if not param:
        return "请提供搜索关键词"

    # 必应搜索URL（使用简单HTML查询）
    url = f"https://www.bing.com/search?q={param}&format=rss"

    # 超时重试逻辑：最多尝试3次，每次超时5秒
    for attempt in range(3):
        try:
            data = requests.get(url, timeout=5)
            data.raise_for_status()
            break
        except Exception as e:
            if attempt == 2:
                return f"搜索失败：{e}"
            continue

    try:
        # 解析RSS格式的搜索结果
        import xml.etree.ElementTree as ET
        root = ET.fromstring(data.text)
        items = root.findall('.//item')

        if items:
            # 取前3条结果摘要
            results = []
            for item in items[:3]:
                title = item.find('title').text if item.find('title') is not None else ''
                desc = item.find('description').text if item.find('description') is not None else ''
                if title or desc:
                    results.append(f"{title}: {desc[:150]}")
            if results:
                return f"搜索结果：\n" + "\n".join(results)

        return f"没有找到「{param}」的摘要信息"
    except Exception as e:
        return f"解析搜索结果失败：{e}"

__skill_meta__ = {"description": "联网搜索并返回摘要（必应搜索，带超时重试）", "params": {"param": "搜索关键词"}, "tier": 1}