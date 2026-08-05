from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import Any


MANUAL_REGION_TYPE = "manual"
MANUAL_REGION_PREFIX = "__manual_region__:"
DEFAULT_MANUAL_REGIONS_CONFIG = {
    "version": 1,
    "cameras": {},
}

_REGION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
_MIN_REGION_SIZE = 0.002


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a finite number.") from None
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number.")
    return number


def _positive_integer(value: Any, field_name: str) -> int:
    number = _finite_number(value, field_name)
    if not number.is_integer() or number <= 0:
        raise ValueError(f"{field_name} must be a positive integer.")
    return int(number)


def manual_region_key(region_id: Any) -> str:
    normalized_id = str(region_id or "").strip()
    return (
        f"{MANUAL_REGION_PREFIX}{normalized_id}"
        if normalized_id
        else ""
    )


def is_manual_region_reference(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and str(value.get("type") or "").strip().lower()
        == MANUAL_REGION_TYPE
    )


def manual_region_reference_id(value: Any) -> str:
    if not is_manual_region_reference(value):
        return ""
    return str(value.get("id") or value.get("regionId") or "").strip()


def manual_region_reference_camera(value: Any) -> str:
    if not is_manual_region_reference(value):
        return ""
    return str(value.get("cameraName") or "").strip()


def region_reference_key(value: Any) -> str:
    """
    Return the internal label used by the existing rectangle-based state machine.

    Legacy string values remain ONNX labels. Manual references use a reserved
    label namespace so they cannot collide with model labels.
    """

    if is_manual_region_reference(value):
        return manual_region_key(manual_region_reference_id(value))
    if isinstance(value, dict):
        return str(value.get("label") or value.get("value") or "").strip()
    return str(value or "").strip()


def region_reference_name(value: Any) -> str:
    if is_manual_region_reference(value):
        return str(
            value.get("name")
            or value.get("regionName")
            or manual_region_reference_id(value)
            or ""
        ).strip()
    if isinstance(value, dict):
        return str(
            value.get("name")
            or value.get("label")
            or value.get("value")
            or ""
        ).strip()
    return str(value or "").strip()


def normalize_region_reference(value: Any) -> str | dict[str, str]:
    """Normalize a legacy ONNX label or a new manual-region reference."""

    if not is_manual_region_reference(value):
        if isinstance(value, dict):
            return str(value.get("label") or value.get("value") or "").strip()
        return str(value or "").strip()

    region_id = manual_region_reference_id(value)
    camera_name = manual_region_reference_camera(value)
    name = region_reference_name(value)
    if not region_id or not _REGION_ID_PATTERN.fullmatch(region_id):
        raise ValueError("Manual region reference id is invalid.")
    if not camera_name:
        raise ValueError("Manual region reference cameraName is required.")
    if not name:
        raise ValueError("Manual region reference name is required.")
    return {
        "type": MANUAL_REGION_TYPE,
        "id": region_id,
        "name": name,
        "cameraName": camera_name,
    }


def _normalize_region(region: Any, *, strict: bool) -> dict[str, Any] | None:
    if not isinstance(region, dict):
        if strict:
            raise ValueError("Each manual region must be an object.")
        return None

    region_id = str(region.get("id") or "").strip()
    name = str(region.get("name") or "").strip()
    color = str(region.get("color") or "#409EFF").strip().upper()

    if not region_id or not _REGION_ID_PATTERN.fullmatch(region_id):
        if strict:
            raise ValueError("Manual region id may contain only letters, numbers, '_' and '-'.")
        return None
    if not name or len(name) > 64:
        if strict:
            raise ValueError("Manual region name is required and must not exceed 64 characters.")
        return None
    if not _HEX_COLOR_PATTERN.fullmatch(color):
        if strict:
            raise ValueError(f"Manual region '{name}' color must be a #RRGGBB value.")
        color = "#409EFF"

    try:
        x1 = _finite_number(region.get("x1"), f"{name}.x1")
        y1 = _finite_number(region.get("y1"), f"{name}.y1")
        x2 = _finite_number(region.get("x2"), f"{name}.x2")
        y2 = _finite_number(region.get("y2"), f"{name}.y2")
    except ValueError:
        if strict:
            raise
        return None

    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    if not all(0.0 <= value <= 1.0 for value in (left, top, right, bottom)):
        if strict:
            raise ValueError(f"Manual region '{name}' coordinates must be between 0 and 1.")
        return None
    if right - left < _MIN_REGION_SIZE or bottom - top < _MIN_REGION_SIZE:
        if strict:
            raise ValueError(f"Manual region '{name}' is too small.")
        return None

    return {
        "id": region_id,
        "name": name,
        "color": color,
        "shape": "rectangle",
        "x1": round(left, 6),
        "y1": round(top, 6),
        "x2": round(right, 6),
        "y2": round(bottom, 6),
        "enabled": region.get("enabled") is not False,
    }


def normalize_manual_region_profile(
    profile: Any,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    profile = profile if isinstance(profile, dict) else {}
    try:
        reference_width = _positive_integer(
            profile.get("referenceWidth", 640),
            "referenceWidth",
        )
        reference_height = _positive_integer(
            profile.get("referenceHeight", 480),
            "referenceHeight",
        )
    except ValueError:
        if strict:
            raise
        reference_width, reference_height = 640, 480

    raw_regions = profile.get("regions", [])
    if not isinstance(raw_regions, list):
        if strict:
            raise ValueError("Manual regions must be an array.")
        raw_regions = []

    regions: list[dict[str, Any]] = []
    ids: set[str] = set()
    names: set[str] = set()
    for raw_region in raw_regions:
        region = _normalize_region(raw_region, strict=strict)
        if region is None:
            continue
        region_id = region["id"]
        normalized_name = region["name"].casefold()
        if region_id in ids:
            if strict:
                raise ValueError(f"Duplicate manual region id: {region_id}")
            continue
        if normalized_name in names:
            if strict:
                raise ValueError(f"Duplicate manual region name: {region['name']}")
            continue
        ids.add(region_id)
        names.add(normalized_name)
        regions.append(region)

    return {
        "referenceWidth": reference_width,
        "referenceHeight": reference_height,
        "regions": regions,
    }


def normalize_manual_regions_config(
    config: Any,
    *,
    strict: bool = False,
) -> dict[str, Any]:
    config = config if isinstance(config, dict) else {}
    raw_cameras = config.get("cameras", {})
    if not isinstance(raw_cameras, dict):
        if strict:
            raise ValueError("manualRegions.cameras must be an object.")
        raw_cameras = {}

    cameras: dict[str, dict[str, Any]] = {}
    all_ids: set[str] = set()
    for raw_camera_name, raw_profile in raw_cameras.items():
        camera_name = str(raw_camera_name or "").strip()
        if not camera_name:
            if strict:
                raise ValueError("Manual region camera name is required.")
            continue
        profile = normalize_manual_region_profile(raw_profile, strict=strict)
        unique_regions: list[dict[str, Any]] = []
        for region in profile["regions"]:
            if region["id"] in all_ids:
                if strict:
                    raise ValueError(
                        f"Manual region id '{region['id']}' must be globally unique."
                    )
                continue
            all_ids.add(region["id"])
            unique_regions.append(region)
        profile["regions"] = unique_regions
        cameras[camera_name] = profile

    return {
        "version": 1,
        "cameras": cameras,
    }


def build_manual_region_detections(
    config: Any,
    camera_name: str,
    frame_width: int,
    frame_height: int,
    included_region_keys: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Convert saved normalized rectangles to virtual detection boxes."""

    normalized = normalize_manual_regions_config(config)
    profile = normalized["cameras"].get(str(camera_name or "").strip())
    if not profile or frame_width <= 0 or frame_height <= 0:
        return []
    included = None if included_region_keys is None else {str(key or "").strip().casefold() for key in included_region_keys if str(key or "").strip()}

    detections: list[dict[str, Any]] = []
    for region in profile["regions"]:
        if region.get("enabled") is False:
            continue
        region_key = manual_region_key(region["id"])
        if included is not None and region_key.casefold() not in included:continue
        detections.append(
            {
                "label": region_key,
                "displayLabel": region["name"],
                "points": [
                    [
                        round(region["x1"] * frame_width, 2),
                        round(region["y1"] * frame_height, 2),
                    ],
                    [
                        round(region["x2"] * frame_width, 2),
                        round(region["y2"] * frame_height, 2),
                    ],
                ],
                "score": 1.0,
                "class_id": -1,
                "detectionType": "manual_region",
                "regionId": region["id"],
                "cameraName": camera_name,
                "color": region["color"],
            }
        )
    return detections


def collect_step_manual_region_keys(step: Any) -> set[str]:
    """Return every manual region used by one runtime/configured SOP step."""
    if isinstance(step, dict):context = step.get("context", {});rule_groups = (step.get("doneWhen", []),step.get("ngWhen", []))
    else:context = getattr(step,"context",{});rule_groups = (getattr(step,"done_when",[]),getattr(step,"ng_when",[]))
    context = context if isinstance(context,dict) else {}
    references = [context.get("fromRegion"),context.get("toRegion")]
    for rules in rule_groups:
        if isinstance(rules,list):references.extend((rule.get("region") or rule.get("toRegion")) for rule in rules if isinstance(rule,dict))
    return {region_reference_key(reference) for reference in references if is_manual_region_reference(reference)}


def collect_sop_manual_region_keys(definition: Any) -> set[str]:
    """Return manual regions referenced anywhere in one SOP definition."""
    if not isinstance(definition,dict):return set()
    keys: set[str] = set()
    steps = definition.get("steps", [])
    if isinstance(steps,list):
        for step in steps:keys.update(collect_step_manual_region_keys(step))
    extra_regions = definition.get("materialSourceRegions", [])
    if isinstance(extra_regions,list):keys.update(region_reference_key(reference) for reference in extra_regions if is_manual_region_reference(reference))
    return keys


def _manual_regions_by_id(config: Any) -> dict[str, tuple[str, dict[str, Any]]]:
    normalized = normalize_manual_regions_config(config)
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for camera_name, profile in normalized["cameras"].items():
        for region in profile["regions"]:
            result[region["id"]] = (camera_name, region)
    return result


def iter_sop_manual_region_references(
    sop_map_or_definition: Any,
) -> list[tuple[str, int, str, dict[str, Any]]]:
    """
    Return (sop_name, step_id, field_name, reference) for every manual ref.
    """

    if not isinstance(sop_map_or_definition, dict):
        return []

    if isinstance(sop_map_or_definition.get("steps"), list):
        definitions = [
            (
                str(sop_map_or_definition.get("sopName") or ""),
                sop_map_or_definition,
            )
        ]
    else:
        definitions = [
            (str(name), value)
            for name, value in sop_map_or_definition.items()
            if isinstance(value, dict)
        ]

    references: list[tuple[str, int, str, dict[str, Any]]] = []
    for sop_name, definition in definitions:
        steps = definition.get("steps", [])
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            context = step.get("context", {})
            if not isinstance(context, dict):
                continue
            try:
                step_id = int(step.get("id", index + 1))
            except (TypeError, ValueError):
                step_id = index + 1
            for field_name in ("fromRegion", "toRegion"):
                value = context.get(field_name)
                if is_manual_region_reference(value):
                    references.append((sop_name, step_id, field_name, value))
    return references


def find_manual_region_references(
    sop_map: Any,
    *,
    camera_name: str,
    region_id: str,
) -> list[str]:
    result: list[str] = []
    for sop_name, step_id, field_name, reference in iter_sop_manual_region_references(
        sop_map
    ):
        if (
            manual_region_reference_id(reference) == region_id
            and manual_region_reference_camera(reference) == camera_name
        ):
            result.append(
                f"{sop_name or '<unnamed SOP>'} / step {step_id} / {field_name}"
            )
    return result


def validate_sop_manual_region_references(
    definition: Any,
    manual_regions_config: Any,
    *,
    active_camera_name: str | None = None,
) -> str:
    available = _manual_regions_by_id(manual_regions_config)
    for sop_name, step_id, field_name, reference in iter_sop_manual_region_references(
        definition
    ):
        region_id = manual_region_reference_id(reference)
        reference_camera = manual_region_reference_camera(reference)
        found = available.get(region_id)
        prefix = f"SOP '{sop_name}' " if sop_name else ""
        if found is None:
            return (
                f"{prefix}step {step_id} {field_name} references missing "
                f"manual region '{region_reference_name(reference)}'."
            )
        configured_camera, region = found
        if configured_camera != reference_camera:
            return (
                f"{prefix}step {step_id} {field_name} manual region camera "
                f"does not match its saved camera."
            )
        if region.get("enabled") is False:
            return (
                f"{prefix}step {step_id} {field_name} references disabled "
                f"manual region '{region['name']}'."
            )
        if (
            active_camera_name is not None
            and configured_camera != active_camera_name
        ):
            return (
                f"{prefix}step {step_id} requires manual region "
                f"'{region['name']}' from camera '{configured_camera}', but "
                f"the active camera is '{active_camera_name}'."
            )
    return ""


def refresh_sop_manual_region_reference_names(
    sop_map: Any,
    manual_regions_config: Any,
) -> tuple[dict[str, Any], bool]:
    """Keep copied display names synchronized while preserving stable ids."""

    updated = deepcopy(sop_map) if isinstance(sop_map, dict) else {}
    available = _manual_regions_by_id(manual_regions_config)
    changed = False
    for _, _, _, reference in iter_sop_manual_region_references(updated):
        region_id = manual_region_reference_id(reference)
        found = available.get(region_id)
        if found is None:
            continue
        camera_name, region = found
        if reference.get("name") != region["name"]:
            reference["name"] = region["name"]
            changed = True
        if reference.get("cameraName") != camera_name:
            reference["cameraName"] = camera_name
            changed = True
    return updated, changed
