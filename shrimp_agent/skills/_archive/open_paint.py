import subprocess
import sys

def open_paint(param: str = '') -> str:
    """打开系统图画应用"""
    try:
        if sys.platform == 'win32':
            # Windows 系统使用 mspaint 命令
            subprocess.Popen(['mspaint'])
        elif sys.platform == 'darwin':
            # macOS 系统使用 open 命令打开预览
            subprocess.Popen(['open', '-a', 'Preview'])
        else:
            # Linux 系统尝试常见画图应用
            for app in ['kolourpaint', 'pinta', 'gimp']:
                try:
                    subprocess.Popen([app])
                    break
                except FileNotFoundError:
                    continue
            else:
                return '未找到可用的画图应用'
        return '图画应用已打开'
    except Exception as e:
        return f'打开失败：{str(e)}'

__skill_meta__ = {
    "description": "打开系统图画应用",
    "params": {}
}