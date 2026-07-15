
from module._base import get_display_name
from fastapi import APIRouter, WebSocket
import logging
import module._video_stream
from module._base import graph,get_main_config
from module._video_stream import camera_streams,stream_camera
import cv2
import asyncio
logger = logging.getLogger(__name__)
api_common = APIRouter()
@api_common.get("/get_loginUser")
def get_login_user():
    username = get_display_name()
    return {"username": username}
@api_common.get("/get_device")
async def get_device():
    devices = graph.get_input_devices()
    return {"camera": devices}
@api_common.websocket("/ws/video_streaming")
async def websocket_endpoint(websocket: WebSocket, camera_id: int):
    await websocket.accept()
    if camera_id not in module._video_stream.camera_streams:
        camera_streams[camera_id] = {"capture": None,"clients": set(),"active": False}
    camera_streams[camera_id]["clients"].add(websocket)
    try:
        if not camera_streams[camera_id]["active"]:
            camera_streams[camera_id]["active"] = True
            camera_streams[camera_id]["capture"] = cv2.VideoCapture(camera_id,cv2.CAP_DSHOW)
            if not camera_streams[camera_id]["capture"].isOpened():
                logger.error(f"Unable to open camera {camera_id}")
                camera_streams[camera_id]["active"] = False
                camera_streams[camera_id]["clients"].remove(websocket)  # 移除当前客户端
                raise RuntimeError(f"Camera {camera_id} is not available")
            devices = graph.get_input_devices()
            camera_name = devices[camera_id] if camera_id < len(devices) else None
            area,clarity = None,50
            if camera_name:
                config_datas = get_main_config()
                cameraResolution = config_datas.get("cameraResolution", {}).get(camera_name, {})
                if cameraResolution:
                    camera_streams[camera_id]["capture"].set(cv2.CAP_PROP_FRAME_WIDTH, cameraResolution['width'])
                    camera_streams[camera_id]["capture"].set(cv2.CAP_PROP_FRAME_HEIGHT, cameraResolution['height'])
                    area = cameraResolution.get('area', None)
                    clarity = cameraResolution.get('clarity', 50)
            asyncio.create_task(stream_camera(camera_id, area, clarity))
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logger.exception(f"Error with camera {camera_id}: {e}")
    finally:
        if camera_id in camera_streams:
            camera_streams[camera_id]["clients"].remove(websocket)
            logger.info(f"Client disconnected from camera {camera_id}. Remaining clients: {len(camera_streams[camera_id]['clients'])}")
            # 如果没有客户端连接，则停止摄像头流
            if not camera_streams[camera_id]["clients"]:
                camera_streams[camera_id]["active"] = False
                if camera_streams[camera_id]["capture"]:
                    camera_streams[camera_id]["capture"].release()
                del camera_streams[camera_id]  # 删除摄像头记录