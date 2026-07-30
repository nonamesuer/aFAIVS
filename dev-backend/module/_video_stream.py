from __future__ import annotations

import asyncio
import logging
import struct
from typing import Any

from module._camera_settings import (
    crop_display_area,
    encode_jpeg,
)


logger = logging.getLogger(__name__)


camera_streams: dict[
    int,
    dict[str, Any],
] = {}


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

            capture = state.get(
                "capture"
            )

            settings = state.get(
                "settings"
            )

            if (
                capture is None
                or settings is None
            ):
                break

            ret, frame = capture.read()

            if (
                not ret
                or frame is None
            ):
                break

            frame = crop_display_area(
                frame,
                settings.area,
            )

            try:
                frame_bytes = encode_jpeg(
                    frame,
                    settings.clarity,
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

            await asyncio.sleep(0.03)

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