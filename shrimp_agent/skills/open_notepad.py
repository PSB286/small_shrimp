import subprocess

__skill_meta__ = {
    "description": "打开 Windows 记事本程序",
    "params": {"param": {"type": "string", "description": "可选参数，为空即可"}}
}

def open_notepad(param: str = ''):
    try:
        subprocess.Popen('notepad.exe')
        return "记事本已打开"
    except Exception as e:
        return f"打开失败: {e}"