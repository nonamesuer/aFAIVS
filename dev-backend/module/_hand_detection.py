# module/_hand_detection.py
import time
import logging
import cv2
import threading
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)
from module._base import MEDIAPIPE_MODEL_PATH
from module._base import CapStatus, DetectorStatus

logger = logging.getLogger(__name__)


class HandTracker:
    """基于 MediaPipe Tasks HandLandmarker 的手部关键点检测器，VIDEO 模式（同步）。

    NOTE: 如果摄像头画面是非镜像的正对工位画面，保持 mirrored=False，
    检测到的左右手标签会自动反转以对应操作员真实的左右手；如果发现反了就切换这个开关。
    """

    LANDMARK_COUNT = 21
    HAND_COLORS = {"l": (0, 0, 255), "r": (0, 255, 0)}
    ACTION_POINT_COLOR = (0, 255, 255)
    HAND_CONNECTIONS = [
        (0, 1), (1, 2), (2, 3), (3, 4),          # 拇指
        (0, 5), (5, 6), (6, 7), (7, 8),          # 食指
        (5, 9), (9, 10), (10, 11), (11, 12),     # 中指
        (9, 13), (13, 14), (14, 15), (15, 16),   # 无名指
        (13, 17), (17, 18), (18, 19), (19, 20),  # 小指
        (0, 17),                                  # 手掌根部闭环
    ]
    def __init__(
        self,
        num_hands: int = 2,
        min_hand_detection_confidence: float = 0.2,
        min_hand_presence_confidence: float = 0.2,
        min_tracking_confidence: float = 0.2,
        mirrored: bool = True,
    ):
        base_options = BaseOptions(model_asset_path=MEDIAPIPE_MODEL_PATH)
        options = HandLandmarkerOptions(
            base_options=base_options,
            running_mode=RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_hand_detection_confidence,
            min_hand_presence_confidence=min_hand_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = HandLandmarker.create_from_options(options)
        self._mirrored = mirrored
        self._start_time = time.monotonic()
        self._last_timestamp_ms = -1

    def detect(self, frame_bgr,max_width:int=640) -> dict[str, list[tuple[float, float]]]:
        """返回 {"l": [(x,y)*21], "r": [(x,y)*21]}，坐标为像素坐标。"""
        if frame_bgr is None:
            return {}
        height, width = frame_bgr.shape[:2]
        proc_frame = frame_bgr
        if width > max_width:
            proc_height = int(height * max_width / width)
            proc_frame = cv2.resize(frame_bgr, (max_width, proc_height), interpolation=cv2.INTER_LINEAR)
        frame_rgb = cv2.cvtColor(proc_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        # VIDEO 模式要求时间戳严格递增
        timestamp_ms = max(int((time.monotonic() - self._start_time) * 1000),self._last_timestamp_ms + 1,)
        self._last_timestamp_ms = timestamp_ms
        try:
            result = self._landmarker.detect_for_video(mp_image, timestamp_ms)
        except Exception:
            logger.exception("MediaPipe hand detection failed")
            return {}

        hands: dict[str, list[tuple[float, float]]] = {}
        if not result.hand_landmarks:return hands
        for idx, hand_landmarks in enumerate(result.hand_landmarks):
            label = "r"
            if idx < len(result.handedness):
                mp_label = result.handedness[idx][0].category_name  # "Left" / "Right"
                is_left = mp_label == "Left"
                if not self._mirrored:
                    is_left = not is_left
                label = "l" if is_left else "r"
            points = [(lm.x * width, lm.y * height) for lm in hand_landmarks]
            hands[label] = points
        return hands
    @classmethod
    def draw_hands(cls,image,hands:dict | None) -> None:
        """在图像上绘制手部关键点和骨架。hands 为 detect() 的返回值。"""
        if hands is None:return
        for side,points in hands.items():
            if not points:continue
            color = cls.HAND_COLORS.get(side,(255, 255, 0))
            for a,b in cls.HAND_CONNECTIONS:
                if a < len(points) and b < len(points):
                    pa = (int(points[a][0]), int(points[a][1]))
                    pb = (int(points[b][0]), int(points[b][1]))
                    cv2.line(image, pa, pb, color, 2)
            for x,y in points:
                cv2.circle(image, (int(x), int(y)), 4, color, -1)
            wrist_x,wrist_y = points[0]
            cv2.putText(image, side.upper(), (int(wrist_x) - 10, int(wrist_y) + 25),cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    @classmethod
    def draw_action_points(cls, image, action_points: list[tuple[float, float]] | None) -> None:
        """把SOP状态机实际用来判断抓取/放下的动作点单独高亮出来，方便调试。"""
        if not action_points:
            return
        for x, y in action_points:
            cv2.circle(image, (int(x), int(y)), 10, cls.ACTION_POINT_COLOR, 2)
            cv2.drawMarker(image, (int(x), int(y)), cls.ACTION_POINT_COLOR,
                            markerType=cv2.MARKER_CROSS, markerSize=14, thickness=2)
            
    def close(self):
        self._landmarker.close()

class HandDetectorWorker:
    def __init__(
        self,
        camera,
        hand_tracker: HandTracker,
        infer_period_ms: int = 50,
        gate_fn=None,
        stale_after_s: float = 0.3,
    ):
        self.camera = camera
        self.hand_tracker = hand_tracker
        self.infer_period = infer_period_ms / 1000.0
        self.stale_after_s = stale_after_s
        self.gate_fn = gate_fn  # 可选：返回 bool，决定这一轮要不要真的跑检测
        self.running = False
        self.thread = None
        self.result_lock = threading.Lock()
        self._latest_hands: dict = {}
        self._latest_updated_at: float = 0.0
        self.cap_status = CapStatus()
        self.detector_status = DetectorStatus()
    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
    def _loop(self) -> None:
        next_tick = time.monotonic()
        while self.running:
            cap_status = self.cap_status.get()
            if cap_status == 2:
                time.sleep(1)
                continue
            elif cap_status != 1:
                self.running = False
                return

            if self.gate_fn is None or self.gate_fn():
                frame = self.camera.get_latest_frame()
                if frame is not None:
                    hands = self.hand_tracker.detect(frame)
                    with self.result_lock:
                        self._latest_hands = hands
                        self._latest_updated_at = time.time()
            else:
                # 当前步骤不需要手部识别，清空结果，避免显示过期的手部骨架
                with self.result_lock:
                    self._latest_hands = {}

            next_tick += self.infer_period
            sleep_time = max(0.0, next_tick - time.monotonic())
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                # 万一某一轮明显超时，重新同步计时基准，避免持续欠账
                next_tick = time.monotonic()
    def snapshot(self) -> dict:
        """非阻塞获取最新一次手部检测结果，过期则视为空（避免用陈旧数据误判）。"""
        with self.result_lock:
            if time.time() - self._latest_updated_at > self.stale_after_s:
                return {}
            return dict(self._latest_hands)

    def stop(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.hand_tracker.close()