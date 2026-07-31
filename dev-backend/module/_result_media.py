from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np

from module._base import DEFAULT_RESULT_MEDIA_CONFIG

logger = logging.getLogger(__name__)

NG_EVENT_TYPES = {
    "WRONG_MATERIAL",
    "WRONG_PICK_SOURCE",
    "STEP_BLOCKED",
}


def _as_bool(value, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _as_int(value, fallback: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, parsed))


def normalize_result_media_config(
    value: dict | None,
    *,
    strict: bool = False,
) -> dict:
    source = value if isinstance(value, dict) else {}
    defaults = DEFAULT_RESULT_MEDIA_CONFIG

    image_format = str(
        source.get("imageFormat", defaults["imageFormat"])
    ).strip().lower()
    if image_format not in {"jpg"}:
        if strict:
            raise ValueError("resultMedia.imageFormat currently supports only jpg")
        image_format = defaults["imageFormat"]

    if strict:
        boolean_fields = (
            "enabled",
            "saveOperationError",
            "saveNgRawImage",
            "saveNgAnnotatedImage",
            "saveStepSuccess",
            "saveRunCompleted",
        )
        for field_name in boolean_fields:
            value_to_check = source.get(field_name, defaults[field_name])
            if not isinstance(value_to_check, bool):
                raise ValueError(f"resultMedia.{field_name} must be a boolean")

        integer_fields = {
            "jpegQuality": (60, 100),
            "minFreeDiskPercent": (1, 50),
            "queueSize": (4, 256),
        }
        for field_name, (minimum, maximum) in integer_fields.items():
            value_to_check = source.get(field_name, defaults[field_name])
            if isinstance(value_to_check, bool):
                raise ValueError(f"resultMedia.{field_name} must be an integer")
            try:
                parsed = int(value_to_check)
            except (TypeError, ValueError):
                raise ValueError(
                    f"resultMedia.{field_name} must be an integer"
                ) from None
            if parsed != value_to_check or not minimum <= parsed <= maximum:
                raise ValueError(
                    f"resultMedia.{field_name} must be between "
                    f"{minimum} and {maximum}"
                )

    normalized = {
        "enabled": _as_bool(source.get("enabled"), defaults["enabled"]),
        "saveOperationError": _as_bool(
            source.get("saveOperationError"),
            defaults["saveOperationError"],
        ),
        "saveNgRawImage": _as_bool(
            source.get("saveNgRawImage"),
            defaults["saveNgRawImage"],
        ),
        "saveNgAnnotatedImage": _as_bool(
            source.get("saveNgAnnotatedImage"),
            defaults["saveNgAnnotatedImage"],
        ),
        "saveStepSuccess": _as_bool(
            source.get("saveStepSuccess"),
            defaults["saveStepSuccess"],
        ),
        "saveRunCompleted": _as_bool(
            source.get("saveRunCompleted"),
            defaults["saveRunCompleted"],
        ),
        "imageFormat": image_format,
        "jpegQuality": _as_int(
            source.get("jpegQuality"),
            defaults["jpegQuality"],
            60,
            100,
        ),
        "minFreeDiskPercent": _as_int(
            source.get("minFreeDiskPercent"),
            defaults["minFreeDiskPercent"],
            1,
            50,
        ),
        "queueSize": _as_int(
            source.get("queueSize"),
            defaults["queueSize"],
            4,
            256,
        ),
    }
    if (
        strict
        and normalized["enabled"]
        and normalized["saveOperationError"]
        and not normalized["saveNgRawImage"]
        and not normalized["saveNgAnnotatedImage"]
    ):
        raise ValueError(
            "At least one NG raw or annotated image must be enabled"
        )
    return normalized


def validate_result_media_config(payload: dict) -> str:
    if "resultMedia" not in payload:
        return ""
    if not isinstance(payload["resultMedia"], dict):
        return "resultMedia must be an object"
    try:
        normalize_result_media_config(payload["resultMedia"], strict=True)
    except ValueError as exc:
        return str(exc)
    return ""


@dataclass(order=True)
class MediaWriteTask:
    priority: int
    sequence: int
    event_ref: dict = field(compare=False)
    purpose: str = field(compare=False)
    variant: str = field(compare=False)
    frame: np.ndarray = field(compare=False)
    jpeg_quality: int = field(compare=False)


class ResultMediaRecorder:
    """
    Asynchronously encodes and writes evidence images.

    The detector thread only copies frames and enqueues work. Database writes,
    JPEG encoding and disk I/O stay in this worker.
    """

    def __init__(
        self,
        result_store,
        config: dict | None,
        status_callback: Callable[[dict], None] | None = None,
    ):
        self.result_store = result_store
        self.config = normalize_result_media_config(config)
        self.status_callback = status_callback
        self.enabled = bool(self.config["enabled"])
        self.max_queue_size = int(self.config["queueSize"])

        self._condition = threading.Condition()
        self._tasks: list[MediaWriteTask] = []
        self._sequence = 0
        self._running = self.enabled
        self._thread: threading.Thread | None = None

        if self.enabled:
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="result-media-writer",
                daemon=True,
            )
            self._thread.start()

    def capture_events(
        self,
        event_refs: list[dict] | None,
        raw_frame: np.ndarray,
        annotated_frame_factory: Callable[[], np.ndarray],
    ) -> None:
        if not self.enabled or not event_refs or raw_frame is None:
            return

        selected: list[tuple[dict, str, int, tuple[str, ...]]] = []

        ng_events = [
            event
            for event in event_refs
            if event.get("event_type") in NG_EVENT_TYPES
            or event.get("severity") == "error"
        ]
        if self.config["saveOperationError"] and ng_events:
            specific = next(
                (
                    event
                    for event in ng_events
                    if event.get("event_type") != "STEP_BLOCKED"
                ),
                ng_events[0],
            )
            variants: list[str] = []
            if self.config["saveNgRawImage"]:
                variants.append("raw")
            if self.config["saveNgAnnotatedImage"]:
                variants.append("annotated")
            if variants:
                selected.append(
                    (specific, "operation_error", 0, tuple(variants))
                )

        if self.config["saveStepSuccess"]:
            selected.extend(
                (event, "step_success", 2, ("annotated",))
                for event in event_refs
                if event.get("event_type") == "STEP_COMPLETED"
            )

        if self.config["saveRunCompleted"]:
            selected.extend(
                (event, "run_completed", 1, ("annotated",))
                for event in event_refs
                if event.get("event_type") == "RUN_FINISHED"
                and event.get("details", {}).get("execution_status")
                == "completed"
            )

        if not selected:
            return

        annotated_frame: np.ndarray | None = None
        for event, purpose, priority, variants in selected:
            for variant in variants:
                if variant == "raw":
                    frame = raw_frame.copy()
                else:
                    if annotated_frame is None:
                        annotated_frame = annotated_frame_factory()
                    frame = annotated_frame.copy()

                task = MediaWriteTask(
                    priority=priority,
                    sequence=self._next_sequence(),
                    event_ref=dict(event),
                    purpose=purpose,
                    variant=variant,
                    frame=frame,
                    jpeg_quality=int(self.config["jpegQuality"]),
                )
                if not self._enqueue(task):
                    self._notify(
                        {
                            "type": "result_media",
                            "status": "dropped",
                            "message": "Media queue is full",
                            "purpose": purpose,
                            "variant": variant,
                        }
                    )

    def _next_sequence(self) -> int:
        with self._condition:
            self._sequence += 1
            return self._sequence

    def _enqueue(self, task: MediaWriteTask) -> bool:
        with self._condition:
            if not self._running:
                return False

            if len(self._tasks) >= self.max_queue_size:
                worst_index = max(
                    range(len(self._tasks)),
                    key=lambda index: (
                        self._tasks[index].priority,
                        self._tasks[index].sequence,
                    ),
                )
                worst_task = self._tasks[worst_index]
                if task.priority >= worst_task.priority:
                    return False
                self._tasks.pop(worst_index)
                self._notify(
                    {
                        "type": "result_media",
                        "status": "dropped",
                        "message": (
                            "Media queue replaced this lower-priority image"
                        ),
                        "purpose": worst_task.purpose,
                        "variant": worst_task.variant,
                    }
                )

            self._tasks.append(task)
            self._tasks.sort()
            self._condition.notify()
            return True

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while self._running and not self._tasks:
                    self._condition.wait()
                if not self._running and not self._tasks:
                    return
                task = self._tasks.pop(0)

            self._write_task(task)

    def _write_task(self, task: MediaWriteTask) -> None:
        media_id = ""
        absolute_path = ""
        temp_path = ""
        try:
            reservation = self.result_store.reserve_media(
                event_ref=task.event_ref,
                purpose=task.purpose,
                variant=task.variant,
                width=int(task.frame.shape[1]),
                height=int(task.frame.shape[0]),
                mime_type="image/jpeg",
                extension="jpg",
            )
            if reservation is None:
                raise RuntimeError("Failed to reserve a media database record")

            media_id = reservation["media_id"]
            absolute_path = reservation["absolute_path"]
            temp_path = f"{absolute_path}.part"

            disk = shutil.disk_usage(self.result_store.result_path)
            free_percent = (disk.free / disk.total * 100) if disk.total else 0
            if free_percent < self.config["minFreeDiskPercent"]:
                raise OSError(
                    "Media saving stopped because free disk space is below "
                    f"{self.config['minFreeDiskPercent']}%"
                )

            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
            success, encoded = cv2.imencode(
                ".jpg",
                task.frame,
                [cv2.IMWRITE_JPEG_QUALITY, task.jpeg_quality],
            )
            if not success:
                raise OSError("OpenCV failed to encode the evidence image")

            image_bytes = encoded.tobytes()
            with open(temp_path, "wb") as media_file:
                media_file.write(image_bytes)
                media_file.flush()
                os.fsync(media_file.fileno())
            os.replace(temp_path, absolute_path)

            self.result_store.complete_media(
                media_id=media_id,
                size_bytes=len(image_bytes),
                sha256=hashlib.sha256(image_bytes).hexdigest(),
            )
        except Exception as exc:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                logger.warning("Failed to remove media temp file %s", temp_path)
            if media_id:
                self.result_store.fail_media(media_id, str(exc))
            logger.exception("Failed to save SOP evidence image")
            self._notify(
                {
                    "type": "result_media",
                    "status": "failed",
                    "mediaId": media_id,
                    "message": str(exc),
                }
            )

    def _notify(self, event: dict) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(event)
        except Exception:
            logger.exception("Result media status callback failed")

    def shutdown(self, timeout: float = 5.0) -> None:
        if not self.enabled:
            return
        with self._condition:
            self._running = False
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
