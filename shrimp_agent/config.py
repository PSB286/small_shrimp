import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    api_key: str = os.getenv("API_KEY", "sk-xxx")
    api_url: str = "https://api.deepseek.com/v1/chat/completions"
    max_steps: int = 50
    max_retries: int = 3
    memory_file: str = "data/memory.json"
    error_log_file: str = "data/error_log.json"
    skills_dir: str = "skills"
    updates_dir: str = "updates"
    logs_dir: str = "logs"
    debug: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()