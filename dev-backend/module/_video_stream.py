from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Any

from module._camera_settings import (
    crop_display_area,
    encode_jpeg,
)


logger = logging.getLogger(__name__)

PREVIEW_STREAM_FPS = 15.0

camera_streams: dict[
    int,
    dict[str, Any],
] = {}


def _read_preview_frame(state: dict[str, Any]):
    capture = state.get("capture")
    capture_lock = state.get("capture_lock")
    if capture is None or capture_lock is None:
        return False, None
    with capture_lock:
        if not capture.isOpened():
            return False, None
        return capture.read()


def _encode_preview_frame(frame, settings) -> bytes:
    display_frame = crop_display_area(
        frame,
        settings.area,
    )
    return encode_jpeg(
        display_frame,
        settings.clarity,
    )


async def stream_camera(
    camera_id: int,
) -> None:

    state = camera_streams.get(
        camera_id
    )

    if (
        not state
        or not state.get("active")
    ):
        return

    header = struct.pack(
        ">I",
        0xFFFF0000,
    )
    frame_interval = 1.0 / PREVIEW_STREAM_FPS
    next_tick = time.monotonic()

    try:
        while True:

            state = camera_streams.get(
                camera_id
            )

            if (
                not state
                or not state.get("active")
            ):
                break

            clients = list(
                state.get(
                    "clients",
                    set(),
                )
            )

            if not clients:
                break

            settings = state.get(
                "settings"
            )

            if settings is None:
                break

            ret, frame = await asyncio.to_thread(
                _read_preview_frame,
                state,
            )

            if (
                not ret
                or frame is None
            ):
                break

            try:
                frame_bytes = await asyncio.to_thread(
                    _encode_preview_frame,
                    frame,
                    settings,
                )

            except Exception:
                logger.exception(
                    (
                        "Failed to encode "
                        "preview frame for "
                        "camera %s"
                    ),
                    camera_id,
                )
                continue

            disconnected = []

            for client in clients:
                try:
                    await client.send_bytes(
                        header
                        + frame_bytes
                    )

                except Exception:
                    disconnected.append(
                        client
                    )

            current_state = (
                camera_streams.get(
                    camera_id
                )
            )

            if current_state:
                current_clients = (
                    current_state.get(
                        "clients",
                        set(),
                    )
                )

                for client in disconnected:
                    current_clients.discard(
                        client
                    )

            next_tick += frame_interval
            sleep_time = max(
                0.0,
                next_tick - time.monotonic(),
            )
            if sleep_time:
                await asyncio.sleep(sleep_time)
            elif next_tick < time.monotonic() - 1:
                next_tick = time.monotonic()

    except Exception:
        logger.exception(
            (
                "Streaming disconnected "
                "for camera %s"
            ),
            camera_id,
        )

    finally:
        state = camera_streams.get(
            camera_id
        )

        if state:
            state["active"] = False

            capture = state.get(
                "capture"
            )

            if capture is not None:
                capture_lock = state.get(
                    "capture_lock"
                )
                if capture_lock is not None:
                    with capture_lock:
                        capture.release()
                else:
                    capture.release()

            camera_streams.pop(
                camera_id,
                None,
            )

        logger.warning(
            (
                "Stopping camera stream "
                "for camera %s"
            ),
            camera_id,
        )
