from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from module._base import get_main_config


DEFAULT_CAMERA_WIDTH = 640
DEFAULT_CAMERA_HEIGHT = 480
DEFAULT_DISPLAY_AREA = 0
DEFAULT_DISPLAY_CLARITY = 50


@dataclass(frozen=True)
class CameraSettings:
    """
    单个摄像头配置。

    width / height:
        摄像头实际采集分辨率。

    area:
        浏览器显示区域的中心裁剪尺寸。
        0 表示不裁剪。

    clarity:
        浏览器显示编码质量。
        不影响 ONNX 和 MediaPipe。
    """

    width: int = DEFAULT_CAMERA_WIDTH
    height: int = DEFAULT_CAMERA_HEIGHT
    area: int = DEFAULT_DISPLAY_AREA
    clarity: int = DEFAULT_DISPLAY_CLARITY

    def to_dict(self) -> dict[str, int]:
        return {
            "width": self.width,
            "height": self.height,
            "area": self.area,
            "clarity": self.clarity,
        }


def _safe_int(
    value: Any,
    default: int,
) -> int:
    try:
        if isinstance(value, bool):
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


def normalize_camera_settings(
    data: dict | None,
) -> CameraSettings:
    """
    将 JSON 配置规范化为 CameraSettings。

    保存接口已经做过严格验证，这里主要负责运行时兜底。
    """

    data = data if isinstance(data, dict) else {}

    width = max(
        1,
        _safe_int(
            data.get("width"),
            DEFAULT_CAMERA_WIDTH,
        ),
    )

    height = max(
        1,
        _safe_int(
            data.get("height"),
            DEFAULT_CAMERA_HEIGHT,
        ),
    )

    area = max(
        0,
        _safe_int(
            data.get("area"),
            DEFAULT_DISPLAY_AREA,
        ),
    )

    clarity = min(
        100,
        max(
            1,
            _safe_int(
                data.get("clarity"),
                DEFAULT_DISPLAY_CLARITY,
            ),
        ),
    )

    return CameraSettings(
        width=width,
        height=height,
        area=area,
        clarity=clarity,
    )


def load_camera_settings(
    camera_name: str,
) -> CameraSettings:
    """
    根据相机名称读取独立配置。

    配置结构：

    cameraResolution: {
        "TEF1": {
            "width": 1280,
            "height": 720,
            "area": 640,
            "clarity": 50
        }
    }
    """

    config = get_main_config()

    camera_configs = config.get(
        "cameraResolution",
        {},
    )

    if not isinstance(camera_configs, dict):
        camera_configs = {}

    camera_config = camera_configs.get(
        camera_name,
        {},
    )

    return normalize_camera_settings(
        camera_config
    )


def configure_capture(
    capture: cv2.VideoCapture,
    settings: CameraSettings,
    target_fps: float = 30.0,
) -> dict[str, int | float | bool]:
    """
    将配置应用到真实 VideoCapture。

    返回驱动最终实际采用的分辨率。
    """

    if (
        capture is None
        or not capture.isOpened()
    ):
        raise RuntimeError(
            "Camera capture is not opened"
        )

    # 高分辨率 USB 摄像头在 DirectShow 下通常需要 MJPG。
    # 即使相机不支持，set() 失败也不会抛异常，
    # 后面仍会读取驱动最终采用的实际参数。
    capture.set(
        cv2.CAP_PROP_FOURCC,
        cv2.VideoWriter_fourcc(
            *"MJPG"
        ),
    )

    capture.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        settings.width,
    )

    capture.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        settings.height,
    )

    capture.set(
        cv2.CAP_PROP_FPS,
        float(target_fps),
    )

    # 尽量避免显示旧帧。
    capture.set(
        cv2.CAP_PROP_BUFFERSIZE,
        1,
    )

    actual_width = int(
        round(
            capture.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
            or 0
        )
    )

    actual_height = int(
        round(
            capture.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
            or 0
        )
    )

    actual_fps = float(
        capture.get(
            cv2.CAP_PROP_FPS
        )
        or 0.0
    )

    return {
        "requested_width":
            settings.width,

        "requested_height":
            settings.height,

        "actual_width":
            actual_width,

        "actual_height":
            actual_height,

        "actual_fps":
            round(actual_fps, 2),

        "resolution_matched": (
            actual_width
            == settings.width

            and actual_height
            == settings.height
        ),
    }


def crop_display_area(
    frame: np.ndarray,
    area: int,
) -> np.ndarray:
    """
    按现有 aFAIVS 语义对显示画面进行中心裁剪。

    area = 0:
        不裁剪。

    area > 0:
        宽和高都不超过 area，从中心裁剪。

    示例：

    原始帧 1280x720，area=640
        -> 输出 640x640

    原始帧 1024x768，area=640
        -> 输出 640x640

    原始帧 640x480，area=640
        -> 输出 640x480
    """

    if (
        frame is None
        or frame.size == 0
    ):
        return frame

    height, width = frame.shape[:2]

    area = max(
        0,
        int(area or 0),
    )

    if (
        area == 0
        or max(width, height) <= area
    ):
        return frame

    crop_width = min(
        width,
        area,
    )

    crop_height = min(
        height,
        area,
    )

    start_x = max(
        0,
        (width - crop_width) // 2,
    )

    start_y = max(
        0,
        (height - crop_height) // 2,
    )

    return frame[
        start_y:
        start_y + crop_height,

        start_x:
        start_x + crop_width,
    ]


def encode_jpeg(
    frame: np.ndarray,
    clarity: int,
) -> bytes:
    """
    根据 clarity 将显示帧编码为 JPEG。
    """

    quality = min(
        100,
        max(
            1,
            int(
                clarity
                or DEFAULT_DISPLAY_CLARITY
            ),
        ),
    )

    success, buffer = cv2.imencode(
        ".jpg",
        frame,
        [
            int(
                cv2.IMWRITE_JPEG_QUALITY
            ),
            quality,
        ],
    )

    if not success:
        raise RuntimeError(
            "Failed to encode camera frame"
        )

    return buffer.tobytes()


def apply_display_quality(
    frame: np.ndarray,
    clarity: int,
) -> np.ndarray:
    """
    WebRTC 接收的是 ndarray，不能直接设置 JPEG quality。

    因此先用 clarity 编码，再解码回 ndarray，
    只降低浏览器显示帧质量。

    ONNX 和 MediaPipe 仍然使用原始帧。
    """

    quality = min(
        100,
        max(
            1,
            int(
                clarity
                or DEFAULT_DISPLAY_CLARITY
            ),
        ),
    )

    if quality >= 100:
        return frame

    encoded = encode_jpeg(
        frame,
        quality,
    )

    decoded = cv2.imdecode(
        np.frombuffer(
            encoded,
            dtype=np.uint8,
        ),
        cv2.IMREAD_COLOR,
    )

    return (
        decoded
        if decoded is not None
        else frame
    )