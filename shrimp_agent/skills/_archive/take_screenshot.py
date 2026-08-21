import subprocess
import os
from datetime import datetime

def take_screenshot(param: str = '') -> str:
    """截取当前屏幕截图并保存到指定位置"""
    try:
        # 生成文件名（带时间戳）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{timestamp}.png'
        
        # 保存路径（当前目录）
        save_path = os.path.join(os.getcwd(), filename)
        
        # 使用系统工具截图（macOS/Linux/Windows 兼容）
        system = os.name
        if system == 'nt':  # Windows
            # 使用 PowerShell 截图
            ps_script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            $bitmap.Save('{save_path}')
            '''
            subprocess.run(['powershell', '-Command', ps_script], check=True)
        elif system == 'posix':  # macOS/Linux
            if os.path.exists('/usr/sbin/screencapture'):  # macOS
                subprocess.run(['screencapture', save_path], check=True)
            else:  # Linux
                subprocess.run(['import', save_path], check=True)
        
        return f'✅ 截图已保存到：{save_path}'
    except Exception as e:
        return f'❌ 截图失败：{str(e)}'

__skill_meta__ = {
    "description": "截取当前屏幕截图并保存为PNG文件",
    "params": {}
}