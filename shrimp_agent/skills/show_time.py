import datetime

def show_time(param: str = ''):
    """显示当前日期和时间"""
    now = datetime.datetime.now()
    return f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M:%S')}"

__skill_meta__ = {"description": "显示当前日期和时间", "params": {}, "tier": 1}
