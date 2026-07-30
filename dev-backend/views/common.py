from __future__ import annotations

import asyncio
import logging

import cv2

from fastapi import (
    APIRouter,
    WebSocket,
)

from module._base import (
    get_display_name,
    graph,
)

from module._camera_settings import (
    configure_capture,
    load_camera_settings,
)

from module._video_stream import (
    camera_streams,
    stream_camera,
)


logger = logging.getLogger(__name__)

api_common = APIRouter()


@api_common.get("/get_loginUser")
def get_login_user():

    username = get_display_name()

    return {
        "username": username
    }


@api_common.get("/get_device")
async def get_device():

    devices = (
        graph.get_input_devices()
    )

    return {
        "camera": devices
    }


@api_common.websocket(
    "/ws/video_streaming"
)
async def websocket_endpoint(
    websocket: WebSocket,
    camera_id: int,
):

    await websocket.accept()

    state = camera_streams.setdefault(
        camera_id,
        {
            "capture": None,
            "clients": set(),
            "active": False,
            "camera_name": None,
            "settings": None,
            "capture_report": None,
        },
    )

    state["clients"].add(
        websocket
    )

    try:

        if not state["active"]:

            devices = (
                graph.get_input_devices()
            )

            if (
                camera_id < 0
                or camera_id
                >= len(devices)
            ):
                raise RuntimeError(
                    (
                        "Camera index "
                        f"{camera_id} "
                        "is not available"
                    )
                )

            camera_name = (
                devices[camera_id]
            )

            settings = (
                load_camera_settings(
                    camera_name
                )
            )

            capture = cv2.VideoCapture(
                camera_id,
                cv2.CAP_DSHOW,
            )

            if not capture.isOpened():

                capture.release()

                raise RuntimeError(
                    (
                        f"Camera "
                        f"{camera_name} "
                        "is not available"
                    )
                )

            report = configure_capture(
                capture,
                settings,
                target_fps=30.0,
            )

            state.update(
                {
                    "capture":
                        capture,

                    "active":
                        True,

                    "camera_name":
                        camera_name,

                    "settings":
                        settings,

                    "capture_report":
                        report,
                }
            )

            logger.info(
                (
                    "Preview camera %s "
                    "settings=%s report=%s"
                ),
                camera_name,
                settings.to_dict(),
                report,
            )

            asyncio.create_task(
                stream_camera(
                    camera_id
                )
            )

        while True:
            await asyncio.sleep(1)

    except Exception:

        logger.exception(
            (
                "Error with camera "
                "%s"
            ),
            camera_id,
        )

    finally:

        state = camera_streams.get(
            camera_id
        )

        if state:

            clients = state.get(
                "clients",
                set(),
            )

            clients.discard(
                websocket
            )

            logger.info(
                (
                    "Client disconnected "
                    "from camera %s. "
                    "Remaining clients: %s"
                ),
                camera_id,
                len(clients),
            )

            if not clients:

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