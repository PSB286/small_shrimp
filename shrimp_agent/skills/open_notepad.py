import os
import subprocess
import tempfile

__skill_meta__ = {
    "description": "打开 Windows 记事本程序，并可选择在记事本中写入指定的文字内容",
    "params": {
        "param": {
            "type": "string",
            "description": "要写入记事本的文字内容，为空时仅打开记事本"
        }
    }
}

def open_notepad(param: str = ''):
    """
    打开 Windows 记事本，若 param 非空则同时在记事本中写入指定文字。
    
    Args:
        param: 要写入的文字内容，为空时仅打开记事本
    
    Returns:
        操作结果描述字符串
    """
    try:
        if not param:
            # 仅打开记事本
            subprocess.Popen('notepad.exe')
            return "记事本已打开"
        
        # 写入文字：创建临时文件并通过记事本打开
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            f.write(param)
            temp_file_path = f.name
        
        # 用记事本打开临时文件
        subprocess.Popen(['notepad.exe', temp_file_path])
        
        return f"记事本已打开，并成功写入文字：{param}"
            
    except Exception as e:
        return f"操作失败：{str(e)}"