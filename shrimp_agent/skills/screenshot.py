try:
    from PIL import ImageGrab
    import datetime
    import os

    def screenshot():
        now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screenshot_{now}.png'
        ImageGrab.grab().save(filename)
        try:
            os.startfile(filename)
        except AttributeError:
            import subprocess
            if os.name == 'posix':
                subprocess.run(['open', filename])
            else:
                subprocess.run(['xdg-open', filename])
        return f'截图已保存并打开: {filename}'
except ImportError:
    def screenshot():
        return "错误：未安装 Pillow，请执行 'pip install pillow' 后重试。"