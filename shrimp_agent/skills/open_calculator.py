import subprocess
import sys

def open_calculator() -> str:
    """打开系统计算器应用"""
    try:
        if sys.platform == "win32":
            subprocess.Popen(["calc.exe"])
            return "计算器已打开"
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Calculator"])
            return "计算器已打开"
        elif sys.platform == "linux":
            subprocess.Popen(["gnome-calculator"])
            return "计算器已打开"
        else:
            return "不支持的操作系统"
    except Exception as e:
        return f"打开计算器失败: {str(e)}"

__skill_meta__ = {
    "description": "打开系统计算器应用",
    "params": {}
}