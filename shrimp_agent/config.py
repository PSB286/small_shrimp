"""
配置模块 - 纯 Python 实现（不依赖 pydantic，便于轻量环境/手机 Termux 部署）

所有配置从环境变量读取（.env 由 python-dotenv 加载），
没有 pydantic 也能跑，安装更轻、无编译依赖。
"""

import os
import sys

from dotenv import load_dotenv

# 以 config.py 所在目录为项目根，彻底摆脱"必须在 main.py 目录运行"的限制
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 保证从任何工作目录都能 import core/hardware/templates 等包
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 优先加载项目根目录下的 .env，再兼容当前工作目录
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()


def _abs(path: str) -> str:
    """把相对路径解析为基于项目根目录的绝对路径"""
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    """轻量配置：全部从环境变量读取"""

    def __init__(self):
        self.api_key: str = os.getenv("API_KEY", "sk-xxx")
        self.api_url: str = os.getenv("API_URL", "https://api.deepseek.com/v1/chat/completions")
        self.max_steps: int = _env_int("MAX_STEPS", 50)
        self.max_retries: int = _env_int("MAX_RETRIES", 3)

        # ---- 路径（全部自动解析为绝对路径） ----
        self.base_dir: str = BASE_DIR
        self.memory_file: str = _abs("memory/permanent_memory.json")
        self.error_log_file: str = _abs("data/error_log.json")
        self.skills_dir: str = _abs("skills")
        self.templates_dir: str = _abs("templates")
        self.updates_dir: str = _abs("updates")
        self.logs_dir: str = _abs("logs")
        self.capabilities_file: str = _abs("data/capabilities.json")
        self.environment_manifest: str = _abs("environment.json")

        # ---- 环境自适应相关配置 ----
        self.hardware_mode: str = os.getenv("HARDWARE_MODE", "auto")  # auto | sim | real
        self.max_optimize_per_day: int = _env_int("MAX_OPTIMIZE_PER_DAY", 10)
        self.max_generate_rounds: int = _env_int("MAX_GENERATE_ROUNDS", 3)
        self.auto_bootstrap: bool = os.getenv("AUTO_BOOTSTRAP", "1") == "1"
        self.auto_create_skill: bool = os.getenv("AUTO_CREATE_SKILL", "1") == "1"

        self.debug: bool = os.getenv("DEBUG", "0") == "1"


settings = Settings()
