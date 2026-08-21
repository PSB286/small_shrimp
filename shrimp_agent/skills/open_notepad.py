import os
import subprocess
import tempfile
import time

__skill_meta__ = {
    "description": "打开 Windows 记事本程序，并可选择在记事本中写入指定的文字内容，支持追加写入同一记事本",
    "params": {
        "param": {
            "type": "string",
            "description": "要写入记事本的文字内容，为空时仅打开记事本"
        }
    }
}

# 用于保存当前记事本对应的临时文件路径
_last_temp_file = None

def open_notepad(param: str = ''):
    """
    打开 Windows 记事本，若 param 非空则同时在记事本中写入指定文字。
    支持追加写入同一个记事本（若记事本已打开则复用同一个临时文件）。
    
    Args:
        param: 要写入的文字内容，为空时仅打开记事本
    
    Returns:
        操作结果描述字符串
    """
    global _last_temp_file
    
    try:
        if not param:
            # 仅打开记事本（若已有临时文件则打开它，否则新开）
            if _last_temp_file and os.path.exists(_last_temp_file):
                subprocess.Popen(['notepad.exe', _last_temp_file])
                return f"记事本已打开（复用文件：{_last_temp_file}）"
            else:
                subprocess.Popen('notepad.exe')
                return "记事本已打开"
        
        # 需要写入文字
        if _last_temp_file and os.path.exists(_last_temp_file):
            # 复用已有临时文件，追加内容
            with open(_last_temp_file, 'a', encoding='utf-8') as f:
                f.write(param)
            temp_file_path = _last_temp_file
        else:
            # 创建新的临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                f.write(param)
                temp_file_path = f.name
            _last_temp_file = temp_file_path
        
        # 用记事本打开临时文件
        subprocess.Popen(['notepad.exe', temp_file_path])
        
        return f"记事本已打开，并成功写入文字：{param}"
            
    except Exception as e:
        return f"操作失败：{str(e)}"