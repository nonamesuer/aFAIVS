from __future__ import annotations

import asyncio
import logging
import threading
import time

import cv2

from module._base import (
    CapStatus,
    get_camera_index,
    graph,
    send_websocket_json,
)

from module._camera_settings import (
    CameraSettings,
    apply_display_quality,
    configure_capture,
    crop_display_area,
    load_camera_settings,
    normalize_camera_settings,
)


logger = logging.getLogger(__name__)


class CameraManager:
    """
    相机采集管理器。

    latest_frame 始终保存：
        未裁剪、未压缩的原始采集帧。

    ONNX / MediaPipe：
        使用 latest_frame。

    WebRTC / MJPEG：
        调用 prepare_display_frame() 后显示。
    """

    def __init__(
        self,
        camera_index: int = 0,
        camera_name: str = "",
        target_fps: float = 30.0,
    ):
        self.camera_index = camera_index
        self.camera_name = camera_name

        self.target_fps = target_fps
        self.frame_interval = (
            1.0 / target_fps
        )

        self.settings = (
            load_camera_settings(
                camera_name
            )
        )

        self.actual_width = 0
        self.actual_height = 0
        self.actual_fps = 0.0

        self.cap: (
            cv2.VideoCapture | None
        ) = None

        self.running = False

        self.thread: (
            threading.Thread | None
        ) = None

        self.heartbeat_thread: (
            threading.Thread | None
        ) = None

        self.frame_lock = (
            threading.Lock()
        )

        self.capture_lock = (
            threading.RLock()
        )

        self.settings_lock = (
            threading.RLock()
        )

        self.latest_frame = None

        self.reconnnect_times = 0

        self.cap_status = CapStatus()

        # 区分用户实时修改参数和真实断线。
        self._reconfiguring = False

    # =====================================================
    # 配置读取
    # =====================================================

    @property
    def display_quality(self) -> int:
        with self.settings_lock:
            return self.settings.clarity

    def settings_snapshot(
        self,
    ) -> dict:
        """
        返回请求参数和相机驱动实际采用的参数。
        """

        with self.settings_lock:
            data = (
                self.settings.to_dict()
            )

        data.update(
            {
                "actual_width":
                    self.actual_width,

                "actual_height":
                    self.actual_height,

                "actual_fps":
                    self.actual_fps,

                "resolution_matched": (
                    self.actual_width
                    == data["width"]

                    and self.actual_height
                    == data["height"]
                ),
            }
        )

        return data

    # =====================================================
    # 打开相机
    # =====================================================

    def _open_capture(
        self,
        index: int,
        settings: CameraSettings,
    ) -> tuple[
        cv2.VideoCapture,
        dict,
    ]:

        capture = cv2.VideoCapture(
            index,
            cv2.CAP_DSHOW,
        )

        if not capture.isOpened():
            capture.release()

            raise RuntimeError(
                f"无法打开摄像头 index={index}"
            )

        report = configure_capture(
            capture,
            settings,
            self.target_fps,
        )

        if not report[
            "resolution_matched"
        ]:
            logger.warning(
                (
                    "Camera %s requested "
                    "%sx%s but driver "
                    "reported %sx%s"
                ),
                self.camera_name,

                report[
                    "requested_width"
                ],
                report[
                    "requested_height"
                ],

                report[
                    "actual_width"
                ],
                report[
                    "actual_height"
                ],
            )

        else:
            logger.info(
                (
                    "Camera %s applied "
                    "capture=%sx%s "
                    "area=%s clarity=%s "
                    "fps=%s"
                ),

                self.camera_name,

                report[
                    "actual_width"
                ],
                report[
                    "actual_height"
                ],

                settings.area,
                settings.clarity,

                report[
                    "actual_fps"
                ],
            )

        return capture, report

    @staticmethod
    def _read_first_frame(
        capture: cv2.VideoCapture,
        attempts: int = 20,
    ):
        for _ in range(
            max(1, attempts)
        ):
            ok, frame = capture.read()

            if (
                ok
                and frame is not None
                and frame.size
            ):
                return frame

            time.sleep(0.02)

        return None

    def _install_capture(
        self,
        capture: cv2.VideoCapture,
        first_frame,
        report: dict,
    ) -> None:

        with self.capture_lock:
            self.cap = capture

        if first_frame is not None:
            height, width = (
                first_frame.shape[:2]
            )

            self.actual_width = width
            self.actual_height = height

            with self.frame_lock:
                self.latest_frame = (
                    first_frame
                )

        else:
            self.actual_width = int(
                report.get(
                    "actual_width",
                    0,
                )
            )

            self.actual_height = int(
                report.get(
                    "actual_height",
                    0,
                )
            )

        self.actual_fps = float(
            report.get(
                "actual_fps",
                0.0,
            )
        )

    # =====================================================
    # 生命周期
    # =====================================================

    def start(self) -> None:

        if self.running:
            return

        # 每次正式启动都重新读取最新配置。
        settings = load_camera_settings(
            self.camera_name
        )

        with self.settings_lock:
            self.settings = settings

        capture, report = (
            self._open_capture(
                self.camera_index,
                settings,
            )
        )

        with self.capture_lock:
            self.cap = capture

        self.cap_status.set(1)
        self.running = True

        self.thread = threading.Thread(
            target=self._update_loop,
            name=(
                "camera-capture-"
                f"{self.camera_name}"
            ),
            daemon=True,
        )

        self.thread.start()

        self.heartbeat_thread = (
            threading.Thread(
                target=self._heartbeat,
                name=(
                    "camera-heartbeat-"
                    f"{self.camera_name}"
                ),
                daemon=True,
            )
        )

        self.heartbeat_thread.start()

        self.actual_width = int(
            report.get(
                "actual_width",
                0,
            )
        )

        self.actual_height = int(
            report.get(
                "actual_height",
                0,
            )
        )

        self.actual_fps = float(
            report.get(
                "actual_fps",
                0.0,
            )
        )

    def stop(self) -> None:

        self.running = False
        self.cap_status.set(0)

        with self.capture_lock:
            capture = self.cap
            self.cap = None

            if capture is not None:
                try:
                    capture.release()

                except Exception:
                    logger.exception(
                        "释放摄像头失败"
                    )

        if (
            self.thread
            and self.thread.is_alive()
        ):
            self.thread.join(
                timeout=2.0
            )

        if (
            self.heartbeat_thread
            and self.heartbeat_thread
            .is_alive()
        ):
            self.heartbeat_thread.join(
                timeout=2.0
            )

        with self.frame_lock:
            self.latest_frame = None

        self.thread = None
        self.heartbeat_thread = None

        self.reconnnect_times = 0
        self._reconfiguring = False

    # =====================================================
    # 实时应用新配置
    # =====================================================

    def apply_settings(
        self,
        values: dict,
    ) -> dict:
        """
        配置保存后，将配置应用到正在运行的相机。

        area / clarity:
            不需要重开相机，立即生效。

        width / height:
            需要安全释放并重新打开 VideoCapture。
        """

        new_settings = (
            normalize_camera_settings(
                values
            )
        )

        with self.settings_lock:
            old_settings = self.settings

            resolution_changed = (
                old_settings.width
                != new_settings.width

                or old_settings.height
                != new_settings.height
            )

            self.settings = new_settings

        if (
            self.running
            and resolution_changed
        ):
            self._reconfigure_capture(
                new_settings,
                old_settings,
            )

        logger.info(
            "Camera %s settings updated: %s",
            self.camera_name,
            self.settings_snapshot(),
        )

        return self.settings_snapshot()

    def _reconfigure_capture(
        self,
        new_settings: CameraSettings,
        old_settings: CameraSettings,
    ) -> None:
        """
        运行中修改真实采集分辨率。

        新配置失败时，自动恢复旧分辨率。
        """

        self._reconfiguring = True
        self.cap_status.set(2)

        with self.frame_lock:
            self.latest_frame = None

        with self.capture_lock:
            old_capture = self.cap
            self.cap = None

            if old_capture is not None:
                old_capture.release()

        try:
            index = get_camera_index(
                self.camera_name
            )

            if index is None:
                raise RuntimeError(
                    "Camera is not available"
                )

            self.camera_index = index

            new_capture, new_report = (
                self._open_capture(
                    index,
                    new_settings,
                )
            )

            first_frame = (
                self._read_first_frame(
                    new_capture
                )
            )

            if first_frame is None:
                new_capture.release()

                raise RuntimeError(
                    (
                        f"摄像头 "
                        f"{self.camera_name} "
                        "应用新分辨率后"
                        "无法读取画面"
                    )
                )

            self._install_capture(
                new_capture,
                first_frame,
                new_report,
            )

            self.cap_status.set(1)

        except Exception as new_error:

            logger.exception(
                "应用相机新分辨率失败，"
                "开始恢复旧配置"
            )

            with self.settings_lock:
                self.settings = (
                    old_settings
                )

            try:
                rollback_capture, (
                    rollback_report
                ) = self._open_capture(
                    self.camera_index,
                    old_settings,
                )

                rollback_frame = (
                    self._read_first_frame(
                        rollback_capture
                    )
                )

                if rollback_frame is None:
                    rollback_capture.release()

                    raise RuntimeError(
                        "恢复旧相机配置后"
                        "仍无法读取画面"
                    )

                self._install_capture(
                    rollback_capture,
                    rollback_frame,
                    rollback_report,
                )

                self.cap_status.set(1)

            except Exception as rollback_error:

                self.cap_status.set(3)
                self.running = False

                raise RuntimeError(
                    (
                        "应用新相机配置失败，"
                        "且无法恢复旧配置："
                        f"{rollback_error}"
                    )
                ) from new_error

            raise RuntimeError(
                (
                    "应用新相机配置失败，"
                    "已恢复旧配置："
                    f"{new_error}"
                )
            ) from new_error

        finally:
            self._reconfiguring = False

    # =====================================================
    # 帧读取
    # =====================================================

    def _update_loop(self) -> None:

        next_tick = time.monotonic()

        while self.running:

            status = (
                self.cap_status.get()
            )

            if status == 2:
                time.sleep(0.05)
                next_tick = (
                    time.monotonic()
                )
                continue

            if status != 1:
                return

            with self.capture_lock:
                capture = self.cap

                if capture is None:
                    ok, frame = False, None

                else:
                    ok, frame = (
                        capture.read()
                    )

            if (
                ok
                and frame is not None
                and frame.size
            ):
                (
                    self.actual_height,
                    self.actual_width,
                ) = frame.shape[:2]

                with self.frame_lock:
                    # 保持完整原始帧。
                    self.latest_frame = frame

            next_tick += (
                self.frame_interval
            )

            sleep_time = max(
                0.0,
                next_tick
                - time.monotonic(),
            )

            if sleep_time > 0:
                time.sleep(sleep_time)

            elif (
                next_tick
                < time.monotonic() - 1
            ):
                next_tick = (
                    time.monotonic()
                )

    def get_latest_frame(self):
        """
        返回未裁剪、未压缩的原始帧。

        ONNX 与 MediaPipe 必须使用此方法。
        """

        with self.frame_lock:

            if self.latest_frame is None:
                return None

            return (
                self.latest_frame.copy()
            )

    def prepare_display_frame(
        self,
        frame,
        *,
        apply_quality: bool = False,
    ):
        """
        只对浏览器显示帧进行裁剪和质量处理。
        """

        if frame is None:
            return None

        with self.settings_lock:
            settings = self.settings

        display_frame = (
            crop_display_area(
                frame,
                settings.area,
            )
        )

        if apply_quality:
            display_frame = (
                apply_display_quality(
                    display_frame,
                    settings.clarity,
                )
            )

        return display_frame

    def wait_for_first_frame(
        self,
        timeout: float = 3.0,
    ) -> bool:

        deadline = (
            time.monotonic()
            + max(
                0.1,
                float(timeout),
            )
        )

        while (
            self.running
            and time.monotonic()
            < deadline
        ):
            with self.frame_lock:
                if (
                    self.latest_frame
                    is not None
                ):
                    return True

            time.sleep(0.02)

        return False

    # =====================================================
    # 断线重连
    # =====================================================

    def _heartbeat(self) -> None:

        while self.running:

            if self._reconfiguring:
                time.sleep(0.1)
                continue

            alive = (
                self._check_camera_alive()
            )

            if not alive:

                self.cap_status.set(2)

                with self.capture_lock:
                    capture = self.cap
                    self.cap = None

                    if capture is not None:
                        capture.release()

                logger.warning(
                    (
                        "Camera index=%s "
                        "(%s) disconnected!"
                    ),
                    self.camera_index,
                    self.camera_name,
                )

                asyncio.run(
                    self._reopen_if_needed()
                )

            else:
                time.sleep(1)

    def _check_camera_alive(
        self,
    ) -> bool:

        if self._reconfiguring:
            return True

        if self.cap_status.get() == 2:
            return True

        with self.capture_lock:
            if self.cap is None:
                return False

        devices = graph.get_input_devices()

        return (
            self.camera_name
            in devices
        )

    async def _reopen_if_needed(
        self,
    ) -> None:

        try:
            max_retries = 5

            logger.warning(
                (
                    "Camera %s (%s) offline, "
                    "will attempt reconnection"
                ),
                self.camera_index,
                self.camera_name,
            )

            while (
                self.running
                and self.reconnnect_times
                < max_retries
            ):

                self.reconnnect_times += 1

                await send_websocket_json(
                    {
                        "camera_status": {
                            "status":
                                "reconnecting",

                            "message": (
                                "Camera is offline, "
                                "attempting to reconnect "
                                f"{self.reconnnect_times}/"
                                f"{max_retries}..."
                            ),
                        }
                    }
                )

                devices = (
                    graph.get_input_devices()
                )

                if (
                    self.camera_name
                    not in devices
                ):
                    await asyncio.sleep(2)
                    continue

                index = get_camera_index(
                    self.camera_name
                )

                if index is None:
                    await asyncio.sleep(2)
                    continue

                # 重连时重新加载磁盘中的最新配置。
                settings = (
                    load_camera_settings(
                        self.camera_name
                    )
                )

                with self.settings_lock:
                    self.settings = settings

                try:
                    new_capture, report = (
                        self._open_capture(
                            index,
                            settings,
                        )
                    )

                    first_frame = (
                        self._read_first_frame(
                            new_capture
                        )
                    )

                    if first_frame is None:
                        new_capture.release()

                        raise RuntimeError(
                            (
                                "Camera reopened "
                                "but returned no frame"
                            )
                        )

                except Exception:

                    logger.exception(
                        (
                            "Failed to reopen "
                            "camera %s, retry %s"
                        ),
                        self.camera_name,
                        self.reconnnect_times,
                    )

                    await asyncio.sleep(2)
                    continue

                if not self.running:
                    new_capture.release()
                    return

                self.camera_index = index

                self._install_capture(
                    new_capture,
                    first_frame,
                    report,
                )

                self.cap_status.set(1)
                self.reconnnect_times = 0

                await send_websocket_json(
                    {
                        "camera_status": {
                            "status":
                                "reconnected",

                            "message": (
                                "Camera reconnected "
                                "successfully"
                            ),
                        }
                    }
                )

                return

            if not self.running:
                return

            self.cap_status.set(3)
            self.running = False

            await send_websocket_json(
                {
                    "camera_status": {
                        "status":
                            "disconnected",

                        "message": (
                            "Failed to reconnect "
                            "camera after "
                            f"{max_retries} attempts"
                        ),
                    }
                }
            )

        except Exception as exc:

            if not self.running:
                return

            self.running = False
            self.cap_status.set(3)

            logger.exception(
                "Error while trying "
                "to reopen camera"
            )

            await send_websocket_json(
                {
                    "camera_status": {
                        "status":
                            "disconnected",

                        "message": (
                            "Error while trying "
                            "to reopen camera: "
                            f"{exc}"
                        ),
                    }
                }
            )