from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from module.sop_rules import (
    has_hand_tracking,
    normalize_object_detection,
    normalized_hand_points,
    validate_vision_step,
)


DEFAULT_STEP_TIMEOUT_SECONDS = 30.0
DEFAULT_MISS_TOLERANCE = 5
DEFAULT_MOVEMENT_THRESHOLD = 8.0


class SOPRunState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SOPStepState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


class SOPCyclePhase(str, Enum):
    WAITING = "waiting"
    ACQUIRING = "acquiring"
    TRANSIT = "transit"
    TARGET = "target"
    RELEASE = "release"


_PHASE_TO_PICK_STATE = {
    SOPCyclePhase.WAITING: "idle",
    SOPCyclePhase.ACQUIRING: "in_source",
    SOPCyclePhase.TRANSIT: "picked",
    SOPCyclePhase.TARGET: "in_target",
    SOPCyclePhase.RELEASE: "in_target",
}


@dataclass
class DetectionBox:
    label: str
    points: list[Any]
    score: float = 0.0
    class_id: int | None = None

    @property
    def xyxy(self) -> tuple[float, float, float, float] | None:
        if len(self.points) == 2:
            try:
                x1, y1 = self.points[0]
                x2, y2 = self.points[1]
                return float(x1), float(y1), float(x2), float(y2)
            except (TypeError, ValueError):
                return None
        if len(self.points) == 4:
            try:
                x1, y1, x2, y2 = self.points
                return float(x1), float(y1), float(x2), float(y2)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def center(self) -> tuple[float, float] | None:
        box = self.xyxy
        if box is None:
            return None
        x1, y1, x2, y2 = box
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0


@dataclass
class StepObservation:
    expected_boxes: list[DetectionBox]
    source_region_boxes: list[DetectionBox]
    target_region_boxes: list[DetectionBox]
    hand_points: list[tuple[float, float]]
    source_count: int
    target_count: int
    outside_source_count: int
    outside_target_count: int
    transit_count: int
    hand_visible: bool
    hand_in_source: bool
    hand_in_target: bool
    hand_on_object: bool
    outside_target_centers: list[tuple[float, float]]


@dataclass
class SOPStepRuntime:
    id: int
    name: str
    type: str = "p_object"
    hint: str = ""
    target: int = 1
    timeout: float = 0.0
    context: dict[str, Any] = field(default_factory=dict)
    done_when: list[dict[str, Any]] = field(default_factory=list)
    ng_when: list[dict[str, Any]] = field(default_factory=list)

    state: SOPStepState = SOPStepState.PENDING
    matched_count: int = 0
    stable_count: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    paused_at: float | None = None
    last_reason: str = ""

    phase: SOPCyclePhase = SOPCyclePhase.WAITING
    pick_state: str = "idle"
    hand_grip_state: str = "released"
    object_miss_count: int = 0
    hand_miss_count: int = 0
    miss_count: int = 0  # compatibility field: max(object_miss_count, hand_miss_count)

    blocked_pick_state: str | None = None
    awaiting_cycle_reset: bool = False
    cycle_reset_armed: bool = False
    cycle_baseline_initialized: bool = False

    source_baseline_count: int = 0
    target_baseline_count: int = 0
    outside_source_baseline_count: int = 0
    outside_target_baseline_count: int = 0
    initial_object_centers: list[tuple[float, float]] = field(default_factory=list)

    source_departure_seen: bool = False
    transit_seen: bool = False
    target_entry_seen: bool = False
    release_seen: bool = False

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "SOPStepRuntime":
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            type=str(data.get("type", "p_object")),
            hint=str(data.get("hint", "")),
            target=max(1, int(data.get("target", 1) or 1)),
            timeout=_to_float(data.get("timeout", data.get("timeoutSeconds", 0))),
            context=data.get("context", {}) if isinstance(data.get("context"), dict) else {},
            done_when=data.get("doneWhen", []) if isinstance(data.get("doneWhen"), list) else [],
            ng_when=data.get("ngWhen", []) if isinstance(data.get("ngWhen"), list) else [],
        )

    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end_time = self.completed_at or self.paused_at or time.time()
        return round(max(0.0, end_time - self.started_at), 2)

    @property
    def hand_points_config(self) -> dict[str, list[int]]:
        return normalized_hand_points(self.context)

    @property
    def hand_gate_enabled(self) -> bool:
        return has_hand_tracking(self.context)

    @property
    def expected_object(self) -> str:
        return str(self.context.get("expectedObject", "")).strip()

    @property
    def from_region(self) -> str:
        return str(self.context.get("fromRegion", "")).strip()

    @property
    def to_region(self) -> str:
        return str(self.context.get("toRegion", "")).strip()

    @property
    def object_detection_config(self) -> dict[str, bool]:
        return normalize_object_detection(self.context)

    @property
    def require_object_at_source(self) -> bool:
        return self.object_detection_config["source"]

    @property
    def require_object_in_transit(self) -> bool:
        return self.object_detection_config["transit"]

    @property
    def require_object_at_target(self) -> bool:
        return self.object_detection_config["target"]

    @property
    def miss_tolerance(self) -> int:
        try:
            return max(0, int(self.context.get("missTolerance", DEFAULT_MISS_TOLERANCE)))
        except (TypeError, ValueError):
            return DEFAULT_MISS_TOLERANCE

    @property
    def movement_threshold(self) -> float:
        value = _to_float(self.context.get("movementThreshold", DEFAULT_MOVEMENT_THRESHOLD))
        return value if value > 0 else DEFAULT_MOVEMENT_THRESHOLD

    def validate_config(self) -> tuple[bool, str]:
        result = validate_vision_step(
            {
                "id": self.id,
                "type": self.type,
                "target": self.target,
                "context": self.context,
            }
        )
        return result.valid, result.message

    def set_phase(self, phase: SOPCyclePhase) -> None:
        self.phase = phase
        self.pick_state = _PHASE_TO_PICK_STATE[phase]

    def reset_cycle_runtime(self) -> None:
        self.set_phase(SOPCyclePhase.WAITING)
        self.stable_count = 0
        self.object_miss_count = 0
        self.hand_miss_count = 0
        self.miss_count = 0
        self.hand_grip_state = "released"
        self.cycle_baseline_initialized = False
        self.source_baseline_count = 0
        self.target_baseline_count = 0
        self.outside_source_baseline_count = 0
        self.outside_target_baseline_count = 0
        self.initial_object_centers = []
        self.source_departure_seen = False
        self.transit_seen = False
        self.target_entry_seen = False
        self.release_seen = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "hint": self.hint,
            "target": self.target,
            "timeout": self.timeout,
            "context": self.context,
            "state": self.state.value,
            "matched_count": self.matched_count,
            "stable_count": self.stable_count,
            "elapsed": self.elapsed,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "paused_at": self.paused_at,
            "last_reason": self.last_reason,
            "phase": self.phase.value,
            "pick_state": self.pick_state,
            "hand_grip_state": self.hand_grip_state,
            "miss_count": self.miss_count,
            "object_miss_count": self.object_miss_count,
            "hand_miss_count": self.hand_miss_count,
            "blocked_pick_state": self.blocked_pick_state,
            "awaiting_cycle_reset": self.awaiting_cycle_reset,
            "cycle_reset_armed": self.cycle_reset_armed,
            "cycle": {
                "current": min(self.matched_count + 1, self.target),
                "completed": self.matched_count,
                "target": self.target,
                "source_baseline_count": self.source_baseline_count,
                "target_baseline_count": self.target_baseline_count,
                "source_departure_seen": self.source_departure_seen,
                "transit_seen": self.transit_seen,
                "target_entry_seen": self.target_entry_seen,
                "release_seen": self.release_seen,
            },
        }


class SOPStateMachine:
    """Config-driven visual SOP state machine.

    Each cycle records source and target object-count baselines. A cycle can only
    complete when new evidence is observed relative to those baselines. This is
    the key protection for target > 1 and for source regions containing several
    objects of the same class.
    """

    _PICK_STATE_ORDER = {"idle": 0, "in_source": 1, "picked": 2, "in_target": 3, "done": 4}

    def __init__(
        self,
        sop_config: dict[str, Any] | None = None,
        stable_frames: int = 3,
        min_score: float | None = None,
        default_step_timeout: float = DEFAULT_STEP_TIMEOUT_SECONDS,
        enable_ready_check: bool = True,
        ready_check_timeout: float = 10.0,
    ):
        self.sop_config = sop_config or {}
        self.sop_name = str(self.sop_config.get("model", ""))
        self.confidence = self._normalize_confidence(self.sop_config.get("confidence", 0), min_score)
        self.stable_frames = max(1, int(stable_frames))
        self.steps = [
            SOPStepRuntime.from_config(step)
            for step in self.sop_config.get("steps", [])
            if isinstance(step, dict)
        ]
        self.default_step_timeout = self._resolve_default_timeout(default_step_timeout)
        for step in self.steps:
            if step.timeout <= 0:
                step.timeout = self.default_step_timeout
        self.expected_objects_by_step = [step.expected_object for step in self.steps]
        self.state = SOPRunState.IDLE
        self.current_index = 0
        self.started_at: float | None = None
        self.completed_at: float | None = None
        self.last_reason = ""
        self.paused_at: float | None = None
        self.state_before_pause: SOPRunState | None = None
        self.enable_ready_check = enable_ready_check
        self.ready_check_timeout = ready_check_timeout
        self.ready_started_at: float | None = None

    @classmethod
    def from_sop_map(
        cls,
        sop_map: dict[str, Any],
        stable_frames: int = 3,
        min_score: float | None = None,
        default_step_timeout: float = DEFAULT_STEP_TIMEOUT_SECONDS,
        enable_ready_check: bool = True,
        ready_check_timeout: float = 10.0,
    ) -> "SOPStateMachine":
        return cls(
            select_enabled_sop_config(sop_map),
            stable_frames=stable_frames,
            min_score=min_score,
            default_step_timeout=default_step_timeout,
            enable_ready_check=enable_ready_check,
            ready_check_timeout=ready_check_timeout,
        )

    @property
    def current_step(self) -> SOPStepRuntime | None:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None

    @property
    def requires_hand_tracking(self) -> bool:
        return any(step.hand_gate_enabled for step in self.steps)

    @property
    def max_required_hands(self) -> int:
        counts = [len(step.hand_points_config) for step in self.steps if step.hand_gate_enabled]
        return max(counts) if counts else 0

    def start(self) -> None:
        if not self.steps:
            self.state = SOPRunState.FAILED
            self.last_reason = "SOP steps is empty"
            return

        for step in self.steps:
            valid, reason = step.validate_config()
            if not valid:
                self.state = SOPRunState.FAILED
                self.last_reason = reason
                return
            step.state = SOPStepState.PENDING
            step.matched_count = 0
            step.started_at = None
            step.completed_at = None
            step.paused_at = None
            step.last_reason = ""
            step.blocked_pick_state = None
            step.awaiting_cycle_reset = False
            step.cycle_reset_armed = False
            step.reset_cycle_runtime()

        self.current_index = 0
        self.started_at = time.time()
        self.completed_at = None
        self.paused_at = None
        self.state_before_pause = None
        self.ready_started_at = time.time()
        if self.enable_ready_check:
            self.state = SOPRunState.IDLE
            self.last_reason = "Waiting for required regions and objects"
        else:
            self.state = SOPRunState.RUNNING
            step = self.current_step
            if step:
                self._start_step(step)

    def reset(self) -> None:
        self.state = SOPRunState.IDLE
        self.current_index = 0
        self.started_at = None
        self.completed_at = None
        self.paused_at = None
        self.state_before_pause = None
        self.last_reason = ""
        self.ready_started_at = None
        for step in self.steps:
            step.state = SOPStepState.PENDING
            step.matched_count = 0
            step.started_at = None
            step.completed_at = None
            step.paused_at = None
            step.last_reason = ""
            step.blocked_pick_state = None
            step.awaiting_cycle_reset = False
            step.cycle_reset_armed = False
            step.reset_cycle_runtime()

    def pause(self) -> bool:
        if self.state in {SOPRunState.PAUSED, SOPRunState.COMPLETED}:
            return False
        self.state_before_pause = self.state
        self.paused_at = time.time()
        step = self.current_step
        if step and step.started_at is not None:
            step.paused_at = self.paused_at
        self.state = SOPRunState.PAUSED
        self.last_reason = "SOP paused"
        return True

    def resume(self) -> bool:
        if self.state != SOPRunState.PAUSED:
            return False
        now = time.time()
        paused_duration = max(0.0, now - self.paused_at) if self.paused_at is not None else 0.0
        step = self.current_step
        if step:
            if step.started_at is not None:
                step.started_at += paused_duration
            step.paused_at = None
        if self.ready_started_at is not None:
            self.ready_started_at += paused_duration
        if self.started_at is not None:
            self.started_at += paused_duration
        self.state = self.state_before_pause or SOPRunState.RUNNING
        self.paused_at = None
        self.state_before_pause = None
        self.last_reason = "SOP resumed"
        return True

    def update(
        self,
        detections: list[dict[str, Any]] | dict[str, Any] | None,
        hands: dict[str, list[tuple[float, float]]] | None = None,
    ) -> dict[str, Any]:
        if self.state == SOPRunState.IDLE and self.enable_ready_check:
            return self._handle_ready_check(detections)
        if self.state == SOPRunState.IDLE and not self.enable_ready_check:
            self.start()
        if self.state in {SOPRunState.PAUSED, SOPRunState.COMPLETED}:
            return self.snapshot(matched=False, reason=self.last_reason)

        step = self.current_step
        if step is None:
            self._complete_all("All steps completed")
            return self.snapshot(matched=False, reason=self.last_reason)

        valid, validation_reason = step.validate_config()
        if not valid:
            self.state = SOPRunState.FAILED
            step.state = SOPStepState.FAILED
            step.last_reason = validation_reason
            self.last_reason = validation_reason
            return self.snapshot(matched=False, reason=validation_reason)

        boxes = normalize_detections(detections, min_score=self.confidence)

        ng_matched, ng_reason = self._match_ng_when(step, boxes)
        default_ng_reason = self._match_default_wrong_object(step, boxes)
        blocking_reason = ng_reason if ng_matched else default_ng_reason
        if blocking_reason:
            if self.state != SOPRunState.FAILED:
                self._fail_current_step(blocking_reason)
            step.last_reason = blocking_reason
            return self.snapshot(matched=False, reason=blocking_reason)

        if self.state == SOPRunState.FAILED:
            self._recover_current_step("Blocking condition cleared; restarting current cycle")

        timeout_reason = self._check_timeout(step)
        if timeout_reason:
            self._fail_current_step(timeout_reason)
            return self.snapshot(matched=False, reason=timeout_reason)

        observation = self._observe(step, boxes, hands)
        if step.awaiting_cycle_reset:
            ready, reason = self._try_reset_for_next_cycle(step, observation)
            step.last_reason = reason
            if not ready:
                return self.snapshot(matched=False, reason=reason)

        completed_once, reason = self._match_step(step, boxes, observation)
        step.last_reason = reason
        if completed_once:
            step.stable_count += 1
            if step.stable_count >= self.stable_frames:
                self._confirm_cycle_completed(step, reason, observation)
        else:
            step.stable_count = 0
        return self.snapshot(matched=completed_once, reason=reason)

    def snapshot(self, matched: bool = False, reason: str = "") -> dict[str, Any]:
        done_count = sum(1 for step in self.steps if step.state == SOPStepState.DONE)
        return {
            "state": self.state.value,
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "steps": [step.to_dict() for step in self.steps],
            "progress": {"done": done_count, "total": len(self.steps), "current_index": self.current_index},
            "matched": matched,
            "reason": reason,
            "updated_at": time.time(),
        }

    def current_hand_action_points(
        self, hands: dict[str, list[tuple[float, float]]] | None
    ) -> list[tuple[float, float]]:
        step = self.current_step
        return self._hand_action_points(step, hands) if step else []

    def _handle_ready_check(
        self, detections: list[dict[str, Any]] | dict[str, Any] | None
    ) -> dict[str, Any]:
        step = self.current_step
        if step is None:
            self._complete_all("All steps completed")
            return self.snapshot(matched=False, reason=self.last_reason)
        boxes = normalize_detections(detections, min_score=self.confidence)
        ready, missing = self._check_step_ready(step, boxes)
        if not ready:
            if self.ready_started_at and time.time() - self.ready_started_at > self.ready_check_timeout:
                reason = f"Ready check timeout: waiting for {', '.join(missing)}"
                self._fail_current_step(reason)
                return self.snapshot(matched=False, reason=reason)
            reason = f"Waiting for: {', '.join(missing)}"
            return self.snapshot(matched=False, reason=reason)
        self._start_step(step)
        return self.snapshot(matched=False, reason="Required regions and objects ready")

    def _check_step_ready(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> tuple[bool, list[str]]:
        required = {step.to_region}
        if step.from_region:
            required.add(step.from_region)
        if step.expected_object and step.require_object_at_source:
            required.add(step.expected_object)
        if step.expected_object and not step.from_region and not step.hand_gate_enabled and step.require_object_in_transit:
            required.add(step.expected_object)
        for rule in step.done_when:
            if isinstance(rule, dict):
                region = str(rule.get("region") or rule.get("toRegion") or "").strip()
                if region:
                    required.add(region)
        detected = {box.label.strip().lower() for box in boxes}
        missing = [label for label in required if label and label.lower() not in detected]
        return not missing, missing

    def _start_step(self, step: SOPStepRuntime) -> None:
        step.state = SOPStepState.ACTIVE
        step.started_at = time.time()
        step.completed_at = None
        step.matched_count = 0
        step.awaiting_cycle_reset = False
        step.cycle_reset_armed = False
        step.reset_cycle_runtime()
        self.state = SOPRunState.RUNNING
        if self.started_at is None:
            self.started_at = time.time()
        self.last_reason = "SOP started"

    def _observe(
        self,
        step: SOPStepRuntime,
        boxes: list[DetectionBox],
        hands: dict[str, list[tuple[float, float]]] | None,
    ) -> StepObservation:
        expected_boxes = find_boxes(boxes, step.expected_object) if step.expected_object else []
        source_regions = find_boxes(boxes, step.from_region) if step.from_region else []
        target_regions = find_boxes(boxes, step.to_region)
        hand_points = self._hand_action_points(step, hands)

        source_count = count_boxes_inside_regions(expected_boxes, source_regions)
        target_count = count_boxes_inside_regions(expected_boxes, target_regions)
        outside_source_count = len(expected_boxes) - source_count if source_regions else len(expected_boxes)
        outside_target_count = len(expected_boxes) - target_count
        transit_count = count_boxes_outside_regions(expected_boxes, source_regions + target_regions)
        centers = [box.center for box in expected_boxes if box.center and not point_in_any_region(box.center, target_regions)]

        return StepObservation(
            expected_boxes=expected_boxes,
            source_region_boxes=source_regions,
            target_region_boxes=target_regions,
            hand_points=hand_points,
            source_count=source_count,
            target_count=target_count,
            outside_source_count=outside_source_count,
            outside_target_count=outside_target_count,
            transit_count=transit_count,
            hand_visible=bool(hand_points),
            hand_in_source=self._points_engage_boxes(hand_points, source_regions, self._hand_margin(step)),
            hand_in_target=self._points_engage_boxes(hand_points, target_regions, self._hand_margin(step)),
            hand_on_object=self._points_engage_boxes(hand_points, expected_boxes, self._hand_margin(step)),
            outside_target_centers=[center for center in centers if center is not None],
        )

    def _initialize_cycle(self, step: SOPStepRuntime, obs: StepObservation) -> None:
        step.source_baseline_count = obs.source_count
        step.target_baseline_count = obs.target_count
        step.outside_source_baseline_count = obs.outside_source_count
        step.outside_target_baseline_count = obs.outside_target_count
        step.initial_object_centers = list(obs.outside_target_centers)
        step.cycle_baseline_initialized = True
        step.object_miss_count = 0
        step.hand_miss_count = 0
        step.miss_count = 0
        step.source_departure_seen = False
        step.transit_seen = False
        step.target_entry_seen = False
        step.release_seen = False

    def _match_step(
        self, step: SOPStepRuntime, boxes: list[DetectionBox], obs: StepObservation
    ) -> tuple[bool, str]:
        if step.done_when:
            matched_count, reason = self._match_done_when(step.done_when, boxes)
            return matched_count >= len([rule for rule in step.done_when if isinstance(rule, dict)]), reason
        if not step.cycle_baseline_initialized:
            self._initialize_cycle(step, obs)
        if step.from_region:
            return self._match_fixed_source(step, obs)
        return self._match_free_source(step, obs)

    def _match_fixed_source(self, step: SOPStepRuntime, obs: StepObservation) -> tuple[bool, str]:
        if step.hand_gate_enabled:
            return self._match_fixed_source_with_hand(step, obs)
        return self._match_fixed_source_object_only(step, obs)

    def _match_fixed_source_object_only(
        self, step: SOPStepRuntime, obs: StepObservation
    ) -> tuple[bool, str]:
        label = step.expected_object
        source = step.from_region
        target = step.to_region
        target_delta = obs.target_count > step.target_baseline_count

        if step.phase == SOPCyclePhase.WAITING:
            # A very fast next pickup can happen before the state machine sees a
            # separate steady WAITING frame. Because the previous completion
            # frame already captured the baseline, accept a source-count decrease
            # plus a newly visible object outside the source immediately.
            fast_departure = (
                step.source_baseline_count > 0
                and obs.source_count < step.source_baseline_count
                and obs.outside_source_count > step.outside_source_baseline_count
            )
            if fast_departure or target_delta:
                step.source_departure_seen = True
                step.transit_seen = True
                step.set_phase(SOPCyclePhase.TRANSIT)
            elif obs.source_count <= 0:
                return False, f"Waiting for {label} in {source}"
            else:
                # Inventory can be replenished while waiting. The latest stable
                # count becomes this cycle's source baseline.
                step.source_baseline_count = obs.source_count
                step.outside_source_baseline_count = obs.outside_source_count
                step.target_baseline_count = obs.target_count
                step.set_phase(SOPCyclePhase.ACQUIRING)
                return False, f"{label} ready in {source}; waiting for one item to leave"

        if step.phase == SOPCyclePhase.ACQUIRING:
            if obs.source_count > step.source_baseline_count:
                step.source_baseline_count = obs.source_count
                step.outside_source_baseline_count = obs.outside_source_count
                return False, f"{source} inventory baseline updated to {obs.source_count}"
            source_decreased = obs.source_count < step.source_baseline_count
            moved_object_visible = obs.outside_source_count > step.outside_source_baseline_count
            if source_decreased and (moved_object_visible or target_delta):
                step.source_departure_seen = True
                step.transit_seen = True
                step.object_miss_count = 0
                step.set_phase(SOPCyclePhase.TRANSIT)
            elif source_decreased:
                return self._loss_or_restart(
                    step,
                    "object",
                    f"One {label} left {source} but is temporarily occluded",
                )
            else:
                step.object_miss_count = 0
                return False, f"Waiting for one {label} to leave {source}"

        if step.phase == SOPCyclePhase.TRANSIT:
            if target_delta:
                step.target_entry_seen = True
                step.set_phase(SOPCyclePhase.TARGET)
                return True, f"A new {label} entered {target}"
            if step.require_object_in_transit:
                moved_object_visible = obs.outside_source_count > step.outside_source_baseline_count
                if moved_object_visible:
                    step.transit_seen = True
                    step.object_miss_count = 0
                    return False, f"Tracking {label} from {source} to {target}"
                return self._loss_or_restart(step, "object", f"{label} lost during transit")
            return False, f"Waiting for {label} to enter {target}"

        if step.phase == SOPCyclePhase.TARGET:
            return target_delta, f"A new {label} entered {target}" if target_delta else f"Waiting for {label} in {target}"

        return False, f"Waiting for {label}"

    def _match_fixed_source_with_hand(
        self, step: SOPStepRuntime, obs: StepObservation
    ) -> tuple[bool, str]:
        label = step.expected_object
        source = step.from_region
        target = step.to_region
        target_delta = obs.target_count > step.target_baseline_count

        if step.phase == SOPCyclePhase.WAITING:
            if step.require_object_at_source and obs.source_count <= 0:
                return False, f"Waiting for {label} in {source}"
            if not obs.hand_in_source:
                return False, f"Waiting for hand in {source}"
            step.source_baseline_count = obs.source_count
            step.outside_source_baseline_count = obs.outside_source_count
            step.target_baseline_count = obs.target_count
            step.set_phase(SOPCyclePhase.ACQUIRING)
            if step.require_object_at_source and not obs.hand_on_object:
                return False, f"Hand entered {source}; waiting to engage {label}"
            if obs.hand_on_object:
                step.hand_grip_state = "gripping"
            return False, f"Hand ready in {source}"

        if step.phase == SOPCyclePhase.ACQUIRING:
            if obs.hand_on_object:
                step.hand_grip_state = "gripping"
                step.hand_miss_count = 0
            if not obs.hand_visible:
                return self._loss_or_restart(step, "hand", "Hand lost while acquiring object")
            if obs.hand_in_source:
                if step.require_object_at_source and step.hand_grip_state != "gripping":
                    return False, f"Move hand close to {label} in {source}"
                return False, f"Pick {label or 'the item'} from {source}"
            if step.require_object_at_source and step.hand_grip_state != "gripping":
                return self._restart_cycle(step, f"Hand left {source} without engaging {label}")
            step.source_departure_seen = True
            step.set_phase(SOPCyclePhase.TRANSIT)

        if step.phase == SOPCyclePhase.TRANSIT:
            if not obs.hand_visible:
                return self._loss_or_restart(step, "hand", "Hand lost during transit")
            step.hand_miss_count = 0
            if obs.hand_in_source:
                step.set_phase(SOPCyclePhase.ACQUIRING)
                step.hand_grip_state = "released"
                return False, f"Hand returned to {source}; pick again"

            if step.require_object_in_transit:
                object_evidence = obs.hand_on_object or obs.transit_count > 0 or target_delta
                if object_evidence:
                    step.transit_seen = True
                    step.object_miss_count = 0
                else:
                    return self._loss_or_restart(step, "object", f"{label} lost during transit")
            else:
                step.transit_seen = True

            if obs.hand_in_target or target_delta:
                step.target_entry_seen = True
                step.set_phase(SOPCyclePhase.TARGET)
                if not step.require_object_at_target:
                    return True, f"Hand or {label or 'item'} entered {target}"
            else:
                return False, f"Moving to {target}"

        if step.phase == SOPCyclePhase.TARGET:
            if not step.require_object_at_target:
                return True, f"Hand or {label or 'item'} entered {target}"
            if target_delta:
                step.target_entry_seen = True
                step.object_miss_count = 0
                step.set_phase(SOPCyclePhase.RELEASE)
            else:
                return self._loss_or_restart(step, "object", f"Waiting for a new {label} in {target}")

        if step.phase == SOPCyclePhase.RELEASE:
            if not step.target_entry_seen:
                step.set_phase(SOPCyclePhase.TARGET)
                return False, f"Waiting for {label} in {target}"
            if not obs.hand_on_object or not obs.hand_in_target:
                step.release_seen = True
                step.hand_grip_state = "released"
                return True, f"{label} placed in {target} and hand released"
            return False, f"Waiting for hand to release {label} or leave {target}"

        return False, f"Waiting for operation in {source}"

    def _match_free_source(self, step: SOPStepRuntime, obs: StepObservation) -> tuple[bool, str]:
        if step.hand_gate_enabled:
            return self._match_free_source_with_hand(step, obs)
        return self._match_free_source_object_only(step, obs)

    def _match_free_source_object_only(
        self, step: SOPStepRuntime, obs: StepObservation
    ) -> tuple[bool, str]:
        label = step.expected_object
        target = step.to_region
        target_delta = obs.target_count > step.target_baseline_count

        if step.phase == SOPCyclePhase.WAITING:
            if step.require_object_at_source and obs.outside_target_count <= 0:
                return False, f"Waiting for {label} in visible area outside {target}"
            if step.require_object_in_transit and obs.outside_target_count <= 0:
                return False, f"Waiting for moving {label} in visible area"
            step.initial_object_centers = list(obs.outside_target_centers)
            step.set_phase(SOPCyclePhase.TRANSIT if step.require_object_in_transit else SOPCyclePhase.TARGET)
            if step.phase == SOPCyclePhase.TARGET:
                return False, f"Waiting for a new {label} in {target}"

        if step.phase == SOPCyclePhase.TRANSIT:
            if target_delta and step.transit_seen:
                step.target_entry_seen = True
                step.set_phase(SOPCyclePhase.TARGET)
                return True, f"A new {label} entered {target}"
            if self._object_motion_detected(step, obs):
                step.transit_seen = True
                step.object_miss_count = 0
                return False, f"Tracking moving {label} to {target}"
            if target_delta and not step.transit_seen:
                return False, f"{label} reached {target}, but transit evidence is still required"
            if not obs.expected_boxes:
                return self._loss_or_restart(step, "object", f"{label} lost before reaching {target}")
            return False, f"Waiting for {label} movement"

        if step.phase == SOPCyclePhase.TARGET:
            if target_delta:
                step.target_entry_seen = True
                return True, f"{label} count in {target} increased from {step.target_baseline_count} to {obs.target_count}"
            return False, f"Waiting for a new {label} in {target}"

        return False, f"Waiting for {label}"

    def _match_free_source_with_hand(
        self, step: SOPStepRuntime, obs: StepObservation
    ) -> tuple[bool, str]:
        label = step.expected_object
        target = step.to_region
        target_delta = obs.target_count > step.target_baseline_count

        if step.phase == SOPCyclePhase.WAITING:
            if not obs.hand_visible:
                return False, "Waiting for hand in visible area"
            if obs.hand_in_target:
                return False, f"Waiting for hand to leave {target} before a new action"
            if step.require_object_at_source:
                if obs.outside_target_count <= 0:
                    return False, f"Waiting for {label} in visible area"
                if not obs.hand_on_object:
                    return False, f"Move hand close to {label}"
                step.hand_grip_state = "gripping"
            elif step.require_object_in_transit and label:
                if not obs.hand_on_object:
                    return False, f"Waiting for hand to carry {label}"
                step.hand_grip_state = "gripping"
                step.transit_seen = True
            step.set_phase(SOPCyclePhase.TRANSIT)
            return False, f"New hand action detected; move to {target}"

        if step.phase == SOPCyclePhase.TRANSIT:
            if not obs.hand_visible:
                return self._loss_or_restart(step, "hand", "Hand lost during transit")
            step.hand_miss_count = 0

            if step.require_object_in_transit and label:
                if obs.hand_on_object or target_delta:
                    step.transit_seen = True
                    step.object_miss_count = 0
                else:
                    return self._loss_or_restart(step, "object", f"Hand is no longer carrying {label}")
            else:
                step.transit_seen = True

            if obs.hand_in_target or target_delta:
                step.target_entry_seen = True
                step.set_phase(SOPCyclePhase.TARGET)
                if not step.require_object_at_target:
                    return True, f"Hand or {label or 'item'} entered {target}"
                return False, f"Hand reached {target}; verifying {label}"
            return False, f"Moving hand to {target}"

        if step.phase == SOPCyclePhase.TARGET:
            if not step.require_object_at_target:
                return True, f"Hand entered {target}"
            if target_delta:
                step.target_entry_seen = True
                step.object_miss_count = 0
                step.set_phase(SOPCyclePhase.RELEASE)
            else:
                return self._loss_or_restart(step, "object", f"Waiting for a new {label} in {target}")

        if step.phase == SOPCyclePhase.RELEASE:
            if not obs.hand_on_object or not obs.hand_in_target:
                step.release_seen = True
                step.hand_grip_state = "released"
                return True, f"{label} placed in {target} and hand released"
            return False, f"Waiting for hand to release {label} or leave {target}"

        return False, "Waiting for hand action"

    def _try_reset_for_next_cycle(
        self, step: SOPStepRuntime, obs: StepObservation
    ) -> tuple[bool, str]:
        if not step.awaiting_cycle_reset:
            return True, ""

        if step.hand_gate_enabled:
            if not step.cycle_reset_armed:
                released = not obs.hand_in_target and (not step.from_region or not obs.hand_in_source)
                if not released:
                    return False, "Waiting for hand to release before the next cycle"
                step.cycle_reset_armed = True
                return False, "Previous hand action released; waiting for next action"

        step.awaiting_cycle_reset = False
        step.cycle_reset_armed = False
        step.reset_cycle_runtime()
        self._initialize_cycle(step, obs)
        step.started_at = time.time()
        return True, f"Cycle {step.matched_count + 1}/{step.target} ready"

    def _confirm_cycle_completed(
        self, step: SOPStepRuntime, reason: str, observation: StepObservation
    ) -> None:
        step.matched_count += 1
        step.stable_count = 0
        if step.matched_count >= step.target:
            self._finish_current_step(reason)
            return

        if step.hand_gate_enabled:
            # A hand-based cycle needs a release edge before another cycle can
            # start. Baselines are recaptured after that release.
            step.awaiting_cycle_reset = True
            step.cycle_reset_armed = False
        else:
            # For object-only cycles, capture the next baseline on the exact
            # completion frame. Waiting until the following frame would miss a
            # fast next pickup when the source still contains several objects.
            step.reset_cycle_runtime()
            self._initialize_cycle(step, observation)
            step.awaiting_cycle_reset = False
            step.cycle_reset_armed = True

        step.last_reason = f"Cycle {step.matched_count}/{step.target} completed; waiting for next cycle"

    def _finish_current_step(self, reason: str) -> None:
        step = self.current_step
        if step is None:
            return
        step.state = SOPStepState.DONE
        step.completed_at = time.time()
        step.last_reason = reason
        step.pick_state = "done"
        step.awaiting_cycle_reset = False
        self.current_index += 1
        next_step = self.current_step
        if next_step is None:
            self._complete_all("All steps completed")
            return
        if self.enable_ready_check:
            next_step.state = SOPStepState.PENDING
            self.state = SOPRunState.IDLE
            self.ready_started_at = time.time()
            self.last_reason = f"Step {step.id} completed; waiting for next step"
        else:
            self._start_step(next_step)

    def _complete_all(self, reason: str) -> None:
        self.state = SOPRunState.COMPLETED
        self.completed_at = time.time()
        self.last_reason = reason

    def _fail_current_step(self, reason: str) -> None:
        step = self.current_step
        if step:
            step.blocked_pick_state = step.pick_state
            step.state = SOPStepState.FAILED
            step.completed_at = time.time()
            step.last_reason = reason
        self.state = SOPRunState.FAILED
        self.completed_at = time.time()
        self.last_reason = reason

    def _recover_current_step(self, reason: str) -> None:
        step = self.current_step
        if step:
            step.state = SOPStepState.ACTIVE
            step.started_at = time.time()
            step.completed_at = None
            step.last_reason = reason
            step.blocked_pick_state = None
            step.awaiting_cycle_reset = False
            step.cycle_reset_armed = False
            step.reset_cycle_runtime()
        self.state = SOPRunState.RUNNING
        self.completed_at = None
        self.last_reason = ""

    def _restart_cycle(self, step: SOPStepRuntime, reason: str) -> tuple[bool, str]:
        step.reset_cycle_runtime()
        step.awaiting_cycle_reset = step.hand_gate_enabled
        step.cycle_reset_armed = not step.hand_gate_enabled
        step.started_at = time.time()
        return False, f"{reason}; restarting current cycle"

    def _loss_or_restart(self, step: SOPStepRuntime, actor: str, reason: str) -> tuple[bool, str]:
        if actor == "hand":
            step.hand_miss_count += 1
            count = step.hand_miss_count
        else:
            step.object_miss_count += 1
            count = step.object_miss_count
        step.miss_count = max(step.object_miss_count, step.hand_miss_count)
        tolerance = step.miss_tolerance
        if count <= tolerance:
            return False, f"{reason} ({count}/{tolerance}); holding phase {step.phase.value}"
        return self._restart_cycle(step, f"{reason} exceeded missTolerance={tolerance}")

    def _object_motion_detected(self, step: SOPStepRuntime, obs: StepObservation) -> bool:
        if not obs.outside_target_centers:
            return False
        if not step.initial_object_centers:
            step.initial_object_centers = list(obs.outside_target_centers)
            return False
        threshold = step.movement_threshold
        for current in obs.outside_target_centers:
            nearest = min(math.dist(current, initial) for initial in step.initial_object_centers)
            if nearest >= threshold:
                return True
        return False

    def _check_timeout(self, step: SOPStepRuntime) -> str:
        if step.timeout <= 0 or step.started_at is None:
            return ""
        if time.time() - step.started_at <= step.timeout:
            return ""
        return f"Step timeout: {step.name} exceeded {step.timeout:g}s"

    def _match_done_when(
        self, rules: list[dict[str, Any]], boxes: list[DetectionBox]
    ) -> tuple[int, str]:
        matched_rules = 0
        reasons: list[str] = []
        valid_rules = [rule for rule in rules if isinstance(rule, dict)]
        for rule in valid_rules:
            label = str(rule.get("label") or rule.get("expectedObject") or "").strip()
            region = str(rule.get("region") or rule.get("toRegion") or "").strip()
            count = max(1, int(rule.get("count", 1) or 1))
            if not label:
                continue
            label_boxes = find_boxes(boxes, label)
            current_count = (
                count_boxes_inside_regions(label_boxes, find_boxes(boxes, region))
                if region
                else len(label_boxes)
            )
            if current_count >= count:
                matched_rules += 1
            reasons.append(f"{label}:{current_count}/{count}")
        return matched_rules, "; ".join(reasons) or "Waiting for doneWhen"

    def _match_ng_when(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> tuple[bool, str]:
        for rule in step.ng_when:
            if not isinstance(rule, dict):
                continue
            matched, reason = self._match_rule(rule, boxes)
            if matched:
                return True, f"NG: {str(rule.get('message') or reason or 'NG rule matched')}"
        return False, ""

    def _match_default_wrong_object(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> str:
        if not step.expected_object or not step.to_region:
            return ""
        regions = find_boxes(boxes, step.to_region)
        if not regions:
            return ""
        for label in self._future_expected_objects():
            if count_boxes_inside_regions(find_boxes(boxes, label), regions) > 0:
                return f"NG: Expected {step.expected_object}, but {label} entered {step.to_region}"
        return ""

    def _match_rule(self, rule: dict[str, Any], boxes: list[DetectionBox]) -> tuple[bool, str]:
        rule_type = str(rule.get("type", "object_detected")).strip()
        label = str(rule.get("label") or rule.get("object") or rule.get("expectedObject") or "").strip()
        region = str(rule.get("region") or rule.get("toRegion") or "").strip()
        count = max(1, int(rule.get("count", 1) or 1))
        if rule_type in {"object_in_region", "wrong_object_in_region"}:
            if not label or not region:
                return False, "Invalid object_in_region rule"
            actual = count_boxes_inside_regions(find_boxes(boxes, label), find_boxes(boxes, region))
            return actual >= count, f"{label} in {region}: {actual}/{count}"
        if rule_type == "object_missing":
            actual = len(find_boxes(boxes, label)) if label else 0
            return bool(label) and actual < count, f"{label} missing: {actual}/{count}"
        actual = len(find_boxes(boxes, label)) if label else 0
        return bool(label) and actual >= count, f"{label}: {actual}/{count}"

    def _future_expected_objects(self) -> set[str]:
        return {
            label
            for label in self.expected_objects_by_step[self.current_index + 1 :]
            if label
        }

    def _hand_action_points(
        self,
        step: SOPStepRuntime,
        hands: dict[str, list[tuple[float, float]]] | None,
    ) -> list[tuple[float, float]]:
        if not hands or not step.hand_gate_enabled:
            return []
        points: list[tuple[float, float]] = []
        for side, indices in step.hand_points_config.items():
            landmarks = hands.get(side)
            if not landmarks:
                continue
            selected = [landmarks[index] for index in indices if 0 <= index < len(landmarks)]
            if not selected:
                continue
            points.append(
                (
                    sum(point[0] for point in selected) / len(selected),
                    sum(point[1] for point in selected) / len(selected),
                )
            )
        return points

    @staticmethod
    def _points_engage_boxes(
        points: list[tuple[float, float]], boxes: list[DetectionBox], margin: float = 0.0
    ) -> bool:
        return bool(points and boxes) and any(
            point_in_box(point, box, margin=margin) for point in points for box in boxes
        )

    @staticmethod
    def _hand_margin(step: SOPStepRuntime) -> float:
        value = _to_float(step.context.get("handMargin", 30))
        return max(0.0, value)

    @staticmethod
    def _normalize_confidence(config_confidence: Any, min_score: float | None) -> float:
        if min_score is not None:
            return float(min_score)
        value = _to_float(config_confidence)
        return value / 100.0 if value > 1 else value

    def _resolve_default_timeout(self, fallback_timeout: float) -> float:
        configured = self.sop_config.get(
            "defaultStepTimeout",
            self.sop_config.get("stepTimeout", self.sop_config.get("timeout", fallback_timeout)),
        )
        timeout = _to_float(configured)
        return timeout if timeout > 0 else 0.0


def select_enabled_sop_config(sop_map: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(sop_map, dict):
        return {}
    if isinstance(sop_map.get("steps"), list):
        return sop_map
    for value in sop_map.values():
        if isinstance(value, dict) and value.get("enabled") is True:
            return value
    return {}


def normalize_detections(
    detections: list[dict[str, Any]] | dict[str, Any] | None,
    min_score: float = 0.0,
) -> list[DetectionBox]:
    if detections is None:
        return []
    if isinstance(detections, dict):
        raw_items = detections.get("detections") or detections.get("datas") or []
    else:
        raw_items = detections
    boxes: list[DetectionBox] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        score = _to_float(item.get("score", 0.0))
        if score < min_score:
            continue
        points = item.get("points") or item.get("bbox") or []
        label = str(item.get("label", "")).strip()
        if label and points:
            boxes.append(
                DetectionBox(
                    label=label,
                    points=points,
                    score=score,
                    class_id=item.get("class_id"),
                )
            )
    return boxes


def find_boxes(boxes: list[DetectionBox], label: str) -> list[DetectionBox]:
    expected = label.strip().lower()
    return [box for box in boxes if box.label.strip().lower() == expected]


def count_boxes_inside_regions(targets: list[DetectionBox], regions: list[DetectionBox]) -> int:
    return sum(
        1
        for target in targets
        if target.center is not None and point_in_any_region(target.center, regions)
    )


def count_boxes_outside_regions(targets: list[DetectionBox], regions: list[DetectionBox]) -> int:
    if not regions:
        return len(targets)
    return sum(
        1
        for target in targets
        if target.center is not None and not point_in_any_region(target.center, regions)
    )


def point_in_any_region(point: tuple[float, float], regions: list[DetectionBox]) -> bool:
    return any(point_in_box(point, region) for region in regions)


def point_in_box(
    point: tuple[float, float], box: DetectionBox, margin: float = 0.0
) -> bool:
    xyxy = box.xyxy
    if xyxy is None:
        return False
    x1, y1, x2, y2 = xyxy
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    x, y = point
    return left - margin <= x <= right + margin and top - margin <= y <= bottom + margin


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
