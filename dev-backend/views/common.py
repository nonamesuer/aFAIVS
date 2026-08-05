from __future__ import annotations

import asyncio
import logging
import threading
from module._base import open_browser
import cv2
import os
from fastapi import APIRouter, Request, WebSocket
from module._base import get_display_name, graph
from module._camera_settings import configure_capture, load_camera_settings
from module._video_stream import camera_streams, stream_camera
from module._auth import auth_status
logger = logging.getLogger(__name__)
api_common = APIRouter()

@api_common.get("/get_loginUser")
def get_login_user(request: Request):
    status = auth_status(str(request.headers.get("X-Session-Token") or "").strip());user = status.get("user") or {}
    return {"username": user.get("name") or "","loginEnabled": status["loginEnabled"],"authenticated": status["authenticated"],"user": status.get("user")}

@api_common.get("/get_device")
async def get_device():
    devices = graph.get_input_devices()
    return {"camera": devices}


@api_common.websocket("/ws/video_streaming")
async def websocket_endpoint(websocket: WebSocket,camera_id: int,mode: str = "display",):
    await websocket.accept()
    preview_mode = "manual-region" if mode == "manual-region" else "display"
    stream_key = f"{camera_id}:{preview_mode}"
    state = camera_streams.setdefault(
        stream_key,
        {
            "capture": None,
            "clients": set(),
            "active": False,
            "camera_name": None,
            "settings": None,
            "capture_report": None,
            "crop_display":preview_mode != "manual-region",
            "capture_lock": threading.Lock(),
        },
    )
    state["clients"].add(websocket)
    try:
        if not state["active"]:
            devices = graph.get_input_devices()
            if camera_id < 0 or camera_id >= len(devices):raise RuntimeError(f"Camera index {camera_id} is out of range. Available cameras: {len(devices)}")
            camera_name = devices[camera_id]
            settings = load_camera_settings(camera_name)
            capture = cv2.VideoCapture(camera_id,cv2.CAP_DSHOW)
            if not capture.isOpened():
                capture.release()
                raise RuntimeError(f"Camera {camera_name} is not available")
            report = configure_capture(capture,settings,target_fps=30.0)
            state.update(
                {
                    "capture":capture,
                    "active":True,
                    "camera_name":camera_name,
                    "settings":settings,
                    "capture_report":report,
                }
            )
            logger.info("Preview camera %s settings=%s report=%s",camera_name,settings.to_dict(),report )
            asyncio.create_task(stream_camera(stream_key))
        while True:
            await asyncio.sleep(1)

    except Exception:
        logger.exception("Error with camera %s", camera_id)
    finally:
        state = camera_streams.get(stream_key)
        if state:
            clients = state.get("clients",set(),)
            clients.discard(websocket)
            logger.info("Client disconnected from camera %s. Remaining clients: %s",camera_id,len(clients))
            if not clients:
                state["active"] = False
                capture = state.get("capture")
                if capture is not None:
                    capture_lock = state.get("capture_lock")
                    if capture_lock is not None:
                        with capture_lock:
                            capture.release()
                    else:
                        capture.release()
                camera_streams.pop(stream_key,None)
@api_common.get("/shutdown")
async def shutdown():
    #重置所有modbus线圈
    os._exit(0)
    return {"message": "Server shutting down..."}
@api_common.get("/open/browser")
async def open_browsers():
    """打开浏览器"""
    open_browser()
    return {"message": "Browser opened."}