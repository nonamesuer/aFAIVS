from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OBJECT_PHASES = ("source", "transit", "target")
HAND_SIDES = ("l", "r")


@dataclass(frozen=True)
class StepValidationResult:
    valid: bool
    code: str = ""
    message: str = ""


def normalize_object_detection(context: dict[str, Any] | None) -> dict[str, bool]:
    context = context if isinstance(context, dict) else {}
    raw = context.get("objectDetection")
    if isinstance(raw, dict):
        return {
            "source": bool(raw.get("source", True)),
            "transit": bool(raw.get("transit", False)),
            "target": bool(raw.get("target", True)),
        }

    legacy = context.get("expectedObjectRequire", True)
    if isinstance(legacy, dict):
        return {
            "source": bool(legacy.get("source", True)),
            "transit": bool(legacy.get("transit", False)),
            "target": bool(legacy.get("target", True)),
        }

    required = bool(legacy)
    return {
        "source": required,
        "transit": required,
        "target": required,
    }


def normalized_hand_points(context: dict[str, Any] | None) -> dict[str, list[int]]:
    context = context if isinstance(context, dict) else {}
    raw = context.get("handPoints")
    if not isinstance(raw, dict):
        return {}

    result: dict[str, list[int]] = {}
    for side in HAND_SIDES:
        indices = raw.get(side)
        if not isinstance(indices, list):
            continue
        normalized = sorted(
            {
                int(index)
                for index in indices
                if isinstance(index, (int, float)) and 0 <= int(index) <= 20
            }
        )
        if normalized:
            result[side] = normalized
    return result


def has_hand_tracking(context: dict[str, Any] | None) -> bool:
    return bool(normalized_hand_points(context))


def validate_vision_step(step: dict[str, Any]) -> StepValidationResult:
    step_id = step.get("id", "?")
    context = step.get("context") if isinstance(step.get("context"), dict) else {}
    expected = str(context.get("expectedObject", "")).strip()
    source = str(context.get("fromRegion", "")).strip()
    target_region = str(context.get("toRegion", "")).strip()
    phases = normalize_object_detection(context)
    hand_enabled = has_hand_tracking(context)
    any_object_phase = any(phases.values())

    if not target_region:
        return StepValidationResult(False, "target_region_required", f"Step {step_id}: toRegion is required")

    if not expected and any_object_phase:
        return StepValidationResult(
            False,
            "object_phase_without_expected_object",
            f"Step {step_id}: object detection phases require expectedObject",
        )

    if not expected and not hand_enabled:
        return StepValidationResult(
            False,
            "no_observation_method",
            f"Step {step_id}: configure expectedObject or hand keypoints",
        )

    if source:
        if expected and not hand_enabled:
            # With a fixed source and no hand evidence, source + transit are both
            # required. Otherwise a source disappearance can be an occlusion and
            # cannot be linked to the object later seen in the target.
            if not phases["source"] or not phases["transit"]:
                return StepValidationResult(
                    False,
                    "fixed_source_object_only_requires_source_and_transit",
                    f"Step {step_id}: without hand tracking, source and transit object detection must both be enabled",
                )
        elif not expected:
            # Hand-only fixed-source workflows are valid only when no object phase
            # is enabled, because there is no object label to evaluate.
            if any_object_phase:
                return StepValidationResult(
                    False,
                    "hand_only_object_phase_conflict",
                    f"Step {step_id}: disable all object detection phases when expectedObject is empty",
                )
        return StepValidationResult(True)

    # No fixed source region.
    if expected and not hand_enabled:
        # Object-only workflows without a source must prove a new object entered
        # the target. target=true is therefore mandatory; source/transit are
        # optional evidence gates.
        if not phases["target"]:
            return StepValidationResult(
                False,
                "free_source_object_only_requires_target",
                f"Step {step_id}: without fromRegion and hand tracking, target object detection must be enabled",
            )
    elif not expected and any_object_phase:
        return StepValidationResult(
            False,
            "hand_only_object_phase_conflict",
            f"Step {step_id}: disable all object detection phases when expectedObject is empty",
        )

    return StepValidationResult(True)


def validate_sop_config(config: dict[str, Any]) -> list[StepValidationResult]:
    errors: list[StepValidationResult] = []
    steps = config.get("steps") if isinstance(config, dict) else None
    if not isinstance(steps, list) or not steps:
        return [StepValidationResult(False, "steps_required", "SOP steps are required")]

    for step in steps:
        if not isinstance(step, dict):
            errors.append(StepValidationResult(False, "invalid_step", "Each SOP step must be an object"))
            continue
        if str(step.get("type", "p_object")) != "p_object":
            continue
        result = validate_vision_step(step)
        if not result.valid:
            errors.append(result)
    return errors


def build_execution_plan(step: dict[str, Any]) -> list[str]:
    """Return a concise phase plan used by API responses and UI previews."""
    context = step.get("context") if isinstance(step.get("context"), dict) else {}
    expected = str(context.get("expectedObject", "")).strip()
    source = str(context.get("fromRegion", "")).strip()
    target = str(context.get("toRegion", "")).strip()
    phases = normalize_object_detection(context)
    hand = has_hand_tracking(context)

    plan: list[str] = []
    if source:
        if phases["source"] and expected:
            plan.append(f"detect {expected} in {source}")
        if hand:
            plan.append(f"hand enters {source}" + (f" and engages {expected}" if phases["source"] and expected else ""))
        if not hand:
            plan.append(f"confirm one {expected} leaves {source} by source-count decrease")
    else:
        if phases["source"] and expected:
            plan.append(f"detect {expected} in the visible area")
        if hand:
            plan.append("detect a new hand action outside the target")

    if phases["transit"] and expected:
        plan.append(f"track {expected} during transit" + (" near the hand" if hand else ""))
    elif hand:
        plan.append("track the hand during transit")

    if phases["target"] and expected:
        plan.append(f"confirm {expected} count in {target} increases by one")
        if hand:
            plan.append("confirm the hand releases the object or leaves the target")
    elif hand:
        plan.append(f"confirm the hand enters {target}")
    else:
        plan.append(f"confirm the tracked {expected} enters {target}")

    return plan
