from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from module._base import *
from pydantic import BaseModel
import logging
from logging.handlers import RotatingFileHandler
from views.common import api_common
from views.detection import register_detection
from views.config import api_config
from views.log import api_log
import sys


app = FastAPI()
logger = logging.getLogger(__name__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 替换为您允许的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# app.mount("/datasets",StaticFiles(directory="datasets"),name="datasets")
class UploadRequest(BaseModel):
    storage_path: str  # 前端指定的存储路径
def setup_logging():
    """配置日志，保存到文件和控制台"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.encoding = "utf-8"
    logger.addHandler(console_handler)
    # 文件输出（日志切割）
    log_dir = os.path.join("logs")  # 日志目录
    os.makedirs(log_dir, exist_ok=True)  # 自动创建目录
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# 初始化日志
setup_logging() 
app.include_router(api_common,tags=["COMMON"])  
register_detection(app)
app.include_router(api_config,tags=["CONFIG"])
app.include_router(api_log,tags=["LOG"])