import os
import platform
import subprocess

def open_computer(param: str = '') -> str:
    """打开系统计算器应用"""
    try:
        system = platform.system()
        if system == 'Windows':
            os.system('calc')
        elif system == 'Darwin':  # macOS
            subprocess.Popen(['open', '-a', 'Calculator'])
        elif system == 'Linux':
            subprocess.Popen(['gnome-calculator'])
        else:
            return f'不支持的操作系统: {system}'
        return '计算器已成功打开！'
    except Exception as e:
        return f'打开计算器失败: {str(e)}'

__skill_meta__ = {
    "description": "打开系统计算器应用",
    "params": {}
}