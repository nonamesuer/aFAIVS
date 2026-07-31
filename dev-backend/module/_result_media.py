from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np

from module._base import DEFAULT_RESULT_MEDIA_CONFIG, LIB_PATH

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

    boolean_fields = (
        "enabled",
        "saveOperationError",
        "saveNgRawImage",
        "saveNgAnnotatedImage",
        "saveStepSuccess",
        "saveRunCompleted",
        "saveNgVideo",
    )
    integer_fields = {
        "jpegQuality": (60, 100),
        "minFreeDiskPercent": (1, 50),
        "queueSize": (4, 256),
        "ngVideoBeforeSeconds": (1, 30),
        "ngVideoAfterSeconds": (1, 30),
        "ngVideoFps": (1, 25),
        "ngVideoMaxWidth": (320, 3840),
    }
    if strict:
        for field_name in boolean_fields:
            value_to_check = source.get(field_name, defaults[field_name])
            if not isinstance(value_to_check, bool):
                raise ValueError(f"resultMedia.{field_name} must be a boolean")
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
        "saveNgVideo": _as_bool(
            source.get("saveNgVideo"),
            defaults["saveNgVideo"],
        ),
        "ngVideoBeforeSeconds": _as_int(
            source.get("ngVideoBeforeSeconds"),
            defaults["ngVideoBeforeSeconds"],
            1,
            30,
        ),
        "ngVideoAfterSeconds": _as_int(
            source.get("ngVideoAfterSeconds"),
            defaults["ngVideoAfterSeconds"],
            1,
            30,
        ),
        "ngVideoFps": _as_int(
            source.get("ngVideoFps"),
            defaults["ngVideoFps"],
            1,
            25,
        ),
        "ngVideoMaxWidth": _as_int(
            source.get("ngVideoMaxWidth"),
            defaults["ngVideoMaxWidth"],
            320,
            3840,
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
        and not normalized["saveNgVideo"]
    ):
        raise ValueError(
            "At least one NG raw image, annotated image or video must be enabled"
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


@dataclass(frozen=True)
class BufferedVideoFrame:
    captured_monotonic: float
    jpeg_bytes: bytes
    width: int
    height: int


@dataclass
class PendingVideoClip:
    event_ref: dict
    trigger_monotonic: float
    ends_monotonic: float
    frames: list[BufferedVideoFrame]


@dataclass(order=True)
class MediaWriteTask:
    priority: int
    sequence: int
    event_ref: dict = field(compare=False)
    purpose: str = field(compare=False)
    variant: str = field(compare=False)
    media_type: str = field(compare=False, default="image")
    frame: np.ndarray | None = field(compare=False, default=None)
    video_frames: list[BufferedVideoFrame] | None = field(
        compare=False,
        default=None,
    )
    jpeg_quality: int = field(compare=False, default=90)
    fps: int = field(compare=False, default=10)


class ResultMediaRecorder:
    """
    Save images and NG clips outside the detector thread.

    Video frames are sampled and JPEG-compressed by a small capture worker.
    Only compressed frames are retained in the pre-event ring buffer. MP4
    encoding and all disk/database writes run in the media writer worker.
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
        self.video_enabled = bool(
            self.enabled
            and self.config["saveOperationError"]
            and self.config["saveNgVideo"]
        )
        self.max_queue_size = int(self.config["queueSize"])

        self._condition = threading.Condition()
        self._tasks: list[MediaWriteTask] = []
        self._sequence = 0
        self._running = self.enabled
        self._writer_busy = False
        self._sync_when_idle = False
        self._thread: threading.Thread | None = None

        self._video_condition = threading.Condition()
        self._video_running = self.video_enabled
        self._video_input: deque[tuple[float, np.ndarray]] = deque(maxlen=2)
        self._video_ring: deque[BufferedVideoFrame] = deque(
            maxlen=(
                int(self.config["ngVideoBeforeSeconds"])
                * int(self.config["ngVideoFps"])
                + 2
            )
        )
        self._pending_clips: list[PendingVideoClip] = []
        self._video_event_ids: set[str] = set()
        self._last_video_sample = 0.0
        self._video_thread: threading.Thread | None = None

        if self.enabled:
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="result-media-writer",
                daemon=True,
            )
            self._thread.start()

        if self.video_enabled:
            self._video_thread = threading.Thread(
                target=self._video_loop,
                name="result-video-buffer",
                daemon=True,
            )
            self._video_thread.start()

    def buffer_video_frame(self, frame: np.ndarray | None) -> None:
        if not self.video_enabled or frame is None:
            return

        captured = time.monotonic()
        period = 1.0 / int(self.config["ngVideoFps"])
        with self._video_condition:
            if not self._video_running:
                return
            if captured - self._last_video_sample < period:
                return
            self._last_video_sample = captured
            if len(self._video_input) == self._video_input.maxlen:
                self._video_input.popleft()
            # CameraManager.get_latest_frame() already returns a private frame
            # copy, so ownership can be transferred without another full copy.
            self._video_input.append((captured, frame))
            self._video_condition.notify()

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
        specific_ng: dict | None = None
        if self.config["saveOperationError"] and ng_events:
            specific_ng = next(
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
                    (specific_ng, "operation_error", 0, tuple(variants))
                )
            if self.video_enabled:
                self._start_video_clip(specific_ng)

        if self.config["saveStepSuccess"]:
            selected.extend(
                (event, "step_success", 2, ("annotated",))
                for event in event_refs
                if event.get("event_type") == "STEP_COMPLETED"
            )

        run_finished = any(
            event.get("event_type") == "RUN_FINISHED"
            for event in event_refs
        )
        if self.config["saveRunCompleted"]:
            selected.extend(
                (event, "run_completed", 1, ("annotated",))
                for event in event_refs
                if event.get("event_type") == "RUN_FINISHED"
                and event.get("details", {}).get("execution_status")
                == "completed"
            )

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

        if run_finished:
            with self._condition:
                self._sync_when_idle = True
            self._request_sync_if_idle()

    def _start_video_clip(self, event_ref: dict) -> None:
        event_key = (
            f"{event_ref.get('database_path')}:"
            f"{event_ref.get('event_id')}:"
            f"{event_ref.get('run_id')}:"
            f"{event_ref.get('timestamp_ms')}:"
            f"{event_ref.get('event_type')}"
        )
        triggered = time.monotonic()
        with self._video_condition:
            if event_key in self._video_event_ids:
                return
            if len(self._video_event_ids) >= 4096:
                self._video_event_ids.pop()
            self._video_event_ids.add(event_key)
            earliest = triggered - int(self.config["ngVideoBeforeSeconds"])
            frames = [
                frame
                for frame in self._video_ring
                if frame.captured_monotonic >= earliest
            ]
            self._pending_clips.append(
                PendingVideoClip(
                    event_ref=dict(event_ref),
                    trigger_monotonic=triggered,
                    ends_monotonic=(
                        triggered + int(self.config["ngVideoAfterSeconds"])
                    ),
                    frames=frames,
                )
            )

    def _video_loop(self) -> None:
        while True:
            with self._video_condition:
                while self._video_running and not self._video_input:
                    self._video_condition.wait(timeout=0.25)
                    self._finalize_due_clips_locked(time.monotonic())
                if not self._video_running and not self._video_input:
                    self._finalize_all_clips_locked()
                    return
                captured, frame = self._video_input.popleft()

            encoded = self._compress_video_frame(captured, frame)
            if encoded is None:
                continue
            with self._video_condition:
                self._video_ring.append(encoded)
                for clip in self._pending_clips:
                    if captured <= clip.ends_monotonic:
                        clip.frames.append(encoded)
                self._finalize_due_clips_locked(captured)

    def _compress_video_frame(
        self,
        captured: float,
        frame: np.ndarray,
    ) -> BufferedVideoFrame | None:
        try:
            height, width = frame.shape[:2]
            max_width = int(self.config["ngVideoMaxWidth"])
            if width > max_width:
                ratio = max_width / width
                width = max_width
                height = max(2, int(round(height * ratio / 2) * 2))
                frame = cv2.resize(
                    frame,
                    (width, height),
                    interpolation=cv2.INTER_AREA,
                )
            if width % 2:
                width -= 1
                frame = frame[:, :width]
            if height % 2:
                height -= 1
                frame = frame[:height, :]
            success, encoded = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 78],
            )
            if not success:
                return None
            return BufferedVideoFrame(
                captured_monotonic=captured,
                jpeg_bytes=encoded.tobytes(),
                width=width,
                height=height,
            )
        except Exception:
            logger.exception("Failed to buffer a result video frame")
            return None

    def _finalize_due_clips_locked(self, current: float) -> None:
        due = [
            clip
            for clip in self._pending_clips
            if current >= clip.ends_monotonic
        ]
        if not due:
            return
        self._pending_clips = [
            clip
            for clip in self._pending_clips
            if current < clip.ends_monotonic
        ]
        for clip in due:
            self._enqueue_video_clip(clip)

    def _finalize_all_clips_locked(self) -> None:
        clips = self._pending_clips
        self._pending_clips = []
        for clip in clips:
            self._enqueue_video_clip(clip)

    def _enqueue_video_clip(self, clip: PendingVideoClip) -> None:
        if not clip.frames:
            self._notify(
                {
                    "type": "result_media",
                    "status": "dropped",
                    "message": "No buffered frames were available for the NG clip",
                    "purpose": "operation_error",
                    "variant": "event_clip",
                }
            )
            return
        task = MediaWriteTask(
            priority=0,
            sequence=self._next_sequence(),
            event_ref=clip.event_ref,
            purpose="operation_error",
            variant="event_clip",
            media_type="video",
            video_frames=list(clip.frames),
            fps=int(self.config["ngVideoFps"]),
        )
        if not self._enqueue(task):
            self._notify(
                {
                    "type": "result_media",
                    "status": "dropped",
                    "message": "Media queue is full",
                    "purpose": task.purpose,
                    "variant": task.variant,
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
                        "message": "A lower-priority media task was replaced",
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
                self._writer_busy = True
            try:
                if task.media_type == "video":
                    self._write_video_task(task)
                else:
                    self._write_image_task(task)
            finally:
                with self._condition:
                    self._writer_busy = False
                self._request_sync_if_idle()

    def _check_free_disk(self) -> None:
        disk = shutil.disk_usage(self.result_store.result_path)
        free_percent = (disk.free / disk.total * 100) if disk.total else 0
        if free_percent < self.config["minFreeDiskPercent"]:
            raise OSError(
                "Media saving stopped because free disk space is below "
                f"{self.config['minFreeDiskPercent']}%"
            )

    def _write_image_task(self, task: MediaWriteTask) -> None:
        if task.frame is None:
            return
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
            self._check_free_disk()

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
            self._handle_write_failure(media_id, temp_path, exc, "image")

    def _write_video_task(self, task: MediaWriteTask) -> None:
        frames = task.video_frames or []
        if not frames:
            return
        media_id = ""
        temp_path = ""
        try:
            width = frames[0].width
            height = frames[0].height
            duration_ms = max(
                1,
                int(round(len(frames) / max(1, task.fps) * 1000)),
            )
            reservation = self.result_store.reserve_media(
                event_ref=task.event_ref,
                purpose=task.purpose,
                variant=task.variant,
                width=width,
                height=height,
                mime_type="video/mp4",
                extension="mp4",
                media_type="video",
                duration_ms=duration_ms,
                fps=float(task.fps),
            )
            if reservation is None:
                raise RuntimeError("Failed to reserve a video database record")
            media_id = reservation["media_id"]
            absolute_path = reservation["absolute_path"]
            temp_path = f"{absolute_path}.part.mp4"
            self._check_free_disk()
            os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

            if not self._encode_with_ffmpeg(frames, task.fps, temp_path):
                self._encode_with_opencv(
                    frames,
                    task.fps,
                    width,
                    height,
                    temp_path,
                )
            os.replace(temp_path, absolute_path)
            size_bytes, sha256 = self._hash_file(absolute_path)
            self.result_store.complete_media(
                media_id=media_id,
                size_bytes=size_bytes,
                sha256=sha256,
            )
        except Exception as exc:
            self._handle_write_failure(media_id, temp_path, exc, "video")

    def _ffmpeg_path(self) -> str | None:
        candidates = (
            os.path.join(LIB_PATH, "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(LIB_PATH, "ffmpeg.exe"),
            shutil.which("ffmpeg"),
        )
        return next(
            (
                candidate
                for candidate in candidates
                if candidate and os.path.isfile(candidate)
            ),
            None,
        )

    def _encode_with_ffmpeg(
        self,
        frames: list[BufferedVideoFrame],
        fps: int,
        output_path: str,
    ) -> bool:
        ffmpeg = self._ffmpeg_path()
        if not ffmpeg:
            return False
        command = [
            ffmpeg,
            "-loglevel",
            "error",
            "-y",
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "-framerate",
            str(fps),
            "-i",
            "pipe:0",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            output_path,
        ]
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            assert process.stdin is not None
            try:
                for frame in frames:
                    process.stdin.write(frame.jpeg_bytes)
                process.stdin.close()
                stderr = process.stderr.read() if process.stderr else b""
                return_code = process.wait(timeout=120)
            except Exception:
                process.kill()
                process.wait()
                raise
            if return_code != 0:
                logger.warning(
                    "FFmpeg video encoding failed; using OpenCV fallback: %s",
                    stderr.decode("utf-8", errors="replace")[-1000:],
                )
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except OSError:
                    pass
                return False
            return os.path.isfile(output_path) and os.path.getsize(output_path) > 0
        except Exception:
            logger.exception("FFmpeg could not encode the NG clip")
            return False

    @staticmethod
    def _encode_with_opencv(
        frames: list[BufferedVideoFrame],
        fps: int,
        width: int,
        height: int,
        output_path: str,
    ) -> None:
        writer = cv2.VideoWriter(
            output_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            float(fps),
            (width, height),
        )
        if not writer.isOpened():
            raise OSError("Neither FFmpeg nor OpenCV could create the MP4 file")
        try:
            for buffered in frames:
                image = cv2.imdecode(
                    np.frombuffer(buffered.jpeg_bytes, dtype=np.uint8),
                    cv2.IMREAD_COLOR,
                )
                if image is None:
                    continue
                if image.shape[1] != width or image.shape[0] != height:
                    image = cv2.resize(image, (width, height))
                writer.write(image)
        finally:
            writer.release()
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            raise OSError("OpenCV created an empty MP4 file")

    @staticmethod
    def _hash_file(path: str) -> tuple[int, str]:
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as media_file:
            for block in iter(lambda: media_file.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
        return size, digest.hexdigest()

    def _handle_write_failure(
        self,
        media_id: str,
        temp_path: str,
        exc: Exception,
        media_type: str,
    ) -> None:
        try:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            logger.warning("Failed to remove media temp file %s", temp_path)
        if media_id:
            self.result_store.fail_media(media_id, str(exc))
        logger.exception("Failed to save SOP evidence %s", media_type)
        self._notify(
            {
                "type": "result_media",
                "status": "failed",
                "mediaId": media_id,
                "mediaType": media_type,
                "message": str(exc),
            }
        )

    def _request_sync_if_idle(self) -> None:
        with self._video_condition:
            video_pending = bool(self._pending_clips)
        with self._condition:
            if (
                not self._sync_when_idle
                or self._tasks
                or self._writer_busy
                or video_pending
            ):
                return
            self._sync_when_idle = False
        self.result_store.request_storage_sync()

    def request_storage_sync_when_idle(self) -> None:
        if not self.enabled:
            self.result_store.request_storage_sync()
            return
        with self._condition:
            self._sync_when_idle = True
        self._request_sync_if_idle()

    def _notify(self, event: dict) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(event)
        except Exception:
            logger.exception("Result media status callback failed")

    def shutdown(self, timeout: float = 15.0) -> None:
        if not self.enabled:
            self.result_store.request_storage_sync()
            return

        if self.video_enabled:
            with self._video_condition:
                self._video_running = False
                self._video_condition.notify_all()
            if self._video_thread and self._video_thread.is_alive():
                self._video_thread.join(timeout=min(timeout, 5.0))

        with self._condition:
            self._sync_when_idle = True
            self._running = False
            self._condition.notify_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self.result_store.request_storage_sync()
