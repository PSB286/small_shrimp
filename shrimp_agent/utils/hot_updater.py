import os
from datetime import datetime
from config import settings

class HotUpdater:
    def __init__(self):
        self.update_dir = settings.updates_dir
        os.makedirs(self.update_dir, exist_ok=True)

    def trigger_self_healing(self, skill_name: str, error_msg: str):
        """生成修复建议文件（旁路）"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"fix_{skill_name}_{timestamp}.txt"
        filepath = os.path.join(self.update_dir, filename)
        
        content = f"""=== 旁路修复建议 ===
技能名称: {skill_name}
错误信息: {error_msg}
生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

建议:
1. 检查技能代码逻辑
2. 确认依赖库是否安装
3. 查看 skills/{skill_name}.py 文件
"""
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"[HotUpdater] 修复建议: {filepath}")
        return filepath

    def apply_update(self, new_code_path: str):
        """应用更新（预留）"""
        # TODO: 实现版本管理和热切换
        pass