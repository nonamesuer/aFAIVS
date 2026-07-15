import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


DEFAULT_STEP_TIMEOUT_SECONDS = 30.0
DEFAULT_MISS_TOLERANCE = 5  # 目标检测框连续丢失多少帧才判定为真的丢失/放回（缓解偶发漏检抖动）

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
class SOPStepRuntime:
    id: int
    name: str
    type: str = "vision"
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
    pick_state: str = "idle"  # idle, in_source, picked, in_target, done
    hand_grip_state: str = "released"  # released, gripping —— 记录抓取瞬间手是否在物体上
    miss_count: int = 0  # 目标检测框连续丢失的帧数计数（用于容忍偶发漏检）

    blocked_pick_state: str | None = None # 进入 FAILED 时记录当时的动作阶段，用于判断阻塞后是否产生了新的正向操作进展。
    awaiting_cycle_reset: bool = False # 当前一轮动作已经计数完成，# 正在等待下一轮操作的起始条件重新成立。

    @classmethod
    def from_config(cls, data: dict[str, Any]) -> "SOPStepRuntime":
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            type=str(data.get("type", "vision")),
            hint=str(data.get("hint", "")),
            target=max(1, int(data.get("target", 1) or 1)),
            timeout=_to_float(data.get("timeout", data.get("timeoutSeconds", 0))),
            context=data.get("context", {}) if isinstance(data.get("context"), dict) else {},
            done_when=data.get("doneWhen", []) if isinstance(data.get("doneWhen"), list) else [],
            ng_when=data.get("ngWhen", []) if isinstance(data.get("ngWhen"), list) else [],
        )


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
            "pick_state": self.pick_state,
            "miss_count": self.miss_count,
            "blocked_pick_state": self.blocked_pick_state,
            "awaiting_cycle_reset": self.awaiting_cycle_reset,
        }
    def validate_config(self) -> tuple[bool, str]:
        expected_label = self.expected_object
        object_detection = self.object_detection_config
        from_region = str(self.context.get("fromRegion", "")).strip()
        to_region = str(self.context.get("toRegion", "")).strip()
        effective_object_detection = object_detection
        # 任何阶段要求检测 expectedObject，
        # 就必须配置 expectedObject
        if any(effective_object_detection.values()) and not expected_label:
            return False, f"Step {self.id}: expectedObject is required because object detection is enabled"
        # 如果三个阶段都不检测物料，
        # 则必须配置手部
        if not any(effective_object_detection.values()) and not self.hand_gate_enabled:
            return False, f"Step {self.id}: either object detection or hand tracking is required"
        # toRegion 是搬运步骤的最终判定区域，必须配置。
        # fromRegion 允许为空；为空时从整个画面寻找 expectedObject。
        # 来源区和目标区都没有，搬运步骤没有意义
        if not to_region:
            return False, f"Step {self.id}: toRegion is required"
        if not from_region:
            if not expected_label:
                return False, f"Step {self.id}: expectedObject is required when fromRegion is empty"
            if not self.require_object_at_target:
                return False, f"Step {self.id}: target object detection is required when fromRegion is empty"
        return True, ""
    @property
    def elapsed(self) -> float:
        if not self.started_at:
            return 0.0
        end_time = self.completed_at or self.paused_at or time.time()
        return round(max(0.0, end_time - self.started_at), 2)
    
    @property
    def hand_points_config(self) -> dict[str, list[int]]:
        """
        获取当前步骤实际启用的手部关键点配置。
        handPoints 同时表达：
        1. 哪只手参与检测；
        2. 该手使用哪些关键点。
        示例：
        {
            "l": [],
            "r": [4, 8, 12]
        }
        表示仅启用右手，并使用 4、8、12 号关键点。
        """
        raw = self.context.get("handPoints") or {}
        if not isinstance(raw, dict):return {}
        result: dict[str, list[int]] = {}
        # 当前系统只支持左右手，避免错误字段进入状态机
        for side in ("l", "r"):
            indices = raw.get(side,[])
            if not isinstance(indices, list):continue
            # 只保留合法的 MediaPipe Hand Landmark 索引 0~20,同时去重并排序
            valid_indices = sorted({int(i) for i in indices if isinstance(i, (int, float)) and 0 <= int(i) <= 20})
            if valid_indices:result[side] = valid_indices
        return result
    @property
    def hand_gate_enabled(self) -> bool:
        """本步骤是否需要手部动作参与验证。"""
        return bool(self.hand_points_config)
    @property
    def expected_object(self) -> str:
        return str(self.context.get("expectedObject", "")).strip()


    @property
    def object_detection_config(self) -> dict[str, bool]:
        """获取 expectedObject 在不同阶段是否必须参与检测。

        新配置：
        {
            "objectDetection": {
                "source": true,
                "transit": false,
                "target": true
            }
        }

        兼容旧配置 expectedObjectRequire：
        true  -> source/transit/target 全部 true
        false -> source/transit/target 全部 false
        """
        raw = self.context.get("objectDetection")

        if isinstance(raw, dict):
            return {
                "source": bool(raw.get("source", True)),
                "transit": bool(raw.get("transit", False)),
                "target": bool(raw.get("target", True)),
            }

        # 兼容旧版配置
        legacy_required = bool(
            self.context.get(
                "expectedObjectRequire",
                True,
            )
        )

        return {
            "source": legacy_required,
            "transit": legacy_required,
            "target": legacy_required,
        }


    @property
    def require_object_at_source(self) -> bool:
        return self.object_detection_config["source"]


    @property
    def require_object_in_transit(self) -> bool:
        return self.object_detection_config["transit"]


    @property
    def require_object_at_target(self) -> bool:
        return self.object_detection_config["target"]


class SOPStateMachine:
    """SOP 视觉步骤状态机。"""
    _PICK_STATE_ORDER = {
        "idle": 0,
        "in_source": 1,
        "picked": 2,
        "in_target": 3,
        "done": 4,
    }

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
        
        # 准备检查相关
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
        enabled_config = select_enabled_sop_config(sop_map)
        return cls(
            enabled_config,
            stable_frames=stable_frames,
            min_score=min_score,
            default_step_timeout=default_step_timeout,
            enable_ready_check=enable_ready_check,
            ready_check_timeout=ready_check_timeout,
        )

    def start(self) -> None:
        """启动SOP状态机"""
        if not self.steps:
            self.state = SOPRunState.FAILED
            self.last_reason = "SOP steps is empty"
            return

        # 重置所有步骤
        for index, step in enumerate(self.steps):
            valid, reason = step.validate_config()
            if not valid:
                self.state = SOPRunState.FAILED
                self.last_reason = reason
                return
            step.state = SOPStepState.PENDING
            step.matched_count = 0
            step.stable_count = 0
            step.started_at = None
            step.completed_at = None
            step.last_reason = ""
            step.pick_state = "idle"
            step.hand_grip_state = "released"
            step.miss_count = 0
            step.blocked_pick_state = None
            step.awaiting_cycle_reset = False

        self.current_index = 0
        self.started_at = time.time()
        self.completed_at = None
        self.last_reason = ""
        self.paused_at = None
        self.state_before_pause = None
        self.ready_started_at = time.time()

        # 如果启用准备检查，保持IDLE状态等待准备就绪
        if self.enable_ready_check:
            self.state = SOPRunState.IDLE
            self.last_reason = "Waiting for all required objects to be ready"
        else:
            # 直接开始第一个步骤
            self.state = SOPRunState.RUNNING
            first_step = self.current_step
            if first_step:
                first_step.state = SOPStepState.ACTIVE
                first_step.started_at = time.time()
                self.last_reason = "Started"

    def pause(self) -> bool:
        """暂停 SOP。

        暂停后：
        1. 保留 current_index
        2. 保留 pick_state
        3. 保留 stable_count
        4. 保留 matched_count
        5. 暂停时间不计入步骤 timeout
        6. 暂停时间不计入 ready-check timeout
        """
        if self.state in {SOPRunState.PAUSED,SOPRunState.COMPLETED,}:return False

        self.state_before_pause = self.state
        self.paused_at = time.time()

        step = self.current_step
        if step is not None and step.started_at is not None:
            step.paused_at = self.paused_at

        self.state = SOPRunState.PAUSED
        self.last_reason = "SOP paused"

        return True


    def resume(self) -> bool:
        """从暂停位置继续 SOP。"""
        if self.state != SOPRunState.PAUSED:return False
        now = time.time()
        if self.paused_at is not None:
            paused_duration = max(0.0, now - self.paused_at)

            # -------------------------------------------------
            # 修正当前步骤的开始时间
            # 例如：
            # started_at = 10:00:00
            # 10:00:10 暂停
            # 10:01:10 继续
            #
            # started_at 向后移动 60 秒
            # 因此暂停的 60 秒不会进入 elapsed / timeout
            # -------------------------------------------------
            step = self.current_step
            if step is not None:
                if step.started_at is not None:
                    step.started_at += paused_duration
                step.paused_at = None
            # -------------------------------------------------
            # 如果之前处于 ready-check，
            # ready-check 的超时时间同样需要补偿
            # -------------------------------------------------
            if self.ready_started_at is not None:
                self.ready_started_at += paused_duration
            # 整个 SOP 的运行时间也排除暂停时间
            if self.started_at is not None:
                self.started_at += paused_duration
        restore_state = self.state_before_pause
        # 正常情况下恢复暂停前的状态
        if restore_state in {SOPRunState.IDLE,SOPRunState.RUNNING,SOPRunState.FAILED,}:
            self.state = restore_state
        else:
            self.state = SOPRunState.RUNNING
        self.paused_at = None
        self.state_before_pause = None
        self.last_reason = "SOP resumed"

        return True

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
            step.stable_count = 0
            step.started_at = None
            step.completed_at = None
            step.paused_at = None
            step.last_reason = ""
            step.pick_state = "idle"  # 重置状态
            step.hand_grip_state = "released"
            step.miss_count = 0

    def update(
            self,
            detections: list[dict[str, Any]] | dict[str, Any] | None,
            hands: dict[str, list[tuple[float, float]]] | None = None,
        ) -> dict[str, Any]:
        """更新状态机，处理每一帧的检测结果
        hands: {"l": [(x,y)*21], "r": [(x,y)*21]}，来自 HandTracker.detect()，
        没有配置手部识别的步骤可以传 None。
        """
        # 如果是IDLE状态且启用了准备检查
        if self.state == SOPRunState.IDLE and self.enable_ready_check:
            return self._handle_ready_check(detections)
        
        # 如果未启用准备检查，但状态是IDLE，则自动启动
        if self.state == SOPRunState.IDLE and not self.enable_ready_check:
            self.start()
            # 重新调用update，但现在应该是RUNNING状态
            if self.state == SOPRunState.RUNNING:
                return self.update(detections,hands)
            return self.snapshot(matched=False, reason=self.last_reason)

        # 如果已暂停或已完成，返回当前快照
        if self.state in {SOPRunState.PAUSED, SOPRunState.COMPLETED}:
            return self.snapshot(matched=False, reason=self.last_reason)

        # 获取当前步骤
        step = self.current_step
        if step is None:
            self._complete_all("All steps completed")
            return self.snapshot(matched=False, reason=self.last_reason)

        # 标准化检测结果
        boxes = normalize_detections(detections, min_score=self.confidence)
        if self.state == SOPRunState.FAILED:
            # ==================================================
            # FAILED 状态下仍然继续视觉检测
            #
            # self.last_reason:
            #     原始阻塞原因
            #
            # step.last_reason:
            #     当前实时操作状态
            # ==================================================
            # 自定义 NG 条件仍然存在
            ng_matched, ng_reason = self._match_ng_when(step, boxes)
            if ng_matched:
                step.last_reason = ng_reason
                return self.snapshot(matched=False, reason=self.last_reason)
            # 默认错误物料仍然存在
            default_ng_reason = self._match_default_wrong_object(step, boxes)
            if default_ng_reason:return self.snapshot(matched=False, reason=self.last_reason)
            # --------------------------------------------------
            # 如果之前已经完成过一轮，
            # 当前正在等待下一轮开始条件。
            # --------------------------------------------------
            if step.awaiting_cycle_reset:
                cycle_ready, live_reason = self._try_reset_for_next_cycle(step, boxes, hands)
                step.last_reason = live_reason
                if not cycle_ready:return self.snapshot(matched=False, reason=self.last_reason)
            # --------------------------------------------------
            # 继续执行当前动作链
            # --------------------------------------------------
            completed_once, live_reason = self._match_step(step, boxes, hands)
            step.last_reason = live_reason
            # --------------------------------------------------
            # 判断是否产生新的有效正向进展
            # target 不参与解除阻塞。
            # --------------------------------------------------
            can_recover = self._can_recover_current_step(step,completed_once)
            if not can_recover:return self.snapshot(matched=False, reason=self.last_reason)
             # --------------------------------------------------
            # 解除阻塞
            # --------------------------------------------------
            self._recover_current_step(live_reason)
            # --------------------------------------------------
            # 当前这一帧可能已经满足“一轮完成”
            # --------------------------------------------------
            if completed_once:
                step.stable_count += 1
                if step.stable_count >= self.stable_frames:
                    self._confirm_cycle_completed(step, live_reason)
            return self.snapshot(matched=completed_once, reason=live_reason)
        # 检查超时
        timeout_reason = self._check_timeout(step)
        if timeout_reason:
            self._fail_current_step(timeout_reason)
            return self.snapshot(matched=False, reason=timeout_reason)

        # 检查NG条件
        ng_matched, ng_reason = self._match_ng_when(step, boxes)
        if ng_matched:
            self._fail_current_step(ng_reason)
            return self.snapshot(matched=False, reason=ng_reason)

        # 检查默认错误对象
        default_ng_reason = self._match_default_wrong_object(step, boxes)
        if default_ng_reason:
            self._fail_current_step(default_ng_reason)
            return self.snapshot(matched=False, reason=default_ng_reason)
        # ==================================================
        # 如果上一轮已经完成，先等待下一轮起始条件重新成立
        # ==================================================
        if step.awaiting_cycle_reset:
            cycle_ready, cycle_reason = (self._try_reset_for_next_cycle(step,boxes,hands))
            step.last_reason = cycle_reason
            if not cycle_ready:return self.snapshot(matched=False,reason=cycle_reason)
        # ==================================================
        # 执行当前一轮动作判断
        # ==================================================
        completed_once, reason = self._match_step(step,boxes,hands)
        step.last_reason = reason

        # ==================================================
        # 当前这一轮完成条件连续稳定成立
        # ==================================================
        if completed_once:
            step.stable_count += 1
            if step.stable_count >= self.stable_frames:
                self._confirm_cycle_completed(step,reason)
        else:
            step.stable_count = 0
        return self.snapshot(matched=completed_once,reason=reason )

        # return self.snapshot(matched=matched, reason=reason)

    def _handle_ready_check(self, detections: list[dict[str, Any]] | dict[str, Any] | None) -> dict[str, Any]:
        """处理准备检查状态"""
        step = self.current_step
        if step is None:
            self._complete_all("All steps completed")
            return self.snapshot(matched=False, reason=self.last_reason)

        # 标准化检测结果
        boxes = normalize_detections(detections, min_score=self.confidence)

        # 检查当前步骤所需的所有标签是否都准备好
        ready, missing_labels, reason = self._check_step_ready(step, boxes)
        
        if not ready:
            # 检查准备超时
            if self.ready_started_at and (time.time() - self.ready_started_at) > self.ready_check_timeout:
                self._fail_current_step(f"Ready check timeout: {reason}")
                return self.snapshot(matched=False, reason=self.last_reason)
            return self.snapshot(matched=False,reason=f"Waiting for: {', '.join(missing_labels)}")

        # 所有对象都准备好了，真正开始步骤
        self._start_step(step)
        return self.snapshot(matched=False, reason="All required objects ready, starting step")

    def _check_step_ready(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> tuple[bool, list[str], str]:
        """检查步骤所需的所有标签是否都准备好
        
        Returns:
            tuple[bool, list[str], str]: (是否准备好, 缺失的标签列表, 详细原因)
        """
        required_labels = self._get_required_labels(step)
        if not required_labels:
            # 如果没有必需标签，认为准备好了
            return True, [], "No required labels"

        # 获取所有已检测到的标签（去重）
        detected_labels = {box.label.strip().lower() for box in boxes}
        
        # 找出缺失的标签
        missing_labels = []
        for label in required_labels:
            label_lower = label.strip().lower()
            if label_lower not in detected_labels:
                missing_labels.append(label)
        
        if missing_labels:
            return False, missing_labels, f"Missing labels: {', '.join(missing_labels)}"
        
        return True, [], "All required labels detected"

    def _get_required_labels(self, step: SOPStepRuntime) -> set[str]:
        """获取步骤所需的所有标签"""
        labels = set()
        from_region = str(step.context.get("fromRegion", "")).strip()
        to_region = str(step.context.get("toRegion", "")).strip()
        expected_label = step.expected_object
        if from_region:labels.add(from_region)
        if to_region:labels.add(to_region)
        # 只有来源阶段要求检测 expectedObject，
        # 才应该在 ready check 阶段等待它。
        if expected_label and (from_region and step.require_object_at_source) or not from_region:
            labels.add(expected_label)
        # doneWhen 如果明确要求某个静态区域存在，
        # 可以保留区域标签。
        for rule in step.done_when:
            if not isinstance(rule, dict):continue
            region = str(rule.get("region") or rule.get("toRegion") or "").strip()
            if region:labels.add(region)
        # 不再从 ngWhen 收集 object label。
        # NG对象“不出现”才是正常情况，
        # 不能把错误对象作为 ready-check 必需项。
        return labels

    def _start_step(self, step: SOPStepRuntime) -> None:
        """真正开始一个步骤"""
        step.state = SOPStepState.ACTIVE
        step.started_at = time.time()
        step.stable_count = 0
        step.completed_at = None
        step.matched_count = 0
        step.miss_count = 0
        step.last_reason = "Step started"
        
        # 如果整体状态还是IDLE，现在改为RUNNING
        if self.state == SOPRunState.IDLE:
            self.state = SOPRunState.RUNNING
            self.started_at = time.time()
            self.last_reason = "SOP started"
    @property
    def requires_hand_tracking(self) -> bool:
        """整个SOP是否存在需要手部识别的步骤（用于决定要不要开启MediaPipe）。"""
        return any(step.hand_gate_enabled for step in self.steps)
    @property
    def current_step(self) -> SOPStepRuntime | None:
        if 0 <= self.current_index < len(self.steps):
            return self.steps[self.current_index]
        return None
    @property
    def max_required_hands(self) -> int:
        """整个SOP里，需要手部识别的步骤中最多同时用到几只手（用于决定HandLandmarker的num_hands）。"""
        counts = [len(step.hand_points_config) for step in self.steps if step.hand_gate_enabled]
        return max(counts) if counts else 0
    def snapshot(self, matched: bool = False, reason: str = "") -> dict[str, Any]:
        """生成当前状态快照"""
        done_count = sum(1 for step in self.steps if step.state == SOPStepState.DONE)
        current_step = self.current_step.to_dict() if self.current_step else None
        return {
            "state": self.state.value,
            "current_step": current_step,
            "steps": [step.to_dict() for step in self.steps],
            "progress": {
                "done": done_count, 
                "total": len(self.steps), 
                "current_index": self.current_index
            },
            "matched": matched,
            "reason": reason,
            "updated_at": time.time(),
        }
    def _hand_action_points(self, step: SOPStepRuntime, hands: dict[str, list[tuple[float, float]]] | None) -> list[tuple[float, float]]:
        """取出本步骤所需手（可能多只）在配置关键点上的"动作点"（多个关键点的几何中心）。"""
        if not hands or not step.hand_gate_enabled:return []
        points: list[tuple[float, float]] = []
        hand_points_config = step.hand_points_config
        for side, indices in hand_points_config.items():
            landmarks = hands.get(side)
            if not landmarks:continue
            selected = [landmarks[i] for i in indices if 0 <= i < len(landmarks)]
            if not selected:continue
            cx = sum(p[0] for p in selected) / len(selected)
            cy = sum(p[1] for p in selected) / len(selected)
            points.append((cx, cy))
        return points
    @staticmethod
    def _points_engage_boxes(points: list[tuple[float, float]], boxes: list[DetectionBox], margin: float = 0.0) -> bool:
        """判断给定的点集中，是否有任意一点落在给定的任意一个框内。"""
        if not points or not boxes:
            return False
        return any(point_in_box(point, box, margin=margin) for point in points for box in boxes)

    @staticmethod
    def _object_in_regions(expected_boxes: list[DetectionBox],region_boxes: list[DetectionBox],) -> bool:
        if not expected_boxes or not region_boxes:return False
        return (count_boxes_inside_regions(expected_boxes,region_boxes,) > 0)
    def current_hand_action_points(self, hands: dict[str, list[tuple[float, float]]] | None) -> list[tuple[float, float]]:
        """获取当前步骤配置的手，此刻的动作点坐标，仅用于调试可视化。"""
        step = self.current_step
        if step is None:
            return []
        return self._hand_action_points(step, hands)
    def _finish_current_step(self, reason: str) -> None:
        """完成当前步骤"""
        step = self.current_step
        if step is None:
            return
        
        step.state = SOPStepState.DONE
        step.completed_at = time.time()
        step.last_reason = reason
        step.pick_state = "idle"  # 重置状态
        step.miss_count = 0
        step.blocked_pick_state = None
        step.awaiting_cycle_reset = False
        self.current_index += 1

        # 检查是否有下一个步骤
        next_step = self.current_step
        if next_step is None:
            self._complete_all("All steps completed")
            return

        # 启动下一个步骤
        if self.enable_ready_check:
            # 如果启用准备检查，下一个步骤需要等待准备就绪
            next_step.state = SOPStepState.PENDING
            self.state = SOPRunState.IDLE
            self.ready_started_at = time.time()
            self.last_reason = f"Step {step.id} completed, waiting for next step ready"
        else:
            # 直接激活下一个步骤
            next_step.state = SOPStepState.ACTIVE
            next_step.started_at = time.time()
            next_step.stable_count = 0
            self.last_reason = f"Step {step.id} completed, starting step {next_step.id}"

    def _complete_all(self, reason: str) -> None:
        """完成所有步骤"""
        self.state = SOPRunState.COMPLETED
        self.completed_at = time.time()
        self.last_reason = reason

    def _fail_current_step(self, reason: str) -> None:
        """使当前步骤进入阻塞状态，但保留当前动作进度。"""
        step = self.current_step
        if step is not None:
            # 保存进入阻塞时的动作阶段。
            step.blocked_pick_state = step.pick_state
            step.state = SOPStepState.FAILED
            step.completed_at = time.time()
            step.last_reason = reason
            # 不重置 pick_state。
            # FAILED 状态下仍然继续当前视觉动作链。
            # step.pick_state = "idle"  # 重置状态
            step.miss_count = 0
        self.state = SOPRunState.FAILED
        self.completed_at = time.time()
        self.last_reason = reason

    def _recover_current_step(self, reason: str) -> None:
        """恢复当前步骤（从失败中恢复）"""
        step = self.current_step
        if step is not None:
            step.state = SOPStepState.ACTIVE
            step.started_at = time.time()
            step.completed_at = None
            step.last_reason = reason
            step.stable_count = 0
            step.miss_count = 0
            step.blocked_pick_state = None
        self.state = SOPRunState.RUNNING
        self.completed_at = None
        self.last_reason = ""
    def _can_recover_current_step(self,step: SOPStepRuntime,completed_once: bool,) -> bool:
        """
        判断阻塞后的操作是否已经产生有效正向进展。
        target 不参与解除阻塞判断。
        """
        # 当前这一轮已经完成，本身就是明确的正向进展。
        if completed_once:return True
        blocked_state = step.blocked_pick_state or "idle"
        current_state = step.pick_state or "idle"
        blocked_order = self._PICK_STATE_ORDER.get(blocked_state,0)
        current_order = self._PICK_STATE_ORDER.get(current_state,0)
        return current_order > blocked_order
    def _confirm_cycle_completed(self,step: SOPStepRuntime,reason: str) -> None:
        """
        确认当前一轮操作已经稳定完成。
        target 表示需要完成多少轮有效操作。
        """
        step.matched_count += 1
        step.stable_count = 0
        # 已经达到目标次数，完成整个步骤。
        if step.matched_count >= step.target:
            self._finish_current_step(reason)
            return
        # 尚未达到 target，等待下一轮操作重新开始。
        step.awaiting_cycle_reset = True
        step.pick_state = "idle"
        step.hand_grip_state = "released"
        step.miss_count = 0
        step.last_reason = (
            f"Cycle {step.matched_count}/{step.target} completed, "
            f"waiting for next cycle"
        )
    def _try_reset_for_next_cycle(self,step: SOPStepRuntime,boxes: list[DetectionBox],hands: dict[str, list[tuple[float, float]]] | None, ) -> tuple[bool, str]:
        """
        判断当前场景是否已经具备开始下一轮操作的条件。
        """
        if not step.awaiting_cycle_reset:return True, ""
        expected_label = step.expected_object
        from_region = str(step.context.get("fromRegion", "")).strip()
        target_region = str(step.context.get("toRegion", "")).strip()
        hand_margin = float(step.context.get("handMargin", 30))
        hand_points = self._hand_action_points(step,hands )
        # ==================================================
        # 有来源区域
        # ==================================================
        if from_region:
            from_region_boxes = find_boxes(boxes,from_region,)
            # 来源阶段检测物料：
            # 等待下一份物料重新出现在来源区域。
            if step.require_object_at_source and expected_label:
                expected_boxes = find_boxes(boxes,expected_label)
                object_in_source = self._object_in_regions(expected_boxes,from_region_boxes)
                if not object_in_source:return False,f"Waiting for next {expected_label} in {from_region}",
            # 来源阶段不检测物料：
            # 使用手部重新进入来源区域作为下一轮开始条件。
            else:
                hand_in_source = self._points_engage_boxes(hand_points,from_region_boxes,hand_margin)
                if not hand_in_source:return False,f"Waiting for hand to return to {from_region}"
            step.awaiting_cycle_reset = False
            step.pick_state = "idle"
            step.started_at = time.time()
            return True, "Next cycle ready"
        # ==================================================
        # 没有来源区域
        #
        # 当前配置规则下，这种情况依赖 expectedObject。
        # 已经放入目标区域的旧物料不能再次触发新一轮。
        # 必须存在目标区域之外的新 expectedObject。
        # ==================================================
        if expected_label:
            expected_boxes = find_boxes(boxes,expected_label)
            target_region_boxes = find_boxes(boxes,target_region)
            target_count = count_boxes_inside_regions(expected_boxes,target_region_boxes)
            outside_target_count = (len(expected_boxes) - target_count)
            if outside_target_count <= 0:return False,f"Waiting for next {expected_label} in visible area"
            step.awaiting_cycle_reset = False
            step.pick_state = "idle"
            step.started_at = time.time()
            return True, "Next cycle ready"
        # 理论上无 fromRegion 且无 expectedObject
        # 当前配置不应该进入这里。
        return False, "Waiting for next cycle"
    def _check_timeout(self, step: SOPStepRuntime) -> str:
        """检查步骤是否超时"""
        if step.timeout <= 0 or not step.started_at:
            return ""
        elapsed = time.time() - step.started_at
        if elapsed <= step.timeout:
            return ""
        return f"Step timeout: {step.name} exceeded {step.timeout:g}s"
    def _handle_missing_expected_object(self, step: SOPStepRuntime, expected_label: str) -> tuple[bool, str]:
        """目标物体本帧未检测到时的处理。

        只有连续丢失超过 missTolerance 帧（默认 DEFAULT_MISS_TOLERANCE），
        才认为物体真的离开/丢失，进而重置 picked/in_target 的搬运状态；
        单帧的漏检只做"保持当前进度"处理，避免偶发漏检导致误判为"物体放回了 from 区域"。
        可以在该步骤的 context 里配置 missTolerance 覆盖默认值，例如：
        "context": {..., "missTolerance": 8}
        """
        tolerance = max(0, int(step.context.get("missTolerance", DEFAULT_MISS_TOLERANCE)))
        if step.pick_state in ("picked", "in_target"):
            if step.miss_count < tolerance:
                step.miss_count += 1
                return False, f"{expected_label} briefly lost ({step.miss_count}/{tolerance}), holding state"
            # 超过容忍帧数，才真正判定为丢失/放回
            step.pick_state = "idle"
            step.hand_grip_state = "released"
            step.miss_count = 0
            return False, f"Waiting for {expected_label}"
        # 非搬运中状态（idle / in_source），丢失目标框不需要特殊容忍逻辑
        step.miss_count = 0
        return False, f"Waiting for {expected_label}"
    
    def _match_step(self, step: SOPStepRuntime, boxes: list[DetectionBox],hands: dict[str, list[tuple[float, float]]] | None = None,) -> tuple[bool, str]:
        """匹配当前步骤的条件"""
        if step.done_when:
            matched_count, reason = self._match_done_when(step.done_when,boxes)
            completed = matched_count >= len(step.done_when)
            return completed, reason
        expected_label = step.expected_object
        from_region = str(step.context.get("fromRegion", "")).strip()
        target_region = str(step.context.get("toRegion", "")).strip()
        hand_margin = float(step.context.get("handMargin", 30))
        expected_boxes = find_boxes(boxes, expected_label) if expected_label else []
        from_region_boxes = find_boxes(boxes, from_region) if from_region else []
        target_region_boxes = find_boxes(boxes, target_region) if target_region else []
        hand_points = self._hand_action_points(step, hands)
        object_in_source = self._object_in_regions(expected_boxes,from_region_boxes,)
        object_in_target = self._object_in_regions(expected_boxes,target_region_boxes,)
        hand_in_source = self._points_engage_boxes( hand_points, from_region_boxes, hand_margin)
        hand_in_target = self._points_engage_boxes(hand_points, target_region_boxes, hand_margin)
        hand_on_object = self._points_engage_boxes(hand_points, expected_boxes, margin=hand_margin)
        # fromRegion 可选。没有来源区时，从整个画面内寻找并跟踪
        # expectedObject，不依赖固定来源区域。
        if not from_region:
            return self._match_no_source_step(
                step=step,
                expected_label=expected_label,
                expected_boxes=expected_boxes,
                target_region=target_region,
                target_region_boxes=target_region_boxes,
                object_in_target=object_in_target,
                hand_on_object=hand_on_object,
            )
        # ==================================================
        # idle
        # 等待步骤的“来源条件”成立
        # ==================================================
        if step.pick_state == "idle":
            # 来源阶段要求检测物料
            if step.require_object_at_source:
                if not expected_boxes:return False, f"Waiting for {expected_label}"
                if not object_in_source:return False, f"Waiting for {expected_label} in {from_region}"
                step.pick_state = "in_source"
                return False, f"{expected_label} ready in {from_region}, waiting to pick"
            # 来源阶段不要求检测物料，但要求手部识别
            if not step.hand_gate_enabled:return False,"Source object detection disabled but hand tracking is not configured"
            if not hand_in_source:return False, f"Waiting for hand in {from_region}"
            step.pick_state = "in_source"
            return False, f"Hand ready in {from_region}, waiting to pick"
        # ==================================================
        # in_source
        # 等待真正拿起
        # ==================================================
        if step.pick_state == "in_source":
            #来源阶段可以看到目标物体
            if step.require_object_at_source:
                #物料任在来源区域
                if object_in_source:
                    # 有手部时可以记录“手已经接触目标”
                    if step.hand_gate_enabled and hand_on_object:
                        step.hand_grip_state = "gripping"
                    return False, f"Pick {expected_label} from {from_region}"
                # 物料不再位于来源区
                #
                # 如果有手部配置：
                # 允许使用之前已经记录的 gripping，
                # 解决真正抓起时目标被手遮挡的问题。
                if step.hand_gate_enabled:
                    if step.hand_grip_state != "gripping":return False, f"{expected_label} left {from_region} without confirmed hand engagement"
                step.pick_state = "picked"
                step.started_at = time.time()  # 重置计时器，开始计算搬运时间
                return False, f"{expected_label} picked, moving to {target_region}"
            # 来源阶段看不到 expectedObject,只能使用手的位置   
            if hand_in_source:return False, f"Hand remains in {from_region}"
            if not hand_points:return False, f"Waiting for hand in {from_region}"
            step.pick_state = "picked"
            step.hand_grip_state = "gripping"
            step.started_at = time.time()  # 重置计时器，开始计算搬运时间
            return False, f"Hand left {from_region}, moving to {target_region}"
        # ==================================================
        # picked
        # 搬运阶段
        # ==================================================
        if step.pick_state == "picked":
            #搬运阶段要求持续看到目标物体
            if step.require_object_in_transit:
                if not expected_boxes:return self._handle_missing_expected_object(step, expected_label)
                step.miss_count = 0
                #返回来源区
                if object_in_source:
                    step.pick_state = "in_source"
                    step.hand_grip_state = "released"
                    return False, f"{expected_label} returned to {from_region}, pick again"
                #到达目标区
                if object_in_target:
                    step.pick_state = "in_target"
                    return False, f"{expected_label} arrived at {target_region}, waiting for release"
                return False, f"Moving {expected_label} to {target_region}"
            # 搬运阶段不要求持续看到目标物体,使用手部位置继续追踪
            if not step.hand_gate_enabled:return False,"Transit object detection disabled but hand tracking is not configured"
            #手部重新回到来源区
            if hand_in_source:
                step.pick_state = "in_source"
                step.hand_grip_state = "released"
                return False, f"Hand returned to {from_region}, pick again"
            #手部到达目标区
            if hand_in_target:
                step.pick_state = "in_target"
                return False, f"Hand arrived at {target_region}, waiting for release"
            return False, f"Moving hand to {target_region}"
        # ==================================================
        # in_target
        # 验证最终结果
        # ==================================================
        if step.pick_state == "in_target":
            #目标阶段要求看到目标物体
            if step.require_object_at_target:
                if not expected_boxes:return self._handle_missing_expected_object(step, expected_label)
                step.miss_count = 0
                if not object_in_target:return False, f"Waiting for {expected_label} in {target_region}"
                # 配置手部时：
                # 物料已经在目标区，但手还压在物料上，
                # 等待放手。
                if step.hand_gate_enabled and hand_on_object:
                    step.hand_grip_state = "gripping"
                    return False, f"Waiting for hand to release {expected_label} in {target_region}"
                step.hand_grip_state = "released"
                return True, f"{expected_label} reached {target_region}"
            #目标阶段不要求看到目标物体,使用手部位置继续追踪
            if step.hand_gate_enabled:
                #手还在目标区域
                #暂时认为还没有结束放置动作
                if hand_in_target:return False, f"Waiting for hand to leave {target_region}"
                #手已经离开目标区域
                step.hand_grip_state = "released"
                return True, f"Hand left {target_region}, {expected_label} placed"
            # 没有物料目标验证，也没有手部验证
            return False,"Target object detection disabled but hand tracking is not configured"
        return False, f"Unknown pick state: {step.pick_state}"
    def _match_no_source_step(
        self,
        step: SOPStepRuntime,
        expected_label: str,
        expected_boxes: list[DetectionBox],
        target_region: str,
        target_region_boxes: list[DetectionBox],
        object_in_target: bool,
        hand_on_object: bool,
    ) -> tuple[bool, str]:
        """匹配未配置 fromRegion 的步骤。

        expectedObject 的初始位置可以在画面内任意位置。检测框短暂丢失时
        保持搬运状态，连续丢失超过 missTolerance 后才重新寻找目标。
        """
        tolerance = max(0,int(step.context.get("missTolerance", DEFAULT_MISS_TOLERANCE)),)

        def match_target() -> tuple[bool, str]:
            step.pick_state = "in_target"
            step.miss_count = 0
            if step.hand_gate_enabled and hand_on_object:
                step.hand_grip_state = "gripping"
                return False, f"Waiting for hand to release {expected_label} in {target_region}"
            step.hand_grip_state = "released"
            matched_count = count_boxes_inside_regions(expected_boxes,target_region_boxes)
            return True, f"{expected_label} reached {target_region}"

        if object_in_target:
            return match_target()

        if step.pick_state == "idle":
            if not expected_boxes:
                return False, f"Waiting for {expected_label} in visible area"
            step.pick_state = "in_source"
            step.miss_count = 0
            if step.hand_gate_enabled and hand_on_object:
                step.hand_grip_state = "gripping"
            return False, f"{expected_label} found, waiting to move to {target_region}"

        if step.pick_state == "in_source":
            if expected_boxes:
                step.miss_count = 0
                if step.hand_gate_enabled and hand_on_object:
                    step.hand_grip_state = "gripping"
                    return False, f"Picking {expected_label}, move it to {target_region}"
                return False, f"Waiting to pick {expected_label} and move it to {target_region}"

            # 有手部配置时，必须先确认手接触过目标；否则本次消失只按漏帧处理。
            if step.hand_gate_enabled and step.hand_grip_state != "gripping":
                step.miss_count += 1
                if step.miss_count <= tolerance:
                    return False, (
                        f"{expected_label} briefly lost before confirmed pickup "
                        f"({step.miss_count}/{tolerance})"
                    )
                step.pick_state = "idle"
                step.miss_count = 0
                return False, f"Waiting for {expected_label} in visible area"

            # 未配置手部时，目标从原位置消失可视为进入搬运；后续仍需在
            # missTolerance 范围内重新检测到，最终必须出现在 toRegion。
            step.pick_state = "picked"
            step.miss_count = 1
            return False, (
                f"{expected_label} temporarily not detected while moving "
                f"(1/{tolerance})"
            )

        if step.pick_state in {"picked", "in_target"}:
            if expected_boxes:
                step.pick_state = "picked"
                step.miss_count = 0
                return False, f"Moving {expected_label} to {target_region}"

            step.miss_count += 1
            if step.miss_count <= tolerance:
                return False, (
                    f"{expected_label} briefly lost while moving "
                    f"({step.miss_count}/{tolerance}), holding state"
                )

            step.pick_state = "idle"
            step.hand_grip_state = "released"
            step.miss_count = 0
            return False, f"{expected_label} lost, searching visible area again"

        step.pick_state = "idle"
        step.miss_count = 0
        return False, f"Waiting for {expected_label} in visible area"
    def _match_done_when(self, rules: list[dict[str, Any]], boxes: list[DetectionBox]) -> tuple[int, str]:
        """匹配完成条件"""
        matched_rules = 0
        reasons = []
        valid_rules = [rule for rule in rules if isinstance(rule, dict)]
        
        for rule in valid_rules:
            label = str(rule.get("label") or rule.get("expectedObject") or "").strip()
            region = str(rule.get("region") or rule.get("toRegion") or "").strip()
            count = max(1, int(rule.get("count", 1) or 1))
            
            if not label:
                continue
                
            label_boxes = find_boxes(boxes, label)
            if region:
                region_boxes = find_boxes(boxes, region)
                current_count = count_boxes_inside_regions(label_boxes, region_boxes)
            else:
                current_count = len(label_boxes)
                
            if current_count >= count:
                matched_rules += 1
            reasons.append(f"{label}:{current_count}/{count}")
            
        if matched_rules == len(valid_rules):
            return matched_rules, "; ".join(reasons) or "doneWhen matched"
        return 0, "; ".join(reasons) or "Waiting for doneWhen"

    def _match_ng_when(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> tuple[bool, str]:
        """匹配NG条件"""
        for rule in step.ng_when:
            if not isinstance(rule, dict):
                continue
            matched, reason = self._match_rule(rule, boxes)
            if matched:
                message = str(rule.get("message") or reason or "NG rule matched")
                return True, f"NG: {message}"
        return False, ""

    def _match_default_wrong_object(self, step: SOPStepRuntime, boxes: list[DetectionBox]) -> str:
        """匹配默认错误对象"""
        expected_label = str(step.context.get("expectedObject", "")).strip()
        target_region = str(step.context.get("toRegion", "")).strip()
        if not expected_label or not target_region:
            return ""

        region_boxes = find_boxes(boxes, target_region)
        if not region_boxes:
            return ""

        for object_label in self._future_expected_objects():
            object_boxes = find_boxes(boxes, object_label)
            if count_boxes_inside_regions(object_boxes, region_boxes) > 0:
                return f"NG: Expected {expected_label}, but {object_label} entered {target_region}"
        return ""

    def _match_rule(self, rule: dict[str, Any], boxes: list[DetectionBox]) -> tuple[bool, str]:
        """匹配单个规则"""
        rule_type = str(rule.get("type", "object_detected")).strip()
        label = str(rule.get("label") or rule.get("object") or rule.get("expectedObject") or "").strip()
        region = str(rule.get("region") or rule.get("toRegion") or "").strip()
        count = max(1, int(rule.get("count", 1) or 1))

        if rule_type in {"object_in_region", "wrong_object_in_region"}:
            if not label or not region:
                return False, "Invalid object_in_region rule"
            label_boxes = find_boxes(boxes, label)
            region_boxes = find_boxes(boxes, region)
            matched_count = count_boxes_inside_regions(label_boxes, region_boxes)
            return matched_count >= count, f"{label} in {region}: {matched_count}/{count}"

        if rule_type == "object_missing":
            if not label:
                return False, "Invalid object_missing rule"
            matched_count = len(find_boxes(boxes, label))
            return matched_count < count, f"{label} missing: {matched_count}/{count}"

        if not label:
            return False, "Invalid object_detected rule"
        matched_count = len(find_boxes(boxes, label))
        return matched_count >= count, f"{label}: {matched_count}/{count}"

    @staticmethod
    def _normalize_confidence(config_confidence: Any, min_score: float | None) -> float:
        """标准化置信度"""
        if min_score is not None:
            return float(min_score)
        try:
            confidence = float(config_confidence)
        except (TypeError, ValueError):
            return 0.0
        return confidence / 100.0 if confidence > 1 else confidence

    def _resolve_default_timeout(self, fallback_timeout: float) -> float:
        """解析默认超时时间"""
        configured_timeout = self.sop_config.get(
            "defaultStepTimeout",
            self.sop_config.get("stepTimeout", self.sop_config.get("timeout", fallback_timeout)),
        )
        timeout = _to_float(configured_timeout)
        return timeout if timeout > 0 else 0.0

    def _future_expected_objects(self) -> set[str]:
        """获取未来步骤的期望对象"""
        labels = set()
        for expected_label in self.expected_objects_by_step[self.current_index + 1:]:
            if expected_label:
                labels.add(expected_label)
        return labels
    
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

    boxes = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        score = _to_float(item.get("score", 0.0))
        if score < min_score:
            continue
        points = item.get("points") or item.get("bbox") or []
        label = str(item.get("label", "")).strip()
        if not label or not points:
            continue
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
    count = 0
    for target in targets:
        center = target.center
        if center is None:
            continue
        if any(point_in_box(center, region) for region in regions):
            count += 1
    return count


def point_in_box(point: tuple[float, float], box: DetectionBox,margin: float = 0.0) -> bool:
    xyxy = box.xyxy
    if xyxy is None:
        return False
    x1, y1, x2, y2 = xyxy
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    left, top = left - margin, top - margin
    right, bottom = right + margin, bottom + margin
    x, y = point
    return left <= x <= right and top <= y <= bottom


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0