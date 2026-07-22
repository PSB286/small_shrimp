import logging
import os
from datetime import datetime
from config import settings

# 创建日志目录
os.makedirs(settings.logs_dir, exist_ok=True)

log_file = os.path.join(settings.logs_dir, f"shrimp_{datetime.now().strftime('%Y%m%d')}.log")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("shrimp")