import asyncio
import json
import threading
import logging
import os
import time
import uuid
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse,JSONResponse
from pydantic import BaseModel

from module._detector import DetectionRuntime
from module._base import get_main_config,get_models_path,SopConfig,WEBSOCKET_CLIENTS,get_camera_index,CapStatus,DetectorStatus
from module._sop_config import resolve_sop_model
from module._auth import ensure_operator_available, require_authenticated
logger = logging.getLogger(__name__)
api_detection = APIRouter(prefix="/detection")
_runtime_lock = threading.Lock()
_runtime: DetectionRuntime | None = None
_external_start_lock = asyncio.Lock()
_external_start_status_lock = threading.Lock()
_external_start_status = {
    "request_id": None,
    "state": "idle",
    "message": "",
    "sn": None,
    "sop_name": None,
    "camera_name": None,
    "updated_at": None,
}
EXTERNAL_START_TERMINAL_STATES = {"success", "failed"}
ACTIVE_STATUS_VALUES = {1, 2}


def get_runtime() -> DetectionRuntime | None:
    # if _runtime is None:
    #     raise HTTPException(status_code=503, detail="检测运行时尚未初始化")
    return _runtime


def get_or_create_runtime(camera_index, camera_name, model_path=None, model_name=None, project_name=None, sop_name=None) -> DetectionRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = DetectionRuntime(camera_index=camera_index, camera_name=camera_name, model_path=model_path, model_name=model_name, project_name=project_name, sop_name=sop_name)
        return _runtime


def _read_external_start_status(*, consume_terminal: bool = False) -> dict:
    """
    读取最近一次外部启动状态。

    /status 轮询读取到 success/failed 后立即恢复为 idle，确保终态事件
    只被前端消费一次；starting 状态保留，直到本次启动得出最终结果。
    """
    with _external_start_status_lock:
        snapshot = dict(_external_start_status)
        if (
            consume_terminal
            and snapshot.get("state") in EXTERNAL_START_TERMINAL_STATES
        ):
            _external_start_status.update({
                "request_id": None,
                "state": "idle",
                "message": "",
                "sn": None,
                "sop_name": None,
                "camera_name": None,
                "updated_at": None,
            })
        return snapshot


def runtime_status(*, consume_external_start: bool = False) -> dict:
    status = {
        "initialized": _runtime is not None,
        "running": bool(_runtime and _runtime.running and not _runtime.paused),
        "paused": bool(_runtime and _runtime.running and _runtime.paused),
        "active": bool(_runtime and _runtime.running),
    }
    if _runtime is not None:
        if _runtime.external_mode:
            status.update({
                "trigger_configured": True,
                "waiting_for_trigger": bool(
                    _runtime.running and _runtime.detector.waiting_for_trigger
                ),
                "detecting": bool(
                    _runtime.running and not _runtime.detector.waiting_for_trigger
                ),
                "trigger_methods": ["external_api"],
                "trigger_source": (
                    "external_api" if _runtime.external_reference else None
                ),
                "triggered_at": _runtime.external_triggered_at,
            })
        else:
            status.update(_runtime.trigger_controller.status())
        status.update({
            "runtime_id": _runtime.runtime_id,
            "camera_name": _runtime.camera_name,
            "project_name": _runtime.project_name,
            "sop_name": _runtime.sop_name,
            "model_name": _runtime.model_name,
            "external_mode": _runtime.external_mode,
            "external_reference": _runtime.external_reference,
            "camera_settings":_runtime.camera.settings_snapshot(),
        })
    else:
        status.update({
            "trigger_configured": False,
            "waiting_for_trigger": False,
            "detecting": False,
            "trigger_methods": [],
            "trigger_source": None,
            "triggered_at": None,
            "runtime_id": None,
            "camera_name": None,
            "project_name": None,
            "sop_name": None,
            "model_name": None,
            "external_mode": False,
            "external_reference": None,
            "camera_settings": None,
        })
    status["external_start"] = _read_external_start_status(
        consume_terminal=consume_external_start,
    )
    return status


def _set_external_start_status(
    state: str,
    message: str,
    *,
    request_id: str,
    sn: str | None,
    sop_name: str | None,
    camera_name: str | None,
) -> None:
    with _external_start_status_lock:
        _external_start_status.update({
            "request_id": request_id,
            "state": state,
            "message": message,
            "sn": sn,
            "sop_name": sop_name,
            "camera_name": camera_name,
            "updated_at": time.time(),
        })


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
            message = await websocket.receive_text()
            try:
                payload = json.loads(message)
            except (TypeError, json.JSONDecodeError):
                continue

            if not isinstance(payload, dict) or payload.get("type") != "usb_trigger":
                continue

            runtime = get_runtime()
            value = payload.get("value")
            if not runtime or not runtime.running or not isinstance(value, str):
                continue

            accepted, reason = runtime.trigger_controller.trigger_usb(value)
            if not accepted:
                logger.info("USB scanner trigger ignored: %s", reason)

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
        logger.exception("Failed to close WebRTC connection")

    try:
        # runtime.stop() 中包含线程 join，
        # 放到工作线程执行，避免阻塞 FastAPI 事件循环。
        await asyncio.to_thread(runtime.stop)
    except Exception:
        logger.exception("Failed to stop detection runtime")


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
        raise HTTPException(status_code=409, detail="Detection not started")
    return await runtime.create_webrtc_answer(payload.sdp, payload.type)


@api_detection.get("/server-stream")
def server_stream():
    """MJPEG 兜底流：Firefox 默认走这里，并限制帧率避免浏览器卡死。"""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        raise HTTPException(status_code=409, detail="Detection not started")
    return StreamingResponse(
        runtime.iter_server_camera_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@api_detection.get("/status")
def status_detection():
    # 外部启动 success/failed 是一次性通知。当前轮询响应返回终态后，
    # 后端立即恢复为 idle，刷新页面不会再次弹出已经处理过的失败。
    return runtime_status(consume_external_start=True)


@api_detection.get("/trigger/http")
def trigger_http(request: Request):
    """HTTP GET trigger. Only configured parameter names are required; values are dynamic."""
    runtime = get_runtime()
    if not runtime or not runtime.running:
        return JSONResponse({"status": False, "msg": "Detection not started", "data": runtime_status()})
    accepted, message = runtime.trigger_controller.trigger_http(request.query_params)
    return JSONResponse({"status": accepted, "msg": message, "data": runtime_status()})


@api_detection.get("/external/start")
async def external_start_detection(
    SN: str | None = Query(default=None),
    SOP_NAME: str | None = Query(default=None),
    CAP_NAME: str | None = Query(default=None),
):
    """
    外部系统直接启动检测。

    该接口不依赖前端“开始”按钮。相同相机和 SOP 的后续产品会复用
    已打开的运行时；只有上一件完成并进入等待状态后才接受新的 SN。
    """
    global _runtime

    request_id = uuid.uuid4().hex
    sn = str(SN or "").strip()
    sop_name = str(SOP_NAME or "").strip()
    camera_name = str(CAP_NAME or "").strip()

    def failed(message: str) -> JSONResponse:
        _set_external_start_status(
            "failed",
            message,
            request_id=request_id,
            sn=sn or None,
            sop_name=sop_name or None,
            camera_name=camera_name or None,
        )
        return JSONResponse({
            "status": False,
            "msg": message,
            "data": runtime_status(),
        })

    operator_available,_operator_name = ensure_operator_available()
    if not operator_available:return failed("No operator is logged in")

    if not sn:
        return failed("SN cannot be empty")
    if not sop_name:
        return failed("SOP_NAME cannot be empty")
    if not camera_name:
        return failed("CAP_NAME cannot be empty")

    try:
        resolved_sop_name, model_project, _definition = resolve_sop_model(
            SopConfig().get(),
            sop_name,
        )
    except ValueError as exc:
        return failed(str(exc))

    model_path = os.path.join(get_models_path(), model_project)
    if not os.path.isdir(model_path):
        return failed(f"Model {model_project} does not exist")
    onnx_files = sorted(
        name for name in os.listdir(model_path) if name.endswith(".onnx")
    )
    if not onnx_files or not os.path.isfile(os.path.join(model_path, "cache.json")):
        return failed(f"Model {model_project} is incomplete, please check ONNX and cache.json")

    camera_index = get_camera_index(camera_name)
    if camera_index is None:
        return failed(f"Camera {camera_name} not found")

    async with _external_start_lock:
        current = get_runtime()
        if current and current.running:
            sop_state = str(
                (current.detector.snapshot().get("sop") or {}).get("state") or ""
            ).lower()
            same_runtime = (
                current.external_mode
                and current.camera_name == camera_name
                and current.sop_name == resolved_sop_name
                and current.project_name == model_project
            )

            if same_runtime:
                if not current.detector.waiting_for_trigger:
                    return failed(
                        "A SOP is currently in progress, please wait for it to complete before triggering the next one"
                    )
                if not current.start_external_cycle(sn):
                    return failed("External trigger not accepted by runtime, please try again later")
                _set_external_start_status(
                    "success",
                    "Reused the current camera and started the next SOP",
                    request_id=request_id,
                    sn=sn,
                    sop_name=resolved_sop_name,
                    camera_name=camera_name,
                )
                return JSONResponse({
                    "status": True,
                    "msg": "The next SOP has been initiated using the current camera and SOP",
                    "data": runtime_status(),
                })

            if sop_state not in {"", "completed", "idle"}:
                return failed(
                    "A SOP is currently in progress, cannot switch SOP or camera"
                )
            await _stop_detection_runtime(current)

        _set_external_start_status(
            "starting",
            "Starting the camera and SOP",
            request_id=request_id,
            sn=sn,
            sop_name=resolved_sop_name,
            camera_name=camera_name,
        )

        runtime = None
        try:
            runtime = DetectionRuntime(
                camera_index=camera_index,
                camera_name=camera_name,
                model_path=model_path,
                model_name=onnx_files[0],
                project_name=model_project,
                sop_name=resolved_sop_name,
            )
            with _runtime_lock:
                _runtime = runtime
            await asyncio.to_thread(runtime.start, True)
            if not runtime.start_external_cycle(sn):
                raise RuntimeError("Camera started, but SOP did not accept external trigger")
        except Exception as exc:
            logger.exception("Failed to start detection via external interface")
            if runtime is not None:
                await _stop_detection_runtime(runtime)
            return failed(str(exc))

        _set_external_start_status(
            "success",
            "Camera and SOP started successfully",
            request_id=request_id,
            sn=sn,
            sop_name=resolved_sop_name,
            camera_name=camera_name,
        )
        return JSONResponse({
            "status": True,
            "msg": "External detection started successfully",
            "data": runtime_status(),
        })



@api_detection.get("/start_detection")
def start_detection(
    camera_name: str,
    sop_name: str | None = None,
    project_name: str | None = None,
    _user: dict = Depends(require_authenticated),
):
    """Start a named SOP. project_name remains as a legacy alias."""
    operator_available,_operator_name = ensure_operator_available()
    if not operator_available:return JSONResponse({"status": False,"msg": "Please log in before starting detection"})
    try:
        resolved_sop_name, model_project, _definition = resolve_sop_model(
            SopConfig().get(),
            sop_name or project_name,
        )
    except ValueError as exc:
        return JSONResponse({"status": False, "msg": str(exc)})

    path = get_models_path()
    model_path = os.path.join(path, model_project)
    if not os.path.exists(model_path):
        return JSONResponse({"status":False,"msg":f"Model {model_project} not found"})
    onnx_files = [f for f in os.listdir(model_path) if f.endswith(".onnx")]
    cache_file = os.path.join(model_path, "cache.json")
    if not onnx_files or not os.path.exists(cache_file):
        return JSONResponse({"status":False,"msg":f"Model {model_project} is incomplete,please check the model folder"})
    model_name = onnx_files[0]  # 使用第一个 ONNX 文件作为模型名称
    index = get_camera_index(camera_name)
    if index is None:
        logger.error(f"Camera {camera_name} not found in available devices")
        return JSONResponse({"status":False,"msg":f"Camera {camera_name} not found"})
    runtime = get_or_create_runtime(
        camera_index=index,
        camera_name=camera_name,
        model_path=model_path,
        model_name=model_name,
        project_name=model_project,
        sop_name=resolved_sop_name,
    )
    try:
        runtime.start()
    except RuntimeError as e:
        logger.error("Failed to start detection: %s", e)
        return JSONResponse({"status":False,"msg":str(e)})
    return JSONResponse({"status":True,"msg":"Start detection successfully","data":runtime_status()})

@api_detection.get("/pause_detection")
def pause_detection(_user: dict = Depends(require_authenticated)):
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "Detection has not started",
            "data": runtime_status(),
        })

    if runtime.paused:
        return JSONResponse({
            "status": True,
            "msg": "Detection is already paused",
            "data": runtime_status(),
        })

    success = runtime.pause()

    if not success:
        return JSONResponse({
            "status": False,
            "msg": "Failed to pause detection",
            "data": runtime_status(),
        })

    return JSONResponse({
        "status": True,
        "msg": "Detection paused",
        "data": runtime_status(),
    })

@api_detection.get("/resume_detection")
def resume_detection(_user: dict = Depends(require_authenticated)):
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "Detection has not started",
            "data": runtime_status(),
        })

    if not runtime.paused:
        return JSONResponse({
            "status": True,
            "msg": "Detection is already running",
            "data": runtime_status(),
        })

    success = runtime.resume()

    if not success:
        return JSONResponse({
            "status": False,
            "msg": "Failed to resume detection",
            "data": runtime_status(),
        })

    return JSONResponse({
        "status": True,
        "msg": "Detection resumed",
        "data": runtime_status(),
    })


@api_detection.post("/reset_detection")
def reset_detection(_user: dict = Depends(require_authenticated)):
    """
    只复位 SOP，不关闭摄像头、线程、WebRTC 和结果 WebSocket。
    """
    runtime = get_runtime()

    if not runtime or not runtime.running:
        return JSONResponse({
            "status": False,
            "msg": "Detection has not started, cannot reset",
            "data": runtime_status(),
        })

    result = runtime.reset()

    if result is None:
        return JSONResponse({
            "status": False,
            "msg": "Failed to reset detection",
            "data": runtime_status(),
        })

    data = runtime_status()
    data["result"] = result

    return JSONResponse({
        "status": True,
        "msg": "SOP has been reset to the first step",
        "data": data,
    })
@api_detection.get("/stop_detection")
async def stop_detection(_user: dict = Depends(require_authenticated)):
    """
    完整停止检测并释放所有资源。
    """
    runtime = get_runtime()

    await _stop_detection_runtime(runtime)

    return JSONResponse({
        "status": True,
        "msg": "Detection stopped",
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
        runtime = get_runtime()
        if runtime and runtime.running and runtime.sop_name:
            active_config = sop_config_datas.get(runtime.sop_name)
            if isinstance(active_config, dict):
                return JSONResponse({
                    "status": True,
                    "data": {
                        runtime.sop_name: {
                            **active_config,
                            "sopName": runtime.sop_name,
                        }
                    },
                    "enableCamera": runtime.camera_name,
                })
        enabled_sop = next(
            (
                {
                    key: {
                        **value,
                        "sopName": key,
                    }
                }
                for key, value in sop_config_datas.items()
                if isinstance(value, dict) and value.get("enabled", False)
            ),
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
