import re
from fastapi import APIRouter
from datetime import datetime
from module._base import PARENT_DIR
from pathlib import Path
from fastapi.responses import JSONResponse, FileResponse
from fastapi import HTTPException
import tempfile
import shutil
api_log = APIRouter()
@api_log.get("/sys/error_log")
def parse_log_file():
    log_entries = []
    current_entry = None
    log_filepath = Path(PARENT_DIR) / "logs" / "app.log"
    if not log_filepath.exists():return JSONResponse({"status": False, "msg": "Log file does not exist"})
    # 日志行正则表达式
    log_pattern = re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - '
        r'(?P<source>[^-]+) - '
        r'(?P<level>[A-Z]+) - '
        r'(?P<message>.*)'
    )
    
    with open(log_filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            match = log_pattern.match(line)
            if match:
                # 如果有上一个entry，先保存
                if current_entry:
                    log_entries.insert(0, current_entry)

                # 开始新的entry
                current_entry = {
                    'timestamp': datetime.strptime(
                        match.group('timestamp'), 
                        '%Y-%m-%d %H:%M:%S,%f'
                    ).timestamp() * 1000,  # 转换为毫秒时间戳
                    'source': match.group('source'),
                    'level': match.group('level'),
                    'message': match.group('message'),
                    'detail': None
                }
            else:
                # 这是堆栈跟踪的一部分
                if current_entry:
                    if current_entry['detail'] is None:
                        current_entry['detail'] = line
                    else:
                        current_entry['detail'] += '\n' + line
    
    # 添加最后一个entry
    if current_entry:
        log_entries.insert(0, current_entry)
    return JSONResponse({"status": True, "msg": "Log file parsed successfully", "data": log_entries})
@api_log.get("/sys/error_log/download")
async def download_log_file():
    """
    下载日志文件接口
    """
    log_filepath = Path(PARENT_DIR) / "logs" / "app.log"
    # 检查文件是否存在
    if not log_filepath.exists():
        raise HTTPException(status_code=404, detail="The log file does not exist")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".log") as tmp_file:
        shutil.copy2(log_filepath, tmp_file.name)
        temp_filepath = Path(tmp_file.name)
    # 返回文件下载响应
    return FileResponse(
        path=temp_filepath,
        filename="FAIVS.log",  # 下载时的文件名
        media_type="application/octet-stream"
    )
@api_log.get("/sys/error_log/clear")
async def clear_log_file():
    log_filepath = Path(PARENT_DIR) / "logs" / "app.log"
    # 检查文件是否存在
    if not log_filepath.exists():
        raise HTTPException(status_code=404, detail="The log file does not exist")

    # 清空日志文件
    with open(log_filepath, 'w', encoding='utf-8') as f:
        f.write("")

    return JSONResponse({"status": True, "msg": "Log file cleared successfully"})