from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

from pymodbus.client import ModbusTcpClient

from module._base import get_main_config

logger = logging.getLogger(__name__)

MODBUS_BIT_TYPES = {"coil", "discreteInput"}
MODBUS_REGISTER_TYPES = {"holdingRegister", "inputRegister"}


def _normalized_trigger_config(config: dict | None = None) -> dict:
    main_config = config if config is not None else get_main_config()
    integration = main_config.get("detectionIntegration", {})
    triggers = integration.get("triggers", {}) if isinstance(integration, dict) else {}
    if not isinstance(triggers, dict):
        triggers = {}

    http_parameters = [
        str(item).strip()
        for item in triggers.get("httpParameters", [])[:3]
        if isinstance(item, str) and str(item).strip()
    ]
    signals = [
        item
        for item in triggers.get("modbusSignals", [])[:3]
        if isinstance(item, dict)
    ]
    scanner_length = triggers.get("usbScannerLength", {})
    if not isinstance(scanner_length, dict):
        scanner_length = {}

    try:
        minimum = max(1, int(scanner_length.get("min", 1)))
    except (TypeError, ValueError):
        minimum = 1
    try:
        maximum = max(minimum, int(scanner_length.get("max", 128)))
    except (TypeError, ValueError):
        maximum = max(minimum, 128)

    return {
        "httpApi": bool(triggers.get("httpApi") and http_parameters),
        "httpParameters": http_parameters,
        "usbScanner": bool(triggers.get("usbScanner")),
        "usbScannerLength": {"min": minimum, "max": maximum},
        "modbus": bool(triggers.get("modbus") and signals),
        "modbusSignals": signals,
    }


class TriggerController:
    """Coordinates HTTP, USB scanner and Modbus triggers for one detection run."""

    def __init__(
        self,
        on_trigger: Callable[[str, dict[str, Any]], bool | None],
        config: dict | None = None,
        client_factory: Callable[..., Any] = ModbusTcpClient,
        poll_interval: float = 0.2,
    ) -> None:
        self.on_trigger = on_trigger
        self.config = _normalized_trigger_config(config)
        self.client_factory = client_factory
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._waiting = False
        self._triggered = False
        self._source: str | None = None
        self._triggered_at: float | None = None

    @property
    def methods(self) -> list[str]:
        return [
            method
            for method, enabled in (
                ("http", self.config["httpApi"]),
                ("usb", self.config["usbScanner"]),
                ("modbus", self.config["modbus"]),
            )
            if enabled
        ]

    @property
    def requires_trigger(self) -> bool:
        return bool(self.methods)

    @property
    def waiting(self) -> bool:
        with self._lock:
            return self._active and self._waiting

    def start(self) -> None:
        with self._lock:
            self._active = True
            self._waiting = self.requires_trigger
            self._triggered = not self.requires_trigger
            self._source = None
            self._triggered_at = None
        self._stop_event.clear()
        if self.config["modbus"]:
            self._thread = threading.Thread(
                target=self._poll_modbus,
                name="modbus-trigger",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            self._active = False
            self._waiting = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "trigger_configured": self.requires_trigger,
                "waiting_for_trigger": self._active and self._waiting,
                "detecting": self._active and not self._waiting,
                "trigger_methods": self.methods,
                "trigger_source": self._source,
                "triggered_at": self._triggered_at,
            }

    def _accept(self, source: str, payload: dict[str, Any]) -> bool:
        with self._lock:
            if not self._active or not self._waiting or self._triggered:
                return False
            self._waiting = False
            self._triggered = True
            self._source = source
            self._triggered_at = time.time()

        try:
            accepted = self.on_trigger(source, payload)
        except Exception:
            logger.exception("Failed to activate detection for %s trigger", source)
            accepted = False

        if accepted is False:
            with self._lock:
                self._waiting = True
                self._triggered = False
                self._source = None
                self._triggered_at = None
            return False
        return True

    def trigger_http(self, parameters: Mapping[str, Any]) -> tuple[bool, str]:
        if not self.config["httpApi"]:
            return False, "HTTP trigger is not enabled"
        missing = [
            name for name in self.config["httpParameters"] if name not in parameters
        ]
        if missing:
            return False, f"Missing HTTP trigger parameters: {', '.join(missing)}"
        values = {name: parameters.get(name) for name in self.config["httpParameters"]}
        if not self._accept("http", {"parameters": values}):
            return False, "Detection is not waiting for a trigger"
        return True, "HTTP trigger accepted"

    def trigger_usb(self, value: str) -> tuple[bool, str]:
        if not self.config["usbScanner"]:
            return False, "USB scanner trigger is not enabled"
        minimum = self.config["usbScannerLength"]["min"]
        maximum = self.config["usbScannerLength"]["max"]
        length = len(value)
        if length < minimum or length > maximum:
            return False, f"USB scanner value length must be between {minimum} and {maximum}"
        if not self._accept("usb", {"value": value, "length": length}):
            return False, "Detection is not waiting for a trigger"
        return True, "USB scanner trigger accepted"

    @staticmethod
    def _read_signal(client: Any, signal: dict[str, Any]) -> Any:
        data_type = signal.get("dataType")
        address = int(signal.get("address", 0))
        device_id = int(signal.get("slaveAddress", 1))
        method_name = {
            "coil": "read_coils",
            "discreteInput": "read_discrete_inputs",
            "holdingRegister": "read_holding_registers",
            "inputRegister": "read_input_registers",
        }.get(data_type)
        if not method_name:
            raise ValueError(f"Unsupported Modbus data type: {data_type}")
        method = getattr(client, method_name)
        try:
            response = method(address, count=1, device_id=device_id)
        except TypeError:
            response = method(address, count=1, slave=device_id)
        if response is None or response.isError():
            raise RuntimeError(f"Unable to read Modbus {data_type} at {address}")
        if data_type in MODBUS_BIT_TYPES:
            return bool(response.bits[0])
        return int(response.registers[0])

    def _poll_modbus(self) -> None:
        main_config = get_main_config()
        connection = main_config.get("modbus", {})
        client = self.client_factory(
            host=str(connection.get("host", "127.0.0.1")),
            port=int(connection.get("port", 502)),
            timeout=float(connection.get("timeout", 3)),
        )
        try:
            while not self._stop_event.is_set() and self.waiting:
                try:
                    if not client.connect():
                        self._stop_event.wait(self.poll_interval)
                        continue
                    for signal in self.config["modbusSignals"]:
                        actual = self._read_signal(client, signal)
                        expected = signal.get("triggerValue")
                        if signal.get("dataType") in MODBUS_BIT_TYPES:
                            matched = actual is bool(expected)
                        else:
                            matched = actual == int(expected)
                        if matched:
                            self._accept(
                                "modbus",
                                {
                                    "signal": dict(signal),
                                    "actualValue": actual,
                                },
                            )
                            return
                except Exception:
                    logger.exception("Failed while polling Modbus trigger")
                self._stop_event.wait(self.poll_interval)
        finally:
            try:
                client.close()
            except Exception:
                logger.exception("Failed to close Modbus trigger client")
