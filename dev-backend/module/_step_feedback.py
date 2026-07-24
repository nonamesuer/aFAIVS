from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

from pymodbus.client import ModbusTcpClient

from module._base import get_main_config,JsonFile


logger = logging.getLogger(__name__)

MAX_STEP_FEEDBACK_SIGNALS = 3
MAX_STEP_HTTP_ENDPOINTS = 5
MOMENTARY_COIL_DELAY_SECONDS = 0.3
WRITABLE_MODBUS_TYPES = {"coil", "holdingRegister"}
HTTP_FEEDBACK_DEBUG_FILE_LOCK = threading.Lock()


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _enabled_http_endpoint_urls(main_config: dict[str, Any]) -> set[str]:
    integration = main_config.get("detectionIntegration", {})
    if not isinstance(integration, dict):
        return set()
    result_feedback = integration.get("resultFeedback", {})
    if not isinstance(result_feedback, dict) or result_feedback.get("enabled") is not True:
        return set()

    urls: set[str] = set()
    for endpoint in result_feedback.get("endpoints", []):
        if not isinstance(endpoint, dict) or endpoint.get("enabled") is not True:
            continue
        name = str(endpoint.get("name", "")).strip()
        url = str(endpoint.get("url", "")).strip()
        if name and url:
            urls.add(url)
    return urls


def _validate_modbus_feedback_signal(signal: Any) -> str:
    if not isinstance(signal, dict):
        return "Each Modbus feedback signal must be an object"

    slave_address = signal.get("slaveAddress")
    address = signal.get("address")
    data_type = signal.get("dataType")
    trigger_value = signal.get("triggerValue")
    instantaneous = signal.get("instantaneous", False)

    if not _is_integer(slave_address) or not 1 <= slave_address <= 247:
        return "Modbus feedback slave address must be an integer between 1 and 247"
    if not _is_integer(address) or not 0 <= address <= 65535:
        return "Modbus feedback address must be an integer between 0 and 65535"
    if data_type not in WRITABLE_MODBUS_TYPES:
        return "Modbus feedback supports only coil and holdingRegister data types"
    if not isinstance(instantaneous, bool):
        return "Modbus feedback instantaneous must be boolean"
    if data_type == "coil":
        if not isinstance(trigger_value, bool):
            return "Modbus coil feedback value must be boolean"
    else:
        if instantaneous:
            return "Modbus feedback instantaneous is supported only for coil data type"
        if not _is_integer(trigger_value) or not 0 <= trigger_value <= 65535:
            return "Modbus holding register feedback value must be an integer between 0 and 65535"
    return ""


def validate_sop_step_feedback_config(
    body: dict[str, Any],
    main_config: dict[str, Any] | None = None,
) -> str:
    """Validate optional per-step result feedback configuration."""
    steps = body.get("steps")
    if steps is None:
        return ""
    if not isinstance(steps, list):
        return "SOP steps must be an array"

    active_http_urls = _enabled_http_endpoint_urls(main_config or get_main_config())
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        context = step.get("context", {})
        if not isinstance(context, dict):
            continue
        feedback = context.get("resultFeedback")
        if feedback is None:
            continue
        if not isinstance(feedback, dict):
            return f"Step {index + 1} resultFeedback must be an object"

        http_feedback = feedback.get("http", {})
        if not isinstance(http_feedback, dict):
            return f"Step {index + 1} HTTP feedback must be an object"
        endpoint_urls = http_feedback.get("endpointUrls", [])
        if not isinstance(endpoint_urls, list):
            return f"Step {index + 1} HTTP endpointUrls must be an array"
        if len(endpoint_urls) > MAX_STEP_HTTP_ENDPOINTS:
            return f"Step {index + 1} allows at most {MAX_STEP_HTTP_ENDPOINTS} HTTP feedback endpoints"
        if any(not isinstance(url, str) or not url.strip() for url in endpoint_urls):
            return f"Step {index + 1} HTTP feedback endpoint URL cannot be empty"
        normalized_urls = [url.strip() for url in endpoint_urls]
        if len(set(normalized_urls)) != len(normalized_urls):
            return f"Step {index + 1} HTTP feedback endpoints must be unique"
        if http_feedback.get("enabled") is True:
            if not normalized_urls:
                return f"Step {index + 1} must select at least one HTTP feedback endpoint"
            if any(url not in active_http_urls for url in normalized_urls):
                return f"Step {index + 1} selected an HTTP feedback endpoint that is not enabled in public configuration"

        modbus_feedback = feedback.get("modbus", {})
        if not isinstance(modbus_feedback, dict):
            return f"Step {index + 1} Modbus feedback must be an object"
        all_signals: list[dict[str, Any]] = []
        for group_name in ("errorSignals", "completionSignals"):
            signals = modbus_feedback.get(group_name, [])
            if not isinstance(signals, list):
                return f"Step {index + 1} {group_name} must be an array"
            if len(signals) > MAX_STEP_FEEDBACK_SIGNALS:
                return f"Step {index + 1} allows at most {MAX_STEP_FEEDBACK_SIGNALS} signals in {group_name}"
            for signal in signals:
                validation_error = _validate_modbus_feedback_signal(signal)
                if validation_error:
                    return f"Step {index + 1}: {validation_error}"
            all_signals.extend(signals)
        if modbus_feedback.get("enabled") is True and not all_signals:
            return f"Step {index + 1} must configure at least one Modbus feedback signal"
    return ""


class StepFeedbackDispatcher:
    """Dispatch step state transitions without blocking the detector thread."""

    def __init__(
        self,
        *,
        project_name: str | None,
        model_name: str | None,
        camera_name: str | None,
        status_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.project_name = project_name or ""
        self.model_name = model_name or ""
        self.camera_name = camera_name or ""
        self.status_callback = status_callback
        self._previous_states: dict[str, str] = {}
        self._previous_sop_state = ""
        self._status_lock = threading.Lock()
        self._status_sequence = 0
        # HTTP endpoints and Modbus are independent tasks. A slow endpoint must
        # not delay the detector thread or another feedback channel.
        # Public HTTP feedback allows up to five endpoints; the sixth worker
        # keeps Modbus independent even when all five HTTP endpoints are slow.
        self._executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="step-feedback")

    @staticmethod
    def _step_key(step: dict[str, Any], index: int) -> str:
        return str(step.get("id", index))

    def reset(self, snapshot: dict[str, Any] | None = None) -> None:
        current_snapshot = snapshot or {}
        self._previous_states = {}
        self._previous_sop_state = str(current_snapshot.get("state", ""))
        for index, step in enumerate(current_snapshot.get("steps", [])):
            if isinstance(step, dict):
                self._previous_states[self._step_key(step, index)] = str(step.get("state", "pending"))

    def process_snapshot(self, snapshot: dict[str, Any], run_id: str | None) -> None:
        steps = snapshot.get("steps", [])
        for index, step in enumerate(snapshot.get("steps", [])):
            if not isinstance(step, dict):
                continue
            key = self._step_key(step, index)
            current_state = str(step.get("state", "pending"))
            previous_state = self._previous_states.get(key)
            self._previous_states[key] = current_state

            event_type = None
            if current_state == "failed" and previous_state != "failed":
                event_type = "operation_error"
            elif current_state == "done" and previous_state != "done":
                event_type = "step_success"
            if event_type:
                self._schedule_event(
                    event_type,
                    deepcopy(step),
                    deepcopy(snapshot),
                    run_id,
                )

        current_sop_state = str(snapshot.get("state", ""))
        previous_sop_state = self._previous_sop_state
        self._previous_sop_state = current_sop_state
        if current_sop_state != "completed" or previous_sop_state == "completed":
            return

        # The final step has just emitted step_success above. Send one extra
        # HTTP-only event so receivers can distinguish "last step succeeded"
        # from "the whole SOP run completed".
        final_step = next(
            (
                step
                for step in reversed(steps)
                if isinstance(step, dict) and str(step.get("state", "")) == "done"
            ),
            None,
        )
        if final_step is not None:
            self._schedule_event(
                "sop_completed",
                deepcopy(final_step),
                deepcopy(snapshot),
                run_id,
                include_modbus=False,
            )

    def _schedule_event(
        self,
        event_type: str,
        step: dict[str, Any],
        snapshot: dict[str, Any],
        run_id: str | None,
        *,
        include_modbus: bool = True,
    ) -> None:
        context = step.get("context", {})
        feedback = context.get("resultFeedback", {}) if isinstance(context, dict) else {}
        if not isinstance(feedback, dict):
            return

        payload = {
            "eventType": event_type,
            "eventScope": "sop" if event_type == "sop_completed" else "step",
            "status": "ng" if event_type == "operation_error" else "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "projectName": self.project_name,
            "modelName": self.model_name,
            "cameraName": self.camera_name,
            "runId": run_id,
            "step": {
                "id": step.get("id"),
                "name": step.get("name"),
                "type": step.get("type"),
                "state": step.get("state"),
                "reason": step.get("last_reason") or snapshot.get("reason", ""),
                "target": step.get("target"),
                "matchedCount": step.get("matched_count"),
            },
            "sop": {
                "state": snapshot.get("state"),
                "progress": snapshot.get("progress", {}),
            },
        }

        http_feedback = feedback.get("http", {})
        if isinstance(http_feedback, dict) and http_feedback.get("enabled") is True:
            selected_urls = http_feedback.get("endpointUrls", [])
            if isinstance(selected_urls, list):
                for selected_url in selected_urls:
                    self._executor.submit(
                        self._send_http_feedback,
                        selected_url,
                        payload,
                        event_type,
                        step,
                        run_id,
                    )

        modbus_feedback = feedback.get("modbus", {})
        if (
            include_modbus
            and isinstance(modbus_feedback, dict)
            and modbus_feedback.get("enabled") is True
        ):
            group_name = "errorSignals" if event_type == "operation_error" else "completionSignals"
            signals = modbus_feedback.get(group_name, [])
            if isinstance(signals, list) and signals:
                self._executor.submit(
                    self._send_modbus_feedback,
                    signals,
                    event_type,
                    step,
                    run_id,
                )

    def _publish_status(
        self,
        *,
        status: str,
        channel: str,
        event_type: str,
        step: dict[str, Any],
        run_id: str | None,
        target: str,
        message: str,
    ) -> None:
        if self.status_callback is None:
            return
        with self._status_lock:
            self._status_sequence += 1
            sequence = self._status_sequence
        event = {
            "id": f"{time.time_ns()}-{sequence}",
            "status": status,
            "channel": channel,
            "eventType": event_type,
            "stepId": step.get("id"),
            "stepName": step.get("name") or "",
            "runId": run_id,
            "target": target,
            "message": message,
            "timestamp": time.time(),
        }
        try:
            self.status_callback(event)
        except Exception:
            logger.exception("Failed to publish step feedback status")

    def _send_http_feedback(
        self,
        selected_url: Any,
        payload: dict[str, Any],
        event_type: str,
        step: dict[str, Any],
        run_id: str | None,
    ) -> None:
        url = str(selected_url).strip()
        self._publish_status(
            status="pending",
            channel="http",
            event_type=event_type,
            step=step,
            run_id=run_id,
            target=url,
            message="HTTP feedback is being sent",
        )
        try:
            active_urls = _enabled_http_endpoint_urls(get_main_config())
            if not url or url not in active_urls:
                raise RuntimeError("The HTTP feedback endpoint is no longer enabled in public configuration")

            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request = Request(
                url,
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urlopen(request, timeout=5.0) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"HTTP {response.status}")
                response_status = response.status

            # Keep the local test log from blocking or corrupting actual HTTP
            # feedback. Final-step success and SOP completion can be dispatched
            # concurrently, so the read/append/write cycle must be serialized.
            try:
                with HTTP_FEEDBACK_DEBUG_FILE_LOCK:
                    json_file = JsonFile(r"C:\Users\LAI8PK\Desktop\update\test.json")
                    cache_data = json_file.read_json_file()
                    if not isinstance(cache_data, list):
                        cache_data = []
                    cache_data.append(payload)
                    json_file.write_json_file(cache_data)
            except Exception:
                logger.exception("Failed to append HTTP feedback debug payload")

            self._publish_status(
                status="success",
                channel="http",
                event_type=event_type,
                step=step,
                run_id=run_id,
                target=url,
                message=f"HTTP feedback succeeded (HTTP {response_status})",
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self._publish_status(
                status="failed",
                channel="http",
                event_type=event_type,
                step=step,
                run_id=run_id,
                target=url,
                message=message,
            )
            logger.exception("Failed to send step feedback to %s", url)

    def _send_modbus_feedback(
        self,
        signals: Any,
        event_type: str,
        step: dict[str, Any],
        run_id: str | None,
    ) -> None:
        if not isinstance(signals, list) or not signals:
            return
        client = None
        target = "Modbus"
        try:
            modbus_config = get_main_config().get("modbus", {})
            if not isinstance(modbus_config, dict):
                raise RuntimeError("Public Modbus configuration is missing")

            host = str(modbus_config.get("host", "")).strip()
            port = int(modbus_config.get("port", 502))
            timeout = float(modbus_config.get("timeout", 3))
            target = f"{host or 'unconfigured'}:{port}"
            self._publish_status(
                status="pending",
                channel="modbus",
                event_type=event_type,
                step=step,
                run_id=run_id,
                target=target,
                message=f"Writing {len(signals)} Modbus feedback signal(s)",
            )
            if not host:
                raise RuntimeError("Modbus host is empty")

            client = ModbusTcpClient(host=host, port=port, timeout=timeout)
            if not client.connect():
                raise ConnectionError(f"Cannot connect to Modbus server {host}:{port}")
            momentary_signals = []
            for signal in signals:
                validation_error = _validate_modbus_feedback_signal(signal)
                if validation_error:
                    raise RuntimeError(validation_error)
                result = self._write_modbus_signal(client, signal)
                if hasattr(result, "isError") and result.isError():
                    raise RuntimeError(
                        f"Write failed at slave {signal['slaveAddress']}, address {signal['address']}: {result}"
                    )
                if signal["dataType"] == "coil" and signal.get("instantaneous") is True:
                    momentary_signals.append(signal)

            if momentary_signals:
                time.sleep(MOMENTARY_COIL_DELAY_SECONDS)
                for signal in momentary_signals:
                    reset_signal = {
                        **signal,
                        "triggerValue": not signal["triggerValue"],
                        "instantaneous": False,
                    }
                    result = self._write_modbus_signal(client, reset_signal)
                    if hasattr(result, "isError") and result.isError():
                        raise RuntimeError(
                            "Momentary reset failed at "
                            f"slave {signal['slaveAddress']}, address {signal['address']}: {result}"
                        )
            self._publish_status(
                status="success",
                channel="modbus",
                event_type=event_type,
                step=step,
                run_id=run_id,
                target=target,
                message=(
                    f"Successfully wrote {len(signals)} Modbus feedback signal(s)"
                    + (
                        f" and reset {len(momentary_signals)} momentary coil(s) after 300 ms"
                        if momentary_signals
                        else ""
                    )
                ),
            )
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self._publish_status(
                status="failed",
                channel="modbus",
                event_type=event_type,
                step=step,
                run_id=run_id,
                target=target,
                message=message,
            )
            logger.exception("Failed to send step Modbus feedback")
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    logger.exception("Failed to close Modbus feedback client")

    @staticmethod
    def _write_modbus_signal(client: ModbusTcpClient, signal: dict[str, Any]):
        kwargs = {"device_id": signal["slaveAddress"]}
        try:
            if signal["dataType"] == "coil":
                return client.write_coil(signal["address"], signal["triggerValue"], **kwargs)
            return client.write_register(signal["address"], signal["triggerValue"], **kwargs)
        except TypeError:
            kwargs = {"slave": signal["slaveAddress"]}
            if signal["dataType"] == "coil":
                return client.write_coil(signal["address"], signal["triggerValue"], **kwargs)
            return client.write_register(signal["address"], signal["triggerValue"], **kwargs)

    def shutdown(self) -> None:
        # Do not block detector shutdown, but let already queued feedback finish.
        self._executor.shutdown(wait=False, cancel_futures=False)
