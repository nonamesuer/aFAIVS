from collections.abc import Callable, Generator
import asyncio
import logging
import os
import threading
import time
import uuid
import cv2
import numpy as np
from aiortc import RTCPeerConnection, RTCConfiguration, RTCIceServer, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from module._base import get_main_config,DEFAULT_BOX_STYLE_CONFIG,DEFAULT_HAND_STYLE_CONFIG,DEFAULT_BOX_COLOR,CapStatus,DetectorStatus,JsonFile,SopConfig
from module._camera import CameraManager
from module._onnx_detection import ONNXDetection
from module._sop_state_machine import SOPStateMachine
from module._vision_fusion import LightweightObjectTracker
from module._hand_detection import HandTracker, HandDetectorWorker
from module._trigger import TriggerController
from module._sop_result_store import SOPResultStore
from module._result_media import ResultMediaRecorder
from module._sop_config import resolve_sop_definition
from module._step_feedback import StepFeedbackDispatcher
from module._box_style import (
    collect_sop_area_labels,
    normalize_area_fill_alpha,
    should_fill_area,
)
from module._camera_settings import (
    encode_jpeg,
)
from module._manual_regions import (
    build_manual_region_detections,
    collect_sop_manual_region_keys,
    normalize_manual_regions_config,
    validate_sop_manual_region_references,
)
from PIL import ImageColor
logger = logging.getLogger(__name__)

# JPEG_QUALITY = 85
SERVER_STREAM_FPS = 30.0
ACTIVE_STATUS_VALUES = {1, 2}
MAX_FEEDBACK_STATUS_EVENTS = 30
BOX_STYLE_CONFIG = {}
HAND_STYLE_CONFIG = {}
BOX_COLOR = {}

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

    def __init__(self, camera_index: int,camera_name: str, model_path: str | None = None, model_name: str | None = None, project_name: str | None = None, sop_name: str | None = None):
        self.runtime_id = uuid.uuid4().hex
        self.camera_name = camera_name
        self.project_name = project_name
        self.sop_name = sop_name
        self.model_name = model_name
        self.external_mode = False
        self.external_reference: str | None = None
        self.external_triggered_at: float | None = None
        self.camera = CameraManager(camera_index=camera_index,camera_name=camera_name, target_fps=30.0)
        self.detector = DetectorWorker(camera=self.camera, model_path=model_path, model_name=model_name, project_name=project_name, sop_name=sop_name, infer_period_ms=70)
        self.peer_connections: set[RTCPeerConnection] = set()
        self.running = False
        self.paused = False
        self.trigger_controller = TriggerController(self.detector.activate_trigger)
        self.detector.on_sop_completed = self._prepare_next_trigger_cycle
        global BOX_STYLE_CONFIG,HAND_STYLE_CONFIG,BOX_COLOR
        main_config = get_main_config()
        BOX_STYLE_CONFIG = main_config.get("boxStyle", DEFAULT_BOX_STYLE_CONFIG)
        HAND_STYLE_CONFIG = main_config.get("handStyle", DEFAULT_HAND_STYLE_CONFIG)
        cache_file = JsonFile(os.path.join(model_path, "cache.json")).read_json_file() if model_path else {}
        BOX_COLOR = cache_file.get("labeling", DEFAULT_BOX_COLOR)
        BOX_COLOR = {k: list(reversed(ImageColor.getrgb(v))) for k, v in BOX_COLOR.items()}

    def _prepare_next_trigger_cycle(self) -> None:
        """触发模式下，当前 SOP 完成后等待下一件的新触发信号。"""
        if not self.external_mode and not self.trigger_controller.requires_trigger:
            return
        if self.detector.prepare_for_next_trigger():
            if not self.external_mode:
                self.trigger_controller.rearm()

    def start(self, external_mode: bool = False) -> None:
        if self.running:
            return
        self.external_mode = bool(external_mode)
        self.camera.start()
        if not self.camera.wait_for_first_frame():
            self.camera.stop()
            raise RuntimeError(f"Camera {self.camera_name} has been opened but failed to read the frame")
        wait_for_trigger = self.external_mode or self.trigger_controller.requires_trigger
        self.detector.start(wait_for_trigger=wait_for_trigger)
        if not self.external_mode:
            self.trigger_controller.start()
        self.running = True
        self.paused = False

    def start_external_cycle(self, sn: str) -> bool:
        """在已打开的外部运行时中启动一件产品，不重复启动相机和模型。"""
        if not self.running or self.paused:
            return False
        if not self.detector.waiting_for_trigger:
            return False
        payload = {
            "value": [sn],
            "SN": sn,
            "SOP_NAME": self.sop_name,
            "CAP_NAME": self.camera_name,
        }
        accepted = self.detector.activate_trigger("external_api", payload)
        if accepted:
            self.external_reference = sn
            self.external_triggered_at = time.time()
        return accepted
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
    def reset(self) -> bool:
        if not self.running:return False
        return self.detector.reset()
    def stop(self) -> None:
        self.running = False
        self.paused = False
        try:
            self.trigger_controller.stop()
        except Exception:
            logger.exception("Failed to stop trigger listener")

        try:
            self.detector.stop()
        except Exception:
            logger.exception("Failed to stop detection thread")

        try:
            self.camera.stop()
        except Exception:
            logger.exception("Failed to stop camera thread")

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

    def iter_server_camera_stream(
        self,
    ) -> Generator[bytes, None, None]:
        """
        Firefox 使用的 MJPEG 兜底流。
        """

        frame_interval = (
            1.0 / SERVER_STREAM_FPS
        )

        next_tick = time.monotonic()

        while self.running:

            if (
                self.camera.cap_status.get()
                not in ACTIVE_STATUS_VALUES

                or self.detector.detector_status
                .get()
                not in ACTIVE_STATUS_VALUES
            ):
                break

            raw_frame = (
                self.camera
                .get_latest_frame()
            )

            if raw_frame is None:
                time.sleep(0.01)
                continue

            # 先按照原始坐标画框。
            processed_frame = process_frame(
                raw_frame,
                self.detector.snapshot(),
            )

            # 再对显示帧进行中心裁剪。
            display_frame = (
                self.camera
                .prepare_display_frame(
                    processed_frame,
                )
            )

            try:
                frame_bytes = encode_jpeg(
                    display_frame,
                    self.camera.display_quality,
                )

            except Exception:
                logger.exception(
                    "MJPEG frame encoding failed"
                )
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + frame_bytes
                + b"\r\n"
            )

            next_tick += frame_interval

            sleep_time = max(
                0.0,
                next_tick - time.monotonic(),
            )

            if sleep_time > 0:
                time.sleep(sleep_time)
    async def close_peer_connections(self) -> None:
        for pc in list(self.peer_connections):
            await pc.close()
            self.peer_connections.discard(pc)


class DetectorWorker:
    """后台检测线程：配置 ONNX_MODEL_PATH 后使用真实 ONNX 模型，否则使用模拟结果。"""

    def __init__(self, camera: CameraManager, model_path: str | None = None, model_name: str | None = None, project_name: str | None = None, sop_name: str | None = None, infer_period_ms: int = 70,hand_infer_period_ms: int = 50):
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
            "manualRegions": [],
            "hands": {},
            "hand_action_points": [],
            "score": 0.0,
            "ok_count": 0,
            "ng_count": 0,
            "feedback": {"events": []},
            "updated_at": 0.0,
        }
        self.paused = False
        self.waiting_for_trigger = False
        self._last_result_storage_error_at = 0.0
        self.on_sop_completed: Callable[[], None] | None = None
        self.trigger_lock = threading.Lock()
        self.pause_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.model_path = model_path
        self.model_name = model_name
        self.project_name = project_name
        self.sop_name = sop_name or project_name
        self.manual_regions_config = normalize_manual_regions_config(
            get_main_config().get("manualRegions")
        )
        self.sop_machine = self._create_sop_machine()
        self._validate_manual_regions_for_active_camera()
        #结果保存器
        self.result_store = SOPResultStore(
            project_name=self.project_name,
            model_name=self.model_name,
            camera_name=self.camera.camera_name,
            sop_config=self.sop_machine.sop_config,
        )
        self.media_recorder = ResultMediaRecorder(
            result_store=self.result_store,
            config=get_main_config().get("resultMedia"),
            status_callback=self._handle_feedback_status,
        )
        self.feedback_dispatcher = StepFeedbackDispatcher(
            project_name=self.project_name,
            sop_name=self.sop_name,
            model_name=self.model_name,
            camera_name=self.camera.camera_name,
            sop_config=self.sop_machine.sop_config,
            status_callback=self._handle_feedback_status,
        )
        self.hand_worker: HandDetectorWorker | None = None
        # self._refresh_hand_tracker()
        self.result["sop"] = self.sop_machine.snapshot(reason="SOP waiting to start")
        self._last_sop_state = self.result["sop"].get("state")
        self._tick = 0
        self.label_class = JsonFile(os.path.join(self.model_path, "cache.json")).read_json_file().get("labeling", {})
        fusion_config = self.sop_machine.detector_fusion_config
        detector_confidence = self.sop_machine.confidence if self.sop_machine.confidence > 0 else 0.5
        self.vision_tracker = LightweightObjectTracker(detector_confidence,fusion_config)
        self.detector = ONNXDetection(onnx_model=os.path.join(self.model_path,self.model_name),classes=self.label_class,confidence=detector_confidence,other_params={"lowConfidence":fusion_config["lowConfidence"],"topK":3})
        self.detector.load_model()

    def _validate_manual_regions_for_active_camera(self) -> None:
        validation_error = validate_sop_manual_region_references(
            self.sop_machine.sop_config,
            self.manual_regions_config,
            active_camera_name=self.camera.camera_name,
        )
        if validation_error:
            raise ValueError(validation_error)

    def _manual_region_detections(self, included_region_keys: set[str]) -> list[dict]:
        return build_manual_region_detections(
            self.manual_regions_config,
            self.camera.camera_name,
            int(self.camera.actual_width or 0),
            int(self.camera.actual_height or 0),
            included_region_keys,
        )
    def _sop_manual_region_detections(self) -> list[dict]:return self._manual_region_detections(collect_sop_manual_region_keys(self.sop_machine.sop_config))
    def _visible_manual_region_detections(self) -> list[dict]:return self._sop_manual_region_detections()
    def _refresh_hand_tracker(self) -> None:
        """按当前SOP是否需要手部识别，惰性创建/销毁 HandTracker，避免不需要时白白耗CPU。"""
        needs_hands = self.sop_machine.requires_hand_tracking
        if needs_hands and self.hand_worker is None:
            # 即使工序只配置单侧手，也必须同时保留左右手检测槽位；否则未配置侧先出现时会占用唯一槽位。
            num_hands = 2
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
            if self.sop_name:
                _, project_config = resolve_sop_definition(config, self.sop_name)
                return SOPStateMachine(project_config, stable_frames=3)
            return SOPStateMachine.from_sop_map(config, stable_frames=3)
        except Exception as e:
            logger.exception("Failed to initialize SOP state machine")
            machine = SOPStateMachine({}, stable_frames=3)
            machine.last_reason = str(e)
            return machine

    def start(self, wait_for_trigger: bool = False) -> None:
        if self.running:return
        self.paused = False
        self.waiting_for_trigger = wait_for_trigger
        self.sop_machine = self._create_sop_machine()
        self.vision_tracker = LightweightObjectTracker(self.sop_machine.confidence if self.sop_machine.confidence > 0 else 0.5,self.sop_machine.detector_fusion_config)
        self._validate_manual_regions_for_active_camera()
        manual_regions = self._visible_manual_region_detections()
        #结果触发器
        self.result_store.set_sop_config(self.sop_machine.sop_config)
        if wait_for_trigger:
            sop_result = self.sop_machine.snapshot(reason="Waiting for configured trigger")
            self.feedback_dispatcher.reset(sop_result,self.sop_machine.sop_config)
            with self.result_lock:
                self.result["sop"] = sop_result
                self.result["manualRegions"] = manual_regions
                self.result["updated_at"] = time.time()
        else:
            self.result_store.start_run(trigger_source="manual",trigger_payload={})
            self.sop_machine.start()
            self._refresh_hand_tracker()
            sop_result = self.sop_machine.snapshot(reason="SOP started")
            self.feedback_dispatcher.reset(sop_result,self.sop_machine.sop_config)
            self._consume_sop_snapshot_safe(sop_result)
        with self.result_lock:
            self.result["manualRegions"] = manual_regions
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
            if self.waiting_for_trigger:
                time.sleep(0.05)
                next_tick = time.monotonic()
                continue
            frame = self.camera.get_latest_frame()
            if frame is not None:
                self.media_recorder.buffer_video_frame(frame)
                detection = self.detector.predict(frame) if self.detector else None
                hands = None
                # 只有当前步骤真的需要手部识别时才跑MediaPipe，减少不必要的开销
                current_step = self.sop_machine.current_step
                if self.hand_worker is not None and current_step is not None and current_step.hand_gate_enabled:
                    hands = self.hand_worker.snapshot()
                if detection is not None:
                    self._update_result(
                        frame,
                        detection[3],
                        hands=hands,
                    )

            next_tick += self.infer_period
            sleep_time = max(0.0, next_tick - time.monotonic())
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _update_result(
        self,
        frame: np.ndarray,
        detection: dict,
        hands=None,
    ) -> None:
        label_box_datas = self.vision_tracker.update(detection.get("datas", []))
        display_detections = [item for item in label_box_datas if item.get("classification_state") == "confirmed" and item.get("high_confidence") is True]
        completed_now = False
        media_events: list[dict] = []
        with self.state_lock:
            visible_manual_regions = self._visible_manual_region_detections()
            media_manual_regions = visible_manual_regions
            observation_boxes = [*label_box_datas,*visible_manual_regions]
            sop_result = self.sop_machine.update(
                observation_boxes,
                hands=hands,
            )
            run_id = self.result_store.current_run_id
            media_events = self._consume_sop_snapshot_safe(sop_result)
            self.feedback_dispatcher.process_snapshot(sop_result, run_id)
            sop_state = sop_result.get("state")
            with self.result_lock:
                self.result["step"] = 1 if self.result.get("step", 1) == 1 else 2
                self.result["gesture"] = "gesture"
                self.result["detections"] = display_detections
                self.result["visionCandidates"] = label_box_datas
                self.result["manualRegions"] = visible_manual_regions
                self.result["hands"] = hands or {}
                self.result["hand_action_points"] = (self.sop_machine.current_hand_action_points(hands) if hands else [])
                self.result["sop"] = sop_result
                if sop_state != self._last_sop_state:
                    if sop_state == "completed":
                        self.result["ok_count"] = self.result.get("ok_count", 0) + 1
                        completed_now = True
                    elif sop_state == "failed":
                        self.result["ng_count"] = self.result.get("ng_count", 0) + 1
                    self._last_sop_state = sop_state
                self.result["updated_at"] = time.time()

        if media_events:
            media_snapshot = self.snapshot()
            media_snapshot["manualRegions"] = media_manual_regions
            self.media_recorder.capture_events(
                event_refs=media_events,
                raw_frame=frame,
                annotated_frame_factory=lambda: process_frame(
                    frame.copy(),
                    media_snapshot,
                ),
            )
        if completed_now:
            self.media_recorder.request_storage_sync_when_idle()

        if completed_now and self.on_sop_completed is not None:
            try:
                self.on_sop_completed()
            except Exception:
                logger.exception("Failed to prepare the next triggered SOP run")

    def _handle_feedback_status(self, event: dict) -> None:
        """Receive status events from feedback worker threads."""
        with self.result_lock:
            feedback = self.result.setdefault("feedback", {"events": []})
            events = feedback.setdefault("events", [])
            events.append(dict(event))
            if len(events) > MAX_FEEDBACK_STATUS_EVENTS:
                del events[:-MAX_FEEDBACK_STATUS_EVENTS]
            self.result["updated_at"] = time.time()

    def _consume_sop_snapshot_safe(self,sop_result:dict) -> list[dict]:
        try:return self.result_store.consume_sop_snapshot(sop_result)
        except Exception as exc:
            now = time.time()
            if now-self._last_result_storage_error_at >= 5:
                self._last_result_storage_error_at = now
                logger.exception("Failed to save SOP snapshot; detection will continue")
                self._handle_feedback_status({"id":f"storage-{time.time_ns()}","status":"failed","channel":"storage","eventType":"result_storage","stepId":(sop_result.get("current_step") or {}).get("id"),"stepName":(sop_result.get("current_step") or {}).get("name","") ,"runId":self.result_store.current_run_id,"target":self.result_store.result_path,"message":str(exc) or exc.__class__.__name__,"timestamp":now})
            return []

    def snapshot(self):
        with self.result_lock:
            snapshot = dict(self.result)
            feedback = self.result.get("feedback", {})
            feedback_events = feedback.get("events", []) if isinstance(feedback, dict) else []
            snapshot["feedback"] = {
                "events": [dict(event) for event in feedback_events if isinstance(event, dict)],
            }
            return snapshot

    def prepare_for_next_trigger(self) -> bool:
        """保持已完成结果可见，但暂停推理并等待下一件触发。"""
        with self.trigger_lock:
            if not self.running or self.waiting_for_trigger:
                return False
            with self.state_lock:
                if self.sop_machine.snapshot().get("state") != "completed":
                    return False
                self.waiting_for_trigger = True
                sop_result = self.sop_machine.snapshot(
                    matched=False,
                    reason="Waiting for the next configured trigger",
                )
                with self.result_lock:
                    self.result["gesture"] = "idle"
                    self.result["bbox"] = []
                    self.result["detections"] = []
                    self.result["manualRegions"] = (
                        self._visible_manual_region_detections()
                    )
                    self.result["hands"] = {}
                    self.result["hand_action_points"] = []
                    self.result["sop"] = sop_result
                    self.result["updated_at"] = time.time()
            return True

    def activate_trigger(self, source: str, payload: dict) -> bool:
        """启动当前零件；SOP 进行期间 TriggerController 会拒绝后续信号。"""
        with self.trigger_lock:
            if not self.running or not self.waiting_for_trigger:
                return False
            with self.state_lock:
                # =====================================
                # 真正生产开始
                #
                # USB扫码枪：
                # payload.value 可以作为产品追溯码
                #
                # HTTP：
                # parameters 会完整保存
                #
                # Modbus：
                # 保存信号信息
                # =====================================
                self.result_store.start_run(trigger_source=source, trigger_payload=payload)
                self.sop_machine.start()

                self.waiting_for_trigger = False
                self._refresh_hand_tracker()
                sop_result = self.sop_machine.snapshot(
                    matched=False,
                    reason=f"Detection started by {source} trigger",
                )
                self.feedback_dispatcher.reset(sop_result,self.sop_machine.sop_config)
                # 先记录初始状态
                self._consume_sop_snapshot_safe(sop_result)
                self._last_sop_state = sop_result.get("state")
                with self.result_lock:
                    self.result.update({
                        "step": 1,
                        "gesture": "idle",
                        "bbox": [],
                        "detections": [],
                        "manualRegions":
                            self._visible_manual_region_detections(),
                        "hands": {},
                        "hand_action_points": [],
                        "score": 0.0,
                        "ok_count": 0,
                        "ng_count": 0,
                        "sop": sop_result,
                        "trigger": {
                            "source": source,
                            "payload": payload,
                        },
                        "updated_at": time.time(),
                    })
            return True
    def pause(self) -> bool:
        """暂停 AI 推理和 SOP 状态推进，但不销毁检测线程。"""
        with self.pause_lock:
            if not self.running:return False
            if self.paused:return True
            with self.state_lock:
                self.paused = True
                self.sop_machine.pause()
                sop_result = self.sop_machine.snapshot(matched=False,reason="SOP paused",)
                self._consume_sop_snapshot_safe(sop_result)
                with self.result_lock:
                    self.result["sop"] = sop_result
                    self.result["hands"] = {}
                    self.result["hand_action_points"] = []
                    self.result["updated_at"] = time.time()
            return True


    def resume(self) -> bool:
        """从暂停位置继续检测。"""
        with self.pause_lock:
            if not self.running: return False
            if not self.paused:return True
            with self.state_lock:
                self.sop_machine.resume()
                self.paused = False
                sop_result = self.sop_machine.snapshot(matched=False,reason="SOP resumed")
                self._consume_sop_snapshot_safe(sop_result)
                with self.result_lock:
                    self.result["sop"] = sop_result
                    self.result["updated_at"] = time.time()
            return True
    def reset(self)-> dict | None:
        """
        将 SOP 复位到第一步。
        运行状态复位后继续运行；
        暂停状态复位后仍保持暂停。
        """
        with self.pause_lock:
            if not self.running:return None
            keep_paused = self.paused
            with self.state_lock:
                previous_run_id = self.result_store.current_run_id
                self.result_store.finish_run(execution_status="reset", reason="Manual SOP reset")
                self.media_recorder.request_storage_sync_when_idle()
                self.result_store.start_run(trigger_source="reset", trigger_payload={"previous_run_id": previous_run_id},keep_session=True)
                # start() 本身已经会清除所有步骤状态、
                # matched_count、时间、失败状态和 current_index。
                self.sop_machine.start()
                if keep_paused:
                    self.sop_machine.pause()
                    reason = "SOP reset and paused"
                else:
                    reason = "SOP reset"
                sop_result = self.sop_machine.snapshot(matched=False,reason=reason)
                self.feedback_dispatcher.reset(sop_result,self.sop_machine.sop_config)
                self._consume_sop_snapshot_safe(sop_result)
                self._last_sop_state = sop_result.get("state")

                with self.result_lock:
                    self.result.update({
                        "step": 1,
                        "gesture": "idle",
                        "bbox": [],
                        "detections": [],
                        "manualRegions":
                            self._visible_manual_region_detections(),
                        "hands": {},
                        "hand_action_points": [],
                        "score": 0.0,
                        "ok_count": 0,
                        "ng_count": 0,
                        "updated_at": time.time(),
                        "sop": sop_result,
                    })

            return dict(self.result)
    def stop(self) -> None:
        self.result_store.finish_run(execution_status="stopped", reason="Manual detection stop")
        self.feedback_dispatcher.shutdown()
        self.running = False
        self.paused = False
        self.waiting_for_trigger = False
        self.detector_status.set(0)
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.thread = None
        self.media_recorder.shutdown()
        if self.hand_worker is not None:
            try:
                self.hand_worker.stop()
            except Exception:
                logger.exception("Stop hand detection thread failed")
            finally:
                self.hand_worker = None
        with self.result_lock:
            self.result = {
                "step": None,
                "gesture": "idle",
                "bbox": [],
                "detections": [],
                "manualRegions": [],
                "hands": {},
                "hand_action_points": [],
                "score": 0.0,
                "ok_count": 0,
                "ng_count": 0,
                "feedback": {"events": []},
                "updated_at": time.time(),
                "sop": None,
            }


class CameraTrack(VideoStreamTrack):
    """WebRTC 视频轨：Chrome/Edge 通过 /offer 拉取这路处理后的视频。"""

    def __init__(self, runtime: DetectionRuntime):
        super().__init__()
        self.runtime = runtime

    async def recv(self):

        pts, time_base = (
            await self.next_timestamp()
        )

        raw_frame = (
            self.runtime.camera
            .get_latest_frame()
        )

        while raw_frame is None:

            await asyncio.sleep(0.005)

            raw_frame = (
                self.runtime.camera
                .get_latest_frame()
            )

        # 检测框坐标基于完整原始帧，
        # 因此必须先画框。
        processed_frame = process_frame(
            raw_frame,
            self.runtime.detector.snapshot(),
        )

        # WebRTC 接收 ndarray，
        # 在这里应用显示区域和显示清晰度。
        display_frame = (
            self.runtime.camera
            .prepare_display_frame(
                processed_frame,
            )
        )

        video_frame = (
            VideoFrame.from_ndarray(
                display_frame,
                format="bgr24",
            )
        )

        video_frame.pts = pts
        video_frame.time_base = time_base

        return video_frame


def process_frame(image: np.ndarray, result: dict | None = None) -> np.ndarray:
    """叠加检测结果并返回处理后画面。"""
    detections = [
        *(result.get("detections") or []),
        *(result.get("manualRegions") or []),
    ] if result else []
    from_area_labels, target_area_labels = collect_sop_area_labels(
        result.get("sop") if result else None
    )
    annotations = []
    for item in detections or []:
        bbox = item.get("points", [])
        if len(bbox) == 4:
            x1, y1, x2, y2 = [int(value) for value in bbox]
        elif (len(bbox) == 2 and all(isinstance(point, (list, tuple)) and len(point) == 2 for point in bbox)):
            x1, y1 = [int(value) for value in bbox[0]]
            x2, y2 = [int(value) for value in bbox[1]]
        else:
            continue
        obj_label = item.get("label", "default")
        is_manual_region = item.get("detectionType") == "manual_region"
        label = (
            str(item.get("displayLabel") or item.get("regionName") or obj_label)
            if is_manual_region
            else f"{obj_label} {float(item.get('score', 0.0)):.2f}"
        )
        if is_manual_region:
            try:
                color = list(
                    reversed(
                        ImageColor.getrgb(
                            str(item.get("color") or "#409EFF")
                        )
                    )
                )
            except (TypeError, ValueError):
                color = BOX_COLOR.get(
                    "default",
                    DEFAULT_BOX_COLOR["default"],
                )
        else:
            color = BOX_COLOR.get(
                obj_label,
                BOX_COLOR.get("default", DEFAULT_BOX_COLOR["default"]),
            )
        annotations.append(
            {
                "bounds": (x1, y1, x2, y2),
                "label": label,
                "color": color,
                "fill": should_fill_area(
                    obj_label,
                    from_area_labels,
                    target_area_labels,
                    BOX_STYLE_CONFIG,
                ),
            }
        )

    filled_annotations = [annotation for annotation in annotations if annotation["fill"]]
    if filled_annotations:
        area_fill_alpha = normalize_area_fill_alpha(
            BOX_STYLE_CONFIG.get("areaFillAlpha"),
            DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"],
        )
        overlay = image.copy()
        for annotation in filled_annotations:
            x1, y1, x2, y2 = annotation["bounds"]
            cv2.rectangle(
                overlay,
                (x1, y1),
                (x2, y2),
                annotation["color"],
                thickness=cv2.FILLED,
            )
        cv2.addWeighted(
            overlay,
            area_fill_alpha,
            image,
            1.0 - area_fill_alpha,
            0,
            dst=image,
        )

    for annotation in annotations:
        x1, y1, x2, y2 = annotation["bounds"]
        color = annotation["color"]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, BOX_STYLE_CONFIG.get("boxThickness", 2))
        cv2.putText(image, annotation["label"], (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, BOX_STYLE_CONFIG.get("fontScale", 0.5), color, BOX_STYLE_CONFIG.get("fontThickness", 2))
    if result:
        HandTracker.draw_hands(
            image,
            result.get("hands"),
            HAND_STYLE_CONFIG,
        )
        HandTracker.draw_action_points(image, result.get("hand_action_points"))
    return image
