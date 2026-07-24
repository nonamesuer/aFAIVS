from __future__ import annotations

from typing import Any


AREA_FILL_ALPHA = 0.5


def collect_sop_area_labels(sop: Any) -> tuple[set[str], set[str]]:
    """Return normalized source- and target-region labels from an SOP snapshot."""
    from_area_labels: set[str] = set()
    target_area_labels: set[str] = set()
    if not isinstance(sop, dict):
        return from_area_labels, target_area_labels

    steps = sop.get("steps", [])
    if not isinstance(steps, list):
        return from_area_labels, target_area_labels

    for step in steps:
        if not isinstance(step, dict):
            continue
        context = step.get("context", {})
        if not isinstance(context, dict):
            continue

        from_region = str(context.get("fromRegion") or "").strip().casefold()
        target_region = str(context.get("toRegion") or "").strip().casefold()
        if from_region:
            from_area_labels.add(from_region)
        if target_region:
            target_area_labels.add(target_region)

    return from_area_labels, target_area_labels


def should_fill_area(
    label: Any,
    from_area_labels: set[str],
    target_area_labels: set[str],
    box_style: dict[str, Any] | None,
) -> bool:
    """Return whether this detection is a configured region that should be filled."""
    normalized_label = str(label or "").strip().casefold()
    if not normalized_label:
        return False

    style = box_style if isinstance(box_style, dict) else {}
    return (
        style.get("fromAreaFill") is True
        and normalized_label in from_area_labels
    ) or (
        style.get("targetAreaFill") is True
        and normalized_label in target_area_labels
    )
