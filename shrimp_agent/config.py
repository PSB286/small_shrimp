import os
import sys

try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover - compatibility for minimal local envs
    from pydantic import BaseSettings

from dotenv import load_dotenv

# 以 config.py 所在目录为项目根，彻底摆脱"必须在 main.py 目录运行"的限制
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 保证从任何工作目录都能 import core/hardware/templates 等包
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# 优先加载项目根目录下的 .env
load_dotenv(os.path.join(BASE_DIR, ".env"))
load_dotenv()  # 兼容旧习惯：也从当前工作目录加载


def _abs(path: str) -> str:
    """把相对路径解析为基于项目根目录的绝对路径"""
    if os.path.isabs(path):
        return path
    return os.path.join(BASE_DIR, path)


class Settings(BaseSettings):
    api_key: str = os.getenv("API_KEY", "sk-xxx")
    api_url: str = "https://api.deepseek.com/v1/chat/completions"
    max_steps: int = 50
    max_retries: int = 3

    # ---- 路径（全部自动解析为绝对路径） ----
    base_dir: str = BASE_DIR
    memory_file: str = _abs("memory/permanent_memory.json")
    error_log_file: str = _abs("data/error_log.json")
    skills_dir: str = _abs("skills")
    templates_dir: str = _abs("templates")
    updates_dir: str = _abs("updates")
    logs_dir: str = _abs("logs")
    capabilities_file: str = _abs("data/capabilities.json")
    environment_manifest: str = _abs("environment.json")

    # ---- 环境自适应相关配置 ----
    hardware_mode: str = os.getenv("HARDWARE_MODE", "auto")  # auto | sim | real
    max_optimize_per_day: int = int(os.getenv("MAX_OPTIMIZE_PER_DAY", "10"))
    max_generate_rounds: int = int(os.getenv("MAX_GENERATE_ROUNDS", "3"))
    auto_bootstrap: bool = True          # 启动时按能力清单自动生成基础技能
    auto_create_skill: bool = True       # 学习器发现重复需求时自动创建技能

    debug: bool = False

    class Config:
        env_file = ".env"


settings = Settings()
