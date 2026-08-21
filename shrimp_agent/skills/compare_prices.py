import os
import re
import json
import csv
import datetime

__skill_meta__ = {
    "description": "比价助手：对比淘宝、闲鱼、京东价格，支持价格筛选、历史趋势、批量比价与CSV导出",
    "params": {
        "param": "用户的完整请求，如：搜索 iPhone15 最高价5000 全新；或：比价 商品A、商品B 导出"
    }
}

# 历史价格记录文件（趋势分析用）
_HISTORY_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "shrimp_price_history.json")

# 使用说明
_HELP = """【比价助手使用说明】
1. 搜索/比价 <商品名> → 对比淘宝、闲鱼、京东价格
2. 筛选参数（可选）：
   • 最高价/上限 3000  → 只看3000元以下
   • 最低价/下限 1000  → 只看1000元以上
   • 全新 / 二手      → 只看全新或只看二手
3. 历史/趋势 → 查看该商品价格走势与购买建议
4. 导出/CSV → 把比价结果导出成CSV文件
5. 批量：商品名用 、 或 ， 分隔（如：比价 耳机、手表、手环）
示例：搜索 iPhone15 最高价5000 全新 导出"""


def _load_history():
    try:
        if os.path.exists(_HISTORY_FILE):
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_history(history):
    try:
        with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _get_mock_prices(product):
    """生成稳定的模拟价格（接入真实API需平台凭据，此处保留演示）"""
    seed = sum(ord(c) for c in product)
    taobao_base = 80 + (seed % 40)
    return {
        "淘宝": [
            {"title": "%s 官方旗舰版" % product, "price": taobao_base, "condition": "new"},
            {"title": "%s 标准版" % product, "price": taobao_base - 5, "condition": "new"},
            {"title": "%s 促销特惠" % product, "price": taobao_base - 12, "condition": "new"},
        ],
        "闲鱼": [
            {"title": "%s 95新(二手)" % product, "price": int(taobao_base * 0.55), "condition": "used"},
            {"title": "%s 9成新(二手)" % product, "price": int(taobao_base * 0.55) - 10, "condition": "used"},
            {"title": "%s 几乎全新" % product, "price": int(taobao_base * 0.55) + 15, "condition": "used"},
        ],
        "京东": [
            {"title": "%s 京东自营" % product, "price": taobao_base + 15, "condition": "new"},
            {"title": "%s 京东优选" % product, "price": taobao_base + 7, "condition": "new"},
            {"title": "%s 京东PLUS版" % product, "price": taobao_base + 10, "condition": "new"},
        ],
    }


def _parse_filters(param):
    """解析筛选参数：最高价/最低价/全新/二手"""
    filters = {}
    m = re.search(r'(?:最高价|上限|不超过|小于|低于)\s*[:：]?\s*(\d+)', param)
    if m:
        filters["max_price"] = int(m.group(1))
    m = re.search(r'(?:最低价|下限|不低于|大于|高于)\s*[:：]?\s*(\d+)', param)
    if m:
        filters["min_price"] = int(m.group(1))
    if "全新" in param:
        filters["condition"] = "new"
    elif "二手" in param or "闲置" in param:
        filters["condition"] = "used"
    return filters


def _extract_products(param):
    """提取商品名：先剥筛选短语（含数字），再去指令词/功能词，按分隔符拆分"""
    text = re.sub(r'^(?:搜索|比价|查|查询|对比|帮我|看看|找一下|搜一下|比较)\s*', '', param)
    # 先剥带数字的筛选短语（最高价200 / 上限3000 / 最低价100…）
    text = re.sub(r'(?:最高价|上限|不超过|小于|低于|最低价|下限|不低于|大于|高于)\s*[:：]?\s*\d+', '', text)
    # 再剥无数字的功能词
    text = re.sub(
        r'(最高价|最低价|上限|下限|不超过|不低于|大于|小于|高于|全新|二手|闲置|'
        r'导出|CSV|表格|存到文件|历史|趋势|走势|分析|价格|多少钱|报价)',
        '', text)
    text = text.strip('，。！？、,.!?;；:： ')
    if not text:
        return []
    return [p.strip() for p in re.split(r'[，,、;；和&]', text) if p.strip()]


def _filter_items(platform_prices, filters):
    """按筛选条件过滤商品"""
    result = []
    for platform, items in platform_prices.items():
        for item in items:
            price = item["price"]
            if filters.get("max_price") is not None and price > filters["max_price"]:
                continue
            if filters.get("min_price") is not None and price < filters["min_price"]:
                continue
            if filters.get("condition") and item.get("condition") != filters["condition"]:
                continue
            result.append((platform, item["title"], price))
    return result


def _lowest_price(product):
    """商品今日最低价（用于历史记录）"""
    all_items = _filter_items(_get_mock_prices(product), {})
    if not all_items:
        return 0
    return min(i[2] for i in all_items)


def _trend_advice(product, history):
    """基于历史价格给出购买建议"""
    entries = history.get(product, [])
    if len(entries) < 2:
        return "📈 历史数据不足，无法分析趋势（多查几次就能看走势了）"
    today_price = entries[-1]["price"]
    prev_price = entries[0]["price"]
    diff = today_price - prev_price
    trend = "↑上涨" if diff > 0 else ("↓下降" if diff < 0 else "→持平")
    lines = ["📈 价格趋势（%s）：" % product]
    points = entries[-5:]
    lines.append("   " + " → ".join("¥%d" % e["price"] for e in points))
    lines.append("   %s：从 ¥%d 到 ¥%d（%s ¥%d）" % (trend, prev_price, today_price,
                                                  "涨了" if diff > 0 else ("降了" if diff < 0 else "不变"), abs(diff)))
    if diff < 0:
        lines.append("💡 价格在降，建议：**可以入手**或再等等")
    elif diff > 0:
        lines.append("💡 价格在涨，建议：**观望**，等回落再买")
    else:
        lines.append("💡 价格平稳，按需购买即可")
    return "\n".join(lines)


def _export_csv(rows):
    """导出比价结果为CSV文件，返回路径"""
    path = os.path.join(os.environ.get("TEMP", "/tmp"),
                        "shrimp_prices_%s.csv" % datetime.datetime.now().strftime("%H%M%S"))
    try:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["商品", "平台", "标题", "价格(¥)"])
            for row in rows:
                writer.writerow(row)
        return path
    except Exception as e:
        return "导出失败: %s" % e


def compare_prices(param: str = ''):
    """
    比价助手：对比各平台价格，支持 筛选 / 历史趋势 / 批量 / CSV导出。
    """
    req = (param or "").strip()

    if not req:
        return "您好！请告诉我想搜索的商品，例如：\n「搜索 iPhone15」或「比价 小米手环 最高价300 二手」\n（输入「比价助手 说明」查看全部用法）"

    if any(k in req for k in ["提示", "帮助", "说明", "怎么用", "用法"]):
        return _HELP

    filters = _parse_filters(req)
    want_history = any(k in req for k in ["历史", "趋势", "走势", "分析"])
    want_export = any(k in req for k in ["导出", "CSV", "表格", "存到文件"])

    products = _extract_products(req)
    if not products:
        return "请告诉我要搜索的商品名，如：搜索 iPhone15（可加 最高价/最低价/全新/二手/导出）"

    lines = []
    all_rows = []
    history = _load_history()

    for product in products:
        lines.append("=" * 42)
        lines.append("📊 【%s】各平台价格" % product)

        all_items = _filter_items(_get_mock_prices(product), filters)
        if not all_items:
            lines.append("   （没有符合筛选条件的商品）")
        else:
            for platform, title, price in all_items:
                lines.append("   • [%s] %s：¥%d" % (platform, title, price))
                all_rows.append([product, platform, title, price])

            all_items.sort(key=lambda x: x[2])
            lowest, highest = all_items[0], all_items[-1]
            lines.append("   ─────────────")
            lines.append("   💰 最低：¥%d（%s）  最高：¥%d（%s）  差价：¥%d"
                         % (lowest[2], lowest[0], highest[2], highest[0], highest[2] - lowest[2]))
            if filters:
                lines.append("   🔍 已按筛选条件过滤")

        if want_history:
            lines.append("")
            lines.append(_trend_advice(product, history))

        # 记录今日最低价
        entry = history.setdefault(product, [])
        entry.append({"date": datetime.date.today().isoformat(), "price": _lowest_price(product)})
        history[product] = entry[-60:]

    if want_export and all_rows:
        path = _export_csv(all_rows)
        lines.append("")
        lines.append("📁 已导出CSV：" + path)

    _save_history(history)

    lines.append("")
    lines.append("⚠️ 注：价格为模拟数据，接入真实平台API需要对应凭据（可用「增强技能」扩展）")
    return "\n".join(lines)
