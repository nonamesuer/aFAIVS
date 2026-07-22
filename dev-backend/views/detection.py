import asyncio
import threading
import logging
import os
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse,JSONResponse
from pydantic import BaseModel

from module._detector import DetectionRuntime
from module._base import get_main_config,get_models_path,SopConfig,WEBSOCKET_CLIENTS,get_camera_index,CapStatus,DetectorStatus
logger = logging.getLogger(__name__)
api_detection = APIRouter(prefix="/detection")
_runtime_lock = threading.Lock()
_runtime: DetectionRuntime | None = None
ACTIVE_STATUS_VALUES = {1, 2}


def get_runtime() -> DetectionRuntime | None:
    # if _runtime is None:
    #     raise HTTPException(status_code=503, detail="检测运行时尚未初始化")
    return _runtime


def get_or_create_runtime(camera_index, camera_name, model_path=None, model_name=None, project_name=None) -> DetectionRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DetectionRuntime(camera_index=camera_index, camera_name=camera_name, model_path=model_path, model_name=model_name, project_name=project_name)
        return _runtime


def runtime_status() -> dict:
    status = {
        "initialized": _runtime is not None,
        "running": bool(_runtime and _runtime.running and not _runtime.paused),
        "paused": bool(_runtime and _runtime.running and _runtime.paused),
        "active": bool(_runtime and _runtime.running),
    }
    if _runtime is not None:
        status.update(_runtime.trigger_controller.status())
    else:
        status.update({
            "trigger_configured": False,
            "waiting_for_trigger": False,
            "detecting": False,
            "trigger_methods": [],
            "trigger_source": None,
            "triggered_at": None,
        })
    return status


async def _send_detection_results(websocket: WebSocket) -> None:
    cap_status = CapStatus()
    detector_status = DetectorStatus()
    while True:
        runtime = get_runtime()
        current_cap_status = cap_status.get()
        current_detector_status = detector_status.get()

        if (
            not runtime
            or not runtime.running
            or current_cap_status not in ACTIVE_STATUS_VALUES
            or current_detector_status not in ACTIVE_STATUS_VALUES
        ):
            logger.info(
                "Stopping detection WebSocket because cap_status=%s detector_status=%s runtime_running=%s",
                current_cap_status,
                current_detector_status,
                bool(runtime and runtime.running),
            )
            await websocket.close(code=1000)
            return

        if (
            current_cap_status == 1
            and current_detector_status == 1
        ):
            await websocket.send_json({
                "ws_result": runtime.detector.snapshot(),
                "runtime_status": runtime_status(),
            })
        await asyncio.sleep(0.1)


async def _wait_websocket_disconnect(websocket: WebSocket) -> None:
    while True:
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
            return


async def _cancel_tasks(*tasks: asyncio.Task) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _stop_detection_runtime(
    runtime: DetectionRuntime | None,
) -> None:
    """
    完整停止检测运行时：

    1. 禁止摄像头和检测线程继续运行。
    2. 关闭所有 WebRTC 连接。
    3. 停止检测线程、手部检测线程和摄像头线程。
    4. 清除全局运行时。
    """
    global _runtime

    CapStatus().set(0)
    DetectorStatus().set(0)

    if runtime is None:
        with _runtime_lock:
            _runtime = None
        return

    # 先从全局移除，防止停止过程中继续使用旧 runtime。
    with _runtime_lock:
        if _runtime is runtime:
            _runtime = None

    try:
        await runtime.close_peer_connections()
    except Exception:
        logger.exception("关闭 WebRTC 连接失败")

    try:
        # runtime.stop() 中包含线程 join，
        # 放到工作线程执行，避免阻塞 FastAPI 事件循环。
        await asyncio.to_thread(runtime.stop)
    except Exception:
        logger.exception("停止检测运行时失败")


@api_detection.websocket("/ws/result")
async def ws_result(websocket: WebSocket):
    """检测结果通道：前端用它更新计数、工序状态和检测框。"""
    await websocket.accept()
    WEBSOCKET_CLIENTS.add(websocket)
    runtime = get_runtime()
    sender_task = asyncio.create_task(_send_detection_results(websocket))
    disconnect_task = asyncio.create_task(_wait_websocket_disconnect(websocket))
    try:
        done, pending = await asyncio.wait(
            {sender_task, disconnect_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception:
        logger.exception("Detection result WebSocket closed unexpectedly")
    finally:
        await _cancel_tasks(sender_task, disconnect_task)
        WEBSOCKET_CLIENTS.discard(websocket)
        # await _stop_detection_runtime(runtime or get_runtime())


class OfferRequest(BaseModel):
    sdp: str
    type: str


@api_detection.post("/webrtc/offer")
async def offer(payload: OfferRequest):
    """WebRTC 信令接口：接收浏览器 offer，返回后端视频流 answer。"""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        raise HTTPException(status_code=409, detail="检测尚未启动")
    return await runtime.create_webrtc_answer(payload.sdp, payload.type)


@api_detection.get("/server-stream")
def server_stream():
    """MJPEG 兜底流：Firefox 默认走这里，并限制帧率避免浏览器卡死。"""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        raise HTTPException(status_code=409, detail="检测尚未启动")
    return StreamingResponse(
        runtime.iter_server_camera_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@api_detection.get("/status")
def status_detection():
    return runtime_status()


@api_detection.get("/trigger/http")
def trigger_http(request: Request):
    """HTTP GET trigger. Only configured parameter names are required; values are dynamic."""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        return JSONResponse({"status": False, "msg": "检测尚未启动", "data": runtime_status()})
    accepted, message = runtime.trigger_controller.trigger_http(request.query_params)
    return JSONResponse({"status": accepted, "msg": message, "data": runtime_status()})


@api_detection.post("/trigger/usb")
async def trigger_usb(request: Request):
    """Accept a scanner value without a rigid Pydantic body to avoid unrelated 422 errors."""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        return JSONResponse({"status": False, "msg": "检测尚未启动", "data": runtime_status()})
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    value = payload.get("value", payload.get("code", ""))
    print("trigger_usb value:", value)
    if not isinstance(value, str):
        return JSONResponse({"status": False, "msg": "USB scanner value must be a string", "data": runtime_status()})
    accepted, message = runtime.trigger_controller.trigger_usb(value)
    return JSONResponse({"status": accepted, "msg": message, "data": runtime_status()})

@api_detection.get("/start_detection")
def start_detection(camera_name: str,project_name: str):
    path = get_models_path()
    model_path = os.path.join(path, project_name)
    if not os.path.exists(model_path):
        return JSONResponse({"status":False,"msg":f"Model {project_name} not found"})
    onnx_files = [f for f in os.listdir(model_path) if f.endswith(".onnx")]
    cache_file = os.path.join(model_path, "cache.json")
    if not onnx_files or not os.path.exists(cache_file):
        return JSONResponse({"status":False,"msg":f"Model {project_name} is incomplete,please check the model folder"})
    model_name = onnx_files[0]  # 使用第一个 ONNX 文件作为模型名称
    index = get_camera_index(camera_name)
    if index is None:
        logger.error(f"Camera {camera_name} not found in available devices")
        return JSONResponse({"status":False,"msg":f"Camera {camera_name} not found"})
    runtime = get_or_create_runtime(camera_index=index,camera_name=camera_name,model_path=model_path,model_name=model_name,project_name=project_name)
    try:
        runtime.start()
    except RuntimeError as e:
        logger.error("Failed to start detection: %s", e)
        return JSONResponse({"status":False,"msg":str(e)})
    return JSONResponse({"status":True,"msg":"Start detection successfully","data":runtime_status()})

@api_detection.get("/pause_detection")
def pause_detection():
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "检测尚未启动",
            "data": runtime_status(),
        })

    if runtime.paused:
        return JSONResponse({
            "status": True,
            "msg": "检测已经处于暂停状态",
            "data": runtime_status(),
        })

    success = runtime.pause()

    if not success:
        return JSONResponse({
            "status": False,
            "msg": "暂停检测失败",
            "data": runtime_status(),
        })

    return JSONResponse({
        "status": True,
        "msg": "检测已暂停",
        "data": runtime_status(),
    })

@api_detection.get("/resume_detection")
def resume_detection():
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "检测尚未启动",
            "data": runtime_status(),
        })

    if not runtime.paused:
        return JSONResponse({
            "status": True,
            "msg": "检测已经处于运行状态",
            "data": runtime_status(),
        })

    success = runtime.resume()

    if not success:
        return JSONResponse({
            "status": False,
            "msg": "继续检测失败",
            "data": runtime_status(),
        })

    return JSONResponse({
        "status": True,
        "msg": "检测已继续",
        "data": runtime_status(),
    })


@api_detection.get("/stop_detection")
async def stop_detection():
    runtime = get_runtime()
    await _stop_detection_runtime(runtime)
    return JSONResponse({"status":True,"msg":"检测已停止","data":runtime_status()})


@api_detection.post("/reset_detection")
def reset_detection():
    """
    只复位 SOP，不关闭摄像头、线程、WebRTC 和结果 WebSocket。
    """
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "检测尚未启动，无法复位",
            "data": runtime_status(),
        })

    result = runtime.reset()

    if result is None:
        return JSONResponse({
            "status": False,
            "msg": "检测复位失败",
            "data": runtime_status(),
        })

    data = runtime_status()
    data["result"] = result

    return JSONResponse({
        "status": True,
        "msg": "工序已复位到第一步",
        "data": data,
    })
@api_detection.get("/stop_detection")
async def stop_detection():
    """
    完整停止检测并释放所有资源。
    """
    runtime = get_runtime()

    await _stop_detection_runtime(runtime)

    return JSONResponse({
        "status": True,
        "msg": "检测已停止",
        "data": runtime_status(),
    })
##
# *********************************************************
# Start my featrue
# 2026.06.30
# *********************************************************
##

@api_detection.get("/sop/configration")
def get_sop_configration():
    try:
        sop_config_datas = SopConfig().get()
        config_datas = get_main_config()
        enabled_sop = next(
            ({key: value} for key, value in sop_config_datas.items() if isinstance(value, dict) and value.get("enabled", False)),
            {},
        )
        enable_camera = config_datas.get("enableCamera", None)
        return JSONResponse({"status":True,"data":enabled_sop, "enableCamera": enable_camera})
    except Exception as e:
        logger.error("Failed to get SOP configuration: %s", e)
        return JSONResponse({"status":False,"msg":str(e)})


def register_detection(app: FastAPI) -> None:
    """在主应用中注册 detection 路由。"""
    @app.on_event("shutdown")
    async def _shutdown_detection_runtime():
        if _runtime is not None:
            await _runtime.close_peer_connections()
            _runtime.stop()

    app.include_router(api_detection, tags=["DETECTION"])





