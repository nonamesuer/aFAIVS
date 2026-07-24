from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
SIDE_KEYS = ("left", "right")


def normalize_hand_style_config(
    config: Any,
    defaults: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, dict[str, Any]]:
    """Normalize independent left/right hand drawing styles."""
    source = config if isinstance(config, dict) else {}
    normalized: dict[str, dict[str, Any]] = {}

    for side in SIDE_KEYS:
        default_side = deepcopy(defaults[side])
        side_source = source.get(side)
        if not isinstance(side_source, dict):
            side_source = {}

        normalized[side] = {
            "keypointSize": _normalize_integer(
                side_source.get("keypointSize", default_side["keypointSize"]),
                default_side["keypointSize"],
                minimum=1,
                maximum=20,
                field_name=f"{side}.keypointSize",
                strict=strict,
            ),
            "keypointColor": _normalize_color(
                side_source.get("keypointColor", default_side["keypointColor"]),
                default_side["keypointColor"],
                field_name=f"{side}.keypointColor",
                strict=strict,
            ),
            "connectionWidth": _normalize_integer(
                side_source.get("connectionWidth", default_side["connectionWidth"]),
                default_side["connectionWidth"],
                minimum=1,
                maximum=10,
                field_name=f"{side}.connectionWidth",
                strict=strict,
            ),
            "connectionColor": _normalize_color(
                side_source.get("connectionColor", default_side["connectionColor"]),
                default_side["connectionColor"],
                field_name=f"{side}.connectionColor",
                strict=strict,
            ),
        }

    return normalized


def hex_to_bgr(color: str) -> tuple[int, int, int]:
    """Convert a normalized #RRGGBB string to an OpenCV BGR tuple."""
    return (
        int(color[5:7], 16),
        int(color[3:5], 16),
        int(color[1:3], 16),
    )


def _normalize_integer(
    value: Any,
    fallback: int,
    *,
    minimum: int,
    maximum: int,
    field_name: str,
    strict: bool,
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        if strict:
            raise ValueError(f"{field_name} must be an integer") from None
        number = int(fallback)

    if strict and not minimum <= number <= maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")
    return min(maximum, max(minimum, number))


def _normalize_color(
    value: Any,
    fallback: str,
    *,
    field_name: str,
    strict: bool,
) -> str:
    color = str(value or "").strip()
    if not HEX_COLOR_PATTERN.fullmatch(color):
        if strict:
            raise ValueError(f"{field_name} must use #RRGGBB format")
        color = fallback
    return color.upper()
