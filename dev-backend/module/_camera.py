import threading
import cv2
import time
import logging
import asyncio
from module._base import send_websocket_json,graph,get_camera_index,CapStatus
logger = logging.getLogger(__name__)
class CameraManager:
    """后台采集线程：持续读取 USB 摄像头最新帧，供 WebRTC/MJPEG 共用。"""
    def __init__(self, camera_index: int = 0, camera_name: str = "", target_fps: float = 30.0):
        self.camera_index = camera_index
        self.camera_name = camera_name
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        self.cap = None
        self.running = False
        self.thread = None
        self.frame_lock = threading.Lock()
        self.heartbeat_thread = None
        self.latest_frame = None
        self.reconnnect_times = 0
        self.cap_status = CapStatus()
    def start(self) -> None:
        
        if self.running:
            return
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开摄像头 index={self.camera_index}")
        self.cap_status.set(1)
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        self.heartbeat_thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.heartbeat_thread.start()

    def _update_loop(self) -> None:
        if self.cap is None:
            return
        next_tick = time.monotonic()
        while self.running:
            if self.cap_status.get() == 2:
                self.latest_frame = None
                time.sleep(1)
                continue
            elif self.cap_status.get() != 1:return
            ok, frame = self.cap.read()
            if ok:
                with self.frame_lock:
                    self.latest_frame = frame
            next_tick += self.frame_interval
            sleep_time = max(0.0, next_tick - time.monotonic())
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_latest_frame(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def stop(self) -> None:
        self.running = False
        self.cap_status.set(0)
        # 先释放 VideoCapture，防止 cap.read() 阻塞线程退出
        cap = self.cap
        self.cap = None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                logger.exception("释放摄像头失败")

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2.0)
        with self.frame_lock:
            self.latest_frame = None
        self.thread = None
        self.heartbeat_thread = None
        self.reconnnect_times = 0

    def _heartbeat(self):
        """心跳函数，定时检查摄像头是否正常工作"""
        while self.running:
            alive = self._check_camera_alive()
            if not alive:
                self.cap_status.set(2)
                self.cap.release()
                self.cap = None
                logger.warning(f"Camera index={self.camera_index} ({self.camera_name}) disconnected!")
                asyncio.run(self._reopen_if_needed())
            else:
                time.sleep(1)
    def _check_camera_alive(self):
        """读取一帧来判断摄像头是否真的在线"""
        if self.cap_status.get() == 2 or not self.cap: return False
        cap_devices = graph.get_input_devices()
        if self.camera_name not in cap_devices:return False
        # ret, frame = self.cap.read()
        # if not ret or frame is None:return False
        return True
    async def _reopen_if_needed(self):
        """
        摄像头异常断开时尝试重连。

        一旦用户点击停止，self.running=False，
        重连过程必须立即退出。
        """
        try:
            max_retries = 5
            logger.warning("Camera %s (%s) offline, will attempt reconnection",self.camera_index,self.camera_name)
            while self.running and self.reconnnect_times < max_retries:
                self.reconnnect_times += 1
                await send_websocket_json({
                    "camera_status": {
                        "status": "reconnecting",
                        "message": (
                            "Camera is offline, attempting to "
                            f"reconnect {self.reconnnect_times}/"
                            f"{max_retries}..."
                        ),
                    }
                })
                if not self.running:return
                cap_devices = graph.get_input_devices()
                if self.camera_name not in cap_devices:
                    logger.error("Camera %s not found in devices: %s",self.camera_name,cap_devices,)
                    await asyncio.sleep(2)
                    continue
                index = get_camera_index(self.camera_name)
                if index is None:
                    await asyncio.sleep(2)
                    continue
                new_cap = cv2.VideoCapture(index,cv2.CAP_DSHOW)
                if not new_cap.isOpened():
                    new_cap.release()
                    logger.error("Failed to reopen camera %s, retry %s",self.camera_name,self.reconnnect_times)
                    await asyncio.sleep(2)
                    continue
                # 打开成功后再次检查是否已经收到停止命令。
                if not self.running:
                    new_cap.release()
                    return
                self.camera_index = index
                self.cap = new_cap
                self.cap_status.set(1)
                self.reconnnect_times = 0
                logger.info("Successfully reopened camera %s (%s)",self.camera_index,self.camera_name)
                await send_websocket_json({
                    "camera_status": {
                        "status": "reconnected",
                        "message": "Camera reconnected successfully",
                    }
                })

                return
            if not self.running:return
            self.cap_status.set(3)
            self.running = False
            await send_websocket_json({
                "camera_status": {
                    "status": "disconnected",
                    "message": (
                        f"Failed to reconnect camera after "
                        f"{max_retries} attempts"
                    ),
                }
            })

        except Exception as exc:
            if not self.running:return
            self.running = False
            self.cap_status.set(3)
            logger.exception("Error while trying to reopen camera")
            await send_websocket_json({
                "camera_status": {
                    "status": "disconnected",
                    "message": (
                        "Error while trying to reopen camera: "
                        f"{exc}"
                    ),
                }
            })