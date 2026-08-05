from __future__ import annotations

import re
import math
from copy import deepcopy
from typing import Any


MAX_SOP_NAME_LENGTH = 64
SOP_NAME_PATTERN = re.compile(r"^[\w-]+$", re.UNICODE)
DEFAULT_READY_CHECK_CONFIG = {"enabled": True, "timeout": 10}
MIN_READY_CHECK_TIMEOUT_SECONDS = 1
MAX_READY_CHECK_TIMEOUT_SECONDS = 3600


def normalize_ready_check_config(value: Any, *, strict: bool = False) -> dict[str, bool | int | float]:
    """Normalize SOP-level preparation checking while keeping old SOP files compatible."""
    if value is None:return deepcopy(DEFAULT_READY_CHECK_CONFIG)
    if not isinstance(value, dict):
        if strict:raise ValueError("readyCheck must be an object.")
        return deepcopy(DEFAULT_READY_CHECK_CONFIG)
    enabled = value.get("enabled", DEFAULT_READY_CHECK_CONFIG["enabled"])
    timeout = value.get("timeout", DEFAULT_READY_CHECK_CONFIG["timeout"])
    if strict and not isinstance(enabled, bool):raise ValueError("readyCheck.enabled must be a boolean.")
    enabled = enabled if isinstance(enabled, bool) else DEFAULT_READY_CHECK_CONFIG["enabled"]
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        if strict:raise ValueError("readyCheck.timeout must be a number.")
        timeout = DEFAULT_READY_CHECK_CONFIG["timeout"]
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout < MIN_READY_CHECK_TIMEOUT_SECONDS or timeout > MAX_READY_CHECK_TIMEOUT_SECONDS:
        if strict:raise ValueError(f"readyCheck.timeout must be between {MIN_READY_CHECK_TIMEOUT_SECONDS} and {MAX_READY_CHECK_TIMEOUT_SECONDS} seconds.")
        timeout = float(DEFAULT_READY_CHECK_CONFIG["timeout"])
    if strict and not timeout.is_integer():raise ValueError("readyCheck.timeout must be an integer number of seconds.")
    return {"enabled": enabled, "timeout": int(timeout) if timeout.is_integer() else timeout}


def normalize_sop_name(value: Any) -> str:
    """Validate and normalize the user-facing SOP configuration key."""
    sop_name = str(value or "").strip()
    if not sop_name:
        raise ValueError("SOP name is required.")
    if len(sop_name) > MAX_SOP_NAME_LENGTH:
        raise ValueError(
            f"SOP name must not exceed {MAX_SOP_NAME_LENGTH} characters."
        )
    if not SOP_NAME_PATTERN.fullmatch(sop_name):
        raise ValueError(
            "SOP name may contain only letters, numbers, underscores, and hyphens."
        )
    return sop_name


def upsert_sop_definition(
    sop_map: dict[str, Any] | None,
    request_body: dict[str, Any],
    *,
    now: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Create, update, or rename one SOP without coupling its key to model."""
    if not isinstance(request_body, dict):
        raise ValueError("Invalid SOP configuration.")

    current_map = deepcopy(sop_map) if isinstance(sop_map, dict) else {}
    explicit_sop_name = "sopName" in request_body
    sop_name = normalize_sop_name(
        request_body.get("sopName")
        if explicit_sop_name
        else request_body.get("model")
    )
    original_name_raw = request_body.get("originalSopName")

    if explicit_sop_name:
        is_edit = bool(str(original_name_raw or "").strip())
        original_name = (
            normalize_sop_name(original_name_raw)
            if is_edit
            else sop_name
        )
    else:
        # Compatibility with the old request shape where model was also the key.
        original_name = sop_name
        is_edit = original_name in current_map

    model_name = str(request_body.get("model") or "").strip()
    if not model_name:
        raise ValueError("Model name is required.")

    if is_edit and original_name not in current_map:
        raise ValueError(f"SOP configuration '{original_name}' was not found.")
    if sop_name != original_name and sop_name in current_map:
        raise ValueError(f"SOP name '{sop_name}' already exists.")
    if not is_edit and sop_name in current_map:
        raise ValueError(f"SOP name '{sop_name}' already exists.")

    definition = {
        key: deepcopy(value)
        for key, value in request_body.items()
        if key not in {"sopName", "originalSopName"}
    }
    existing_definition = (
        current_map.get(original_name)
        if is_edit and isinstance(current_map.get(original_name), dict)
        else None
    )
    if existing_definition:
        for key, value in existing_definition.items():
            definition.setdefault(key, deepcopy(value))
    else:
        definition["create_time"] = now
        definition["enabled"] = False
    definition["readyCheck"] = normalize_ready_check_config(definition.get("readyCheck"), strict=True)
    definition["modify_time"] = now
    if is_edit and original_name != sop_name:
        del current_map[original_name]
    current_map[sop_name] = definition
    return current_map, sop_name, definition


def resolve_sop_definition(
    sop_map: dict[str, Any] | None,
    sop_name: Any,
) -> tuple[str, dict[str, Any]]:
    """Resolve an SOP key and return a copy carrying its transient sopName."""
    normalized_name = normalize_sop_name(sop_name)
    if not isinstance(sop_map, dict):
        raise ValueError(f"SOP configuration '{normalized_name}' was not found.")
    definition = sop_map.get(normalized_name)
    if not isinstance(definition, dict):
        raise ValueError(f"SOP configuration '{normalized_name}' was not found.")
    resolved = deepcopy(definition)
    resolved["sopName"] = normalized_name
    return normalized_name, resolved


def resolve_sop_model(
    sop_map: dict[str, Any] | None,
    sop_name: Any,
) -> tuple[str, str, dict[str, Any]]:
    """Resolve SOP key, referenced model folder, and SOP definition."""
    normalized_name, definition = resolve_sop_definition(sop_map, sop_name)
    model_name = str(definition.get("model") or "").strip()
    if not model_name:
        raise ValueError(
            f"SOP configuration '{normalized_name}' does not reference a model."
        )
    return normalized_name, model_name, definition
