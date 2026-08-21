"""
技能管理器 - 加载、执行、管理技能
"""

import os
import importlib.util
import inspect
import json
import shutil
import logging
from config import settings

# 配置 logger
logger = logging.getLogger(__name__)


class SkillManager:
    def __init__(self):
        # 使用绝对路径避免相对路径问题
        self.skills_dir = os.path.abspath(settings.skills_dir)
        self.skills = {}
        logger.info(f"SkillManager 初始化，技能目录: {self.skills_dir}")
        self.load_skills()

    def load_skills(self):
        """加载 skills/ 目录下的所有技能"""
        logger.info(f"开始加载技能，目录: {self.skills_dir}")
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            logger.info(f"创建技能目录: {self.skills_dir}")
            return

        # 清空现有技能
        self.skills = {}
        for filename in os.listdir(self.skills_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                skill_name = filename[:-3]
                filepath = os.path.join(self.skills_dir, filename)
                logger.debug(f"尝试加载技能: {skill_name}, 文件: {filepath}")
                try:
                    spec = importlib.util.spec_from_file_location(skill_name, filepath)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    if hasattr(module, skill_name) and callable(getattr(module, skill_name)):
                        func = getattr(module, skill_name)
                        sig = inspect.signature(func)
                        params = {p: "any" for p in sig.parameters}
                        meta = getattr(module, "__skill_meta__", {})
                        description = meta.get("description", f"技能 {skill_name}")
                        tier = meta.get("tier", 2)  # 0=系统核心 1=环境基础 2=学习生成

                        self.skills[skill_name] = {
                            "func": func,
                            "description": description,
                            "params": params,
                            "filepath": filepath,
                            "tier": tier
                        }
                        logger.info(f"[SkillManager] 已加载: {skill_name} (路径: {filepath})")
                    else:
                        logger.warning(f"[SkillManager] 文件 {filename} 没有导出同名函数 {skill_name}")
                except Exception as e:
                    logger.error(f"[SkillManager] 加载 {skill_name} 失败: {e}", exc_info=True)

        logger.info(f"加载完成，共加载 {len(self.skills)} 个技能")

    def reload_skills(self):
        """重新加载所有技能"""
        logger.info("重新加载所有技能...")
        self.load_skills()

    def execute(self, skill_name: str, params: dict):
        """执行技能"""
        if skill_name not in self.skills:
            return f"[错误] 技能 {skill_name} 不存在"

        try:
            result = self.skills[skill_name]["func"](**params)
            return result
        except Exception as e:
            return f"[错误] 执行 {skill_name} 失败: {str(e)}"

    def get_skills_info(self):
        """获取所有已启用技能信息（供 API 使用）"""
        return {name: {
            "description": info["description"],
            "params": info["params"]
        } for name, info in self.skills.items()}

    def get_all_skills_info(self):
        """
        获取所有技能信息（含已禁用的 .py.disabled），带 enabled 标记。
        供前端技能管理弹窗展示开/关状态。
        """
        info = self.get_skills_info()
        for name in info:
            info[name]["enabled"] = True

        # 扫描已禁用的技能文件
        if os.path.isdir(self.skills_dir):
            for filename in sorted(os.listdir(self.skills_dir)):
                if filename.endswith(".py.disabled"):
                    name = filename[: -len(".py.disabled")]
                    info[name] = {
                        "description": self._read_disabled_description(filename),
                        "params": {},
                        "enabled": False,
                    }
        return info

    def _read_disabled_description(self, filename):
        """读取已禁用技能的描述（尽力而为）"""
        filepath = os.path.join(self.skills_dir, filename)
        try:
            spec = importlib.util.spec_from_file_location("_disabled_" + filename, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            meta = getattr(module, "__skill_meta__", {})
            return meta.get("description", filename) if isinstance(meta, dict) else filename
        except Exception:
            return filename

    def get_skill_code(self, skill_name: str) -> str:
        """获取技能源码"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def skill_exists(self, skill_name: str) -> bool:
        """检查技能是否存在（启用或禁用状态都算）"""
        if skill_name in self.skills:
            return True
        return os.path.exists(os.path.join(self.skills_dir, f"{skill_name}.py")) or \
               os.path.exists(os.path.join(self.skills_dir, f"{skill_name}.py.disabled"))

    def get_skill_tier(self, skill_name: str) -> int:
        """获取技能级别（0=系统核心 1=环境基础 2=学习生成）"""
        info = self.skills.get(skill_name)
        return info.get("tier", 2) if info else 2

    def modify_skill(self, skill_name: str, new_code: str) -> str:
        """修改技能代码并重新加载"""
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")

        if not os.path.exists(filepath):
            return f"[错误] 技能 {skill_name} 不存在"

        try:
            backup_path = filepath + ".backup"
            shutil.copy2(filepath, backup_path)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_code)

            self.reload_skills()
            return f"[成功] 技能 {skill_name} 已修改并重新加载"
        except Exception as e:
            return f"[错误] 修改技能失败: {str(e)}"

    def delete_skill(self, skill_name: str) -> str:
        """删除技能（同时移除匹配规则）"""
        logger.info(f"=== 开始删除技能: {skill_name} ===")
        logger.info(f"当前技能字典: {list(self.skills.keys())}")

        if skill_name not in self.skills:
            logger.warning(f"技能 {skill_name} 不在技能字典中")
            return f"[错误] 技能 {skill_name} 不存在"

        skill_info = self.skills[skill_name]
        filepath = skill_info.get("filepath")
        logger.info(f"技能信息: {skill_info}")
        logger.info(f"文件路径 (相对): {filepath}")

        if not filepath:
            logger.error("filepath 为空")
            return f"[错误] 技能文件路径缺失"

        abs_path = os.path.abspath(filepath)
        logger.info(f"绝对路径: {abs_path}")
        logger.info(f"当前工作目录: {os.getcwd()}")

        if not os.path.exists(abs_path):
            logger.error(f"文件不存在: {abs_path}")
            return f"[错误] 技能文件不存在：{abs_path}"

        try:
            logger.info(f"执行 os.remove('{abs_path}') ...")
            os.remove(abs_path)
            logger.info("os.remove 执行成功")

            # 验证是否真的删除
            if os.path.exists(abs_path):
                logger.warning(f"删除后文件仍然存在: {abs_path}")
                # 尝试再次删除
                try:
                    os.remove(abs_path)
                    logger.info("第二次删除成功")
                except Exception as e2:
                    logger.error(f"第二次删除失败: {e2}", exc_info=True)
                    return f"[警告] 文件删除失败，可能被占用：{abs_path}"
            else:
                logger.info("验证通过：文件已不存在")

            # 从内存中移除
            del self.skills[skill_name]
            logger.info(f"从技能字典移除: {skill_name}")

            # 重新加载（保持一致性）
            self.reload_skills()
            logger.info("重新加载技能完成")

            # 移除匹配规则
            self._remove_mapping(skill_name)
            logger.info("移除匹配规则完成")

            logger.info(f"=== 技能 {skill_name} 删除成功 ===")
            return f"[成功] 技能 {skill_name} 已删除"
        except Exception as e:
            logger.error(f"删除技能异常: {e}", exc_info=True)
            return f"[错误] 删除技能失败: {str(e)}"

    def _remove_mapping(self, skill_name: str):
        """尝试从 skill_mappings.json 中移除关联规则"""
        try:
            from core.skill_matcher import SkillMatcher
            matcher = SkillMatcher()
            matcher.remove_mapping_by_skill(skill_name)
            logger.info(f"从匹配器中移除 {skill_name} 成功")
        except ImportError:
            logger.warning("未找到 SkillMatcher，跳过移除映射")
        except Exception as e:
            logger.error(f"移除匹配规则失败: {e}", exc_info=True)

    def list_skills_formatted(self) -> str:
        """格式化输出技能列表"""
        if not self.skills:
            return "当前没有任何技能"

        lines = ["【当前技能列表】"]
        for name, info in self.skills.items():
            lines.append(f"  📦 {name} : {info['description']}")
        return "\n".join(lines)

    def toggle_skill(self, skill_name: str, enabled: bool):
        """
        切换技能启用/禁用状态。
        用 os.replace（覆盖式）避免 Windows 上目标已存在时报 WinError183。
        返回 (success, message)
        """
        filepath = os.path.join(self.skills_dir, f"{skill_name}.py")
        disabled_path = os.path.join(self.skills_dir, f"{skill_name}.py.disabled")

        try:
            if enabled:
                if not os.path.exists(disabled_path):
                    return False, f"技能 {skill_name} 不在禁用状态（无 {skill_name}.py.disabled）"
                os.replace(disabled_path, filepath)
                self.reload_skills()
                return True, f"技能 {skill_name} 已启用"
            else:
                if not os.path.exists(filepath):
                    return False, f"技能 {skill_name} 不存在或已禁用"
                os.replace(filepath, disabled_path)
                self.reload_skills()
                return True, f"技能 {skill_name} 已禁用"
        except Exception as e:
            logger.error(f"[SkillManager] 切换技能 {skill_name} 失败: {e}", exc_info=True)
            return False, f"切换失败: {str(e)}"