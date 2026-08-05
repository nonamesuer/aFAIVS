from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from module._base import *
from pydantic import BaseModel
import logging
from logging.handlers import RotatingFileHandler
from views.common import api_common
from views.detection import register_detection
from views.config import api_config,api_config_public
from views.log import api_log
from views.auth import api_auth
from views.results import api_results
import sys
from pathlib import Path
import subprocess
import os
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
    log_dir = os.path.join(PARENT_DIR, "logs")  # 日志目录
    os.makedirs(log_dir, exist_ok=True)  # 自动创建目录
    file_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

def main():
    # 初始化日志
    setup_logging() 
    # 调整模块查找路径
    if getattr(sys, 'frozen', False):
        # 如果是打包后的可执行文件
        base_dir = Path(sys.executable).parent
        sys.path.insert(0, str(base_dir))
    from fastapi import FastAPI
    # from pydantic import BaseModel
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 替换为您允许的域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )



    app.include_router(api_common,tags=["COMMON"])  
    app.include_router(api_auth,tags=["AUTH"])
    register_detection(app)
    app.include_router(api_config,tags=["CONFIG"])
    app.include_router(api_config_public,tags=["PUBLIC CONFIG"])
    app.include_router(api_log,tags=["LOG"])
    app.include_router(api_results,tags=["RESULTS"])
    # 挂载静态文件
    vue_dist_path = Path(__file__).parent / "static/dist"
    app.mount("", StaticFiles(directory=vue_dist_path, html=True), name="static")
    port_in_use= is_port_in_use(20253)
    if port_in_use:
        debug_log_path = Path.home() / "Desktop" / "FAIVS_debug.log"
        with open(debug_log_path, "a", encoding="utf-8") as f:
            f.write("Port 20253 is already in use.\n")
        os._exit(0)
    else:
        frontendAppPath = Path(__file__).parent / "static/afaivs-win32-x64" / "afaivs.exe"
        if frontendAppPath.exists():
            subprocess.Popen([str(frontendAppPath)])
        else:
            open_browser()
        uvicorn.run(app, host="0.0.0.0", port=20253, reload=False,log_config=None)
if __name__ == "__main__":
    main()



