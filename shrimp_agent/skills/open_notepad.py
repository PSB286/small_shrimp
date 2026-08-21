import subprocess
import os
import sys

__skill_meta__ = {
    "description": "打开Windows记事本程序，可输入指定内容自动写入（可选，通过命令行方式）。",
    "params": {
        "param": "用户的完整请求文本，例如：'打开记事本' 或 '打开记事本并写入你好'"
    }
}

def open_notepad(param: str = ''):
    """
    打开 Windows 记事本程序。
    如果 param 中包含 '写入' 或 '输入'，则尝试用记事本打开后自动键入内容（仅支持英文/数字，中文可能因输入法问题受限）。
    实际中更稳妥的方式是直接用 notepad 打开一个临时文件并填入内容。
    """
    try:
        # 提取要写入的内容（如果用户提到写入/输入）
        content = ''
        lower_param = param.lower()
        for keyword in ['写入', '输入', '内容为']:
            if keyword in param:
                # 取关键词之后的部分作为内容
                content = param.split(keyword, 1)[1].strip()
                break

        # 如果没有内容，直接打开记事本
        if not content:
            os.startfile('notepad.exe')
            return "已打开记事本程序。"

        # 如果有内容，创建一个临时txt文件并写入内容，然后用记事本打开
        temp_path = os.path.join(os.environ.get('TEMP', '.'), 'ggb_notepad_temp.txt')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        os.startfile(temp_path)
        return f"已打开记事本并写入内容：{content}"

    except Exception as e:
        return f"打开记事本失败：{str(e)}"