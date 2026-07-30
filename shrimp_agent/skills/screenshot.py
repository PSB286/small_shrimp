import pyautogui
from datetime import datetime

def screenshot(param: str = '') -> str:
    """截取当前屏幕并保存为图片文件"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{timestamp}.png'
        pyautogui.screenshot(filename)
        return f'截图已保存为 {filename}'
    except Exception as e:
        return f'截图失败：{str(e)}'

__skill_meta__ = {
    "description": "截取当前屏幕并保存为PNG图片，文件名包含时间戳",
    "params": {}
}