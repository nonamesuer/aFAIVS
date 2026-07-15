from collections.abc import Generator
import asyncio
import logging
import os
import threading
import time

import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

from module._base import get_main_config,CapStatus,DetectorStatus,JsonFile,SopConfig
from module._camera import CameraManager
from module._onnx_detection import ONNXDetection
from module._sop_state_machine import SOPStateMachine
from module._hand_detection import HandTracker, HandDetectorWorker

logger = logging.getLogger(__name__)

JPEG_QUALITY = 85
SERVER_STREAM_FPS = 12.0
ACTIVE_STATUS_VALUES = {1, 2}


def _build_ice_servers() -> list[RTCIceServer]:
    """读取 WebRTC ICE 配置；不配置时使用默认 STUN。"""
    urls_raw = "stun:stun.l.google.com:19302"
    urls = [url.strip() for url in urls_raw.split(",") if url.strip()]
    username = os.getenv("WEBRTC_ICE_USERNAME", "NA")
    credential = os.getenv("WEBRTC_ICE_CREDENTIAL", "NA")
    if username and credential:
        return [RTCIceServer(urls=urls, username=username, credential=credential)]
    return [RTCIceServer(urls=urls)]


async def _wait_ice_gathering_complete(pc: RTCPeerConnection, timeout_s: float = 5.0) -> None:
    if pc.iceGatheringState == "complete":
        return
    done = asyncio.Event()
    @pc.on("icegatheringstatechange")
    async def _on_ice_gathering_state_change():
        if pc.iceGatheringState == "complete":
            done.set()
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout_s)
    except TimeoutError:
        logger.warning("WebRTC: backend ICE gathering wait timeout")


class DetectionRuntime:
    """检测服务运行时：统一管理采集线程和检测线程生命周期。"""

    def __init__(self, camera_index: int,camera_name: str, model_path: str | None = None, model_name: str | None = None, project_name: str | None = None):
        self.camera = CameraManager(camera_index=camera_index,camera_name=camera_name, target_fps=30.0)
        self.detector = DetectorWorker(camera=self.camera, model_path=model_path, model_name=model_name, project_name=project_name, infer_period_ms=70)
        self.peer_connections: set[RTCPeerConnection] = set()
        self.running = False
        self.paused = False

    def start(self) -> None:
        if self.running:
            return
        self.camera.start()
        self.detector.start()
        self.running = True
        self.paused = False
    def pause(self) -> bool:
        if not self.running:
            return False

        if self.paused:
            return True

        success = self.detector.pause()

        if success:
            self.paused = True

        return success


    def resume(self) -> bool:
        if not self.running:
            return False

        if not self.paused:
            return True

        success = self.detector.resume()

        if success:
            self.paused = False

        return success
    def stop(self) -> None:
        if not self.running:
            return
        self.detector.stop()
        self.camera.stop()
        self.running = False
        self.paused = False

    async def create_webrtc_answer(self, sdp: str, type_: str) -> dict[str, str]:
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=_build_ice_servers()))
        self.peer_connections.add(pc)

        @pc.on("connectionstatechange")
        async def _on_connection_state_change():
            logger.info(f"WebRTC: backend connectionState={pc.connectionState}")
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await pc.close()
                self.peer_connections.discard(pc)

        @pc.on("iceconnectionstatechange")
        async def _on_ice_connection_state_change():
            logger.info(f"WebRTC: backend iceConnectionState={pc.iceConnectionState}")

        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=type_))
        pc.addTrack(CameraTrack(self))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await _wait_ice_gathering_complete(pc)

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
        }

    def iter_server_camera_stream(self) -> Generator[bytes, None, None]:#专供Firefox使用的兜底流，避免浏览器卡死
        frame_interval = 1.0 / SERVER_STREAM_FPS
        next_tick = time.monotonic()
        while self.running:
            if (
                self.camera.cap_status.get() not in ACTIVE_STATUS_VALUES
                or self.detector.detector_status.get() not in ACTIVE_STATUS_VALUES
            ):
                break
            frame = self.camera.get_latest_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            
            processed_frame = process_frame(frame, self.detector.snapshot())
            success, buffer = cv2.imencode(
                ".jpg",
                processed_frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
            )
            if not success:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )

            next_tick += frame_interval
            sleep_time = max(0.0, next_tick - time.monotonic())
            if sleep_time > 0:
                time.sleep(sleep_time)

    async def close_peer_connections(self) -> None:
        for pc in list(self.peer_connections):
            await pc.close()
            self.peer_connections.discard(pc)


class DetectorWorker:
    """后台检测线程：配置 ONNX_MODEL_PATH 后使用真实 ONNX 模型，否则使用模拟结果。"""

    def __init__(self, camera: CameraManager, model_path: str | None = None, model_name: str | None = None, project_name: str | None = None, infer_period_ms: int = 70,hand_infer_period_ms: int = 50):
        if not model_path or not model_name:
            raise RuntimeError("Model path and model name are required")

        self.cap_status = CapStatus()
        self.detector_status = DetectorStatus()
        self.camera = camera
        self.infer_period = infer_period_ms / 1000.0
        self.hand_infer_period_ms = hand_infer_period_ms
        self.running = False
        self.thread = None
        self.result_lock = threading.Lock()
        self.result = {
            "step": 1,
            "gesture": "idle",
            "bbox": [],
            "detections": [],
            "hands": {},
            "hand_action_points": [],
            "score": 0.0,
            "ok_count": 0,
            "ng_count": 0,
            "updated_at": 0.0,
        }
        self.paused = False
        self.pause_lock = threading.Lock()
        self.model_path = model_path
        self.model_name = model_name
        self.project_name = project_name
        self.sop_machine = self._create_sop_machine()
        self.hand_worker: HandDetectorWorker | None = None
        # self._refresh_hand_tracker()
        self.result["sop"] = self.sop_machine.snapshot(reason="SOP waiting to start")
        self._last_sop_state = self.result["sop"].get("state")
        self._tick = 0
        self.label_class = JsonFile(os.path.join(self.model_path, "cache.json")).read_json_file().get("labeling", {})
        self.detector = ONNXDetection(onnx_model=os.path.join(self.model_path, self.model_name), classes=self.label_class)
        self.detector.load_model()
    def _refresh_hand_tracker(self) -> None:
        """按当前SOP是否需要手部识别，惰性创建/销毁 HandTracker，避免不需要时白白耗CPU。"""
        needs_hands = self.sop_machine.requires_hand_tracking
        if needs_hands and self.hand_worker is None:
            num_hands = max(1, self.sop_machine.max_required_hands)
            tracker = HandTracker(num_hands=num_hands)
            self.hand_worker = HandDetectorWorker(
                camera=self.camera,
                hand_tracker=tracker,
                infer_period_ms=self.hand_infer_period_ms,
                gate_fn=lambda: bool(
                    not self.paused
                    and self.sop_machine.current_step
                    and self.sop_machine.current_step.hand_gate_enabled
                ),
            )
            self.hand_worker.start()
            logger.info(f"Hand tracking worker started, num_hands={num_hands}")
        elif not needs_hands and self.hand_worker is not None:
            self.hand_worker.stop()
            self.hand_worker = None
            logger.info("Hand tracking worker stopped")
    def _create_sop_machine(self) -> SOPStateMachine:
        try:
            config = SopConfig().get()
            project_config = config.get(self.project_name) if self.project_name else None
            sop_task = SOPStateMachine.from_sop_map(project_config or config, stable_frames=3)
            return sop_task
        except Exception as e:
            logger.exception("Failed to initialize SOP state machine")
            machine = SOPStateMachine({}, stable_frames=3)
            machine.last_reason = str(e)
            return machine

    def start(self) -> None:
        if self.running:return
        self.paused = False
        self.sop_machine = self._create_sop_machine()
        self.sop_machine.start()
        self._refresh_hand_tracker()
        self._last_sop_state = self.sop_machine.snapshot().get("state")
        self.running = True
        self.detector_status.set(1)
        self.thread = threading.Thread(target=self._detect_loop, daemon=True)
        self.thread.start()

    def _detect_loop(self) -> None:
        next_tick = time.monotonic()
        while self.running:
            cap_status = self.cap_status.get()
            if cap_status == 2:
                time.sleep(1)
                continue
            elif cap_status != 1:
                self.detector_status.set(cap_status)
                self.running = False
                return
            # =================================================
            # 暂停状态
            # 保留线程，但不执行 ONNX / MediaPipe结果读取 / SOP update
            # =================================================
            if self.paused:
                time.sleep(0.05)
                next_tick = time.monotonic()
                continue
            frame = self.camera.get_latest_frame()
            if frame is not None:
                detection = self.detector.predict(frame) if self.detector else None
                hands = None
                # 只有当前步骤真的需要手部识别时才跑MediaPipe，减少不必要的开销
                current_step = self.sop_machine.current_step
                if self.hand_worker is not None and current_step is not None and current_step.hand_gate_enabled:
                    hands = self.hand_worker.snapshot()
                if detection is not None:
                    self._update_result(detection[3], hands=hands)

            next_tick += self.infer_period
            sleep_time = max(0.0, next_tick - time.monotonic())
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _update_result(self, detection: dict, hands=None) -> None:
        label_box_datas = detection.get("datas", [])
        sop_result = self.sop_machine.update(label_box_datas,hands=hands)
        sop_state = sop_result.get("state")
        with self.result_lock:
            self.result["step"] = 1 if self.result.get("step", 1) == 1 else 2
            self.result["gesture"] = "gesture"
            self.result["detections"] = label_box_datas
            self.result["hands"] = hands or {}
            self.result["hand_action_points"] = (self.sop_machine.current_hand_action_points(hands) if hands else [])
            self.result["sop"] = sop_result
            if sop_state != self._last_sop_state:
                if sop_state == "completed":
                    self.result["ok_count"] = self.result.get("ok_count", 0) + 1
                elif sop_state == "failed":
                    self.result["ng_count"] = self.result.get("ng_count", 0) + 1
                self._last_sop_state = sop_state
            self.result["updated_at"] = time.time()

    def snapshot(self):
        with self.result_lock:
            return dict(self.result)
    def pause(self) -> bool:
        """暂停 AI 推理和 SOP 状态推进，但不销毁检测线程。"""
        with self.pause_lock:
            if not self.running:
                return False

            if self.paused:
                return True

            self.paused = True
            self.sop_machine.pause()

            sop_result = self.sop_machine.snapshot(
                matched=False,
                reason="SOP paused",
            )

            with self.result_lock:
                self.result["sop"] = sop_result
                self.result["hands"] = {}
                self.result["hand_action_points"] = []
                self.result["updated_at"] = time.time()

            return True


    def resume(self) -> bool:
        """从暂停位置继续检测。"""
        with self.pause_lock:
            if not self.running:
                return False

            if not self.paused:
                return True

            self.sop_machine.resume()
            self.paused = False

            sop_result = self.sop_machine.snapshot(
                matched=False,
                reason="SOP resumed",
            )

            with self.result_lock:
                self.result["sop"] = sop_result
                self.result["updated_at"] = time.time()

            return True
    def stop(self) -> None:
        self.running = False
        self.paused = False
        self.detector_status.set(0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.hand_worker is not None:
            self.hand_worker.stop()
            self.hand_worker = None


class CameraTrack(VideoStreamTrack):
    """WebRTC 视频轨：Chrome/Edge 通过 /offer 拉取这路处理后的视频。"""

    def __init__(self, runtime: DetectionRuntime):
        super().__init__()
        self.runtime = runtime

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame = self.runtime.camera.get_latest_frame()
        while frame is None:
            await asyncio.sleep(0.005)
            frame = self.runtime.camera.get_latest_frame()

        processed = process_frame(frame, self.runtime.detector.snapshot())
        video_frame = VideoFrame.from_ndarray(processed, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


def process_frame(image: np.ndarray, result: dict | None = None) -> np.ndarray:
    """叠加检测结果并返回处理后画面。"""

    # cv2.putText(image, "SOP Analysis Running", (50, 50),
    #             cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    detections = result.get("detections") if result else []
    for item in detections or []:
        bbox = item.get("points", [])
        if len(bbox) == 4:
            x1, y1, x2, y2 = [int(value) for value in bbox]
        elif (len(bbox) == 2 and all(isinstance(point, (list, tuple)) and len(point) == 2 for point in bbox)):
            x1, y1 = [int(value) for value in bbox[0]]
            x2, y2 = [int(value) for value in bbox[1]]
        else:
            continue
        label = f"{item.get('label', 'unknown')} {float(item.get('score', 0.0)):.2f}"
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 200, 255), 2)
        cv2.putText(image, label, (x1, max(24, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    if result:
        HandTracker.draw_hands(image, result.get("hands"))
        HandTracker.draw_action_points(image, result.get("hand_action_points"))
    return image