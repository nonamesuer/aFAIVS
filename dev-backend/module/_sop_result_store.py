from __future__ import annotations

import copy
import hashlib
import json
import os
import socket
import sqlite3
import threading
import time
import uuid
from typing import Any

from module._base import get_display_name, get_main_config


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def json_dumps(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


class SOPResultStore:
    """
    SOP 生产履历保存器。

    保存：
    1. 一次 SOP Run
    2. 每道 Step
    3. 每次 Cycle
    4. 重要 Event

    不保存每帧检测结果。
    """

    def __init__(
        self,
        project_name: str,
        model_name: str,
        camera_name: str,
        sop_config: dict | None = None,
    ):
        self.project_name = project_name or ""
        self.model_name = model_name or ""
        self.camera_name = camera_name or ""

        self.sop_config = sop_config or {}

        config = get_main_config()
        result_path = (
            config.get("paths", {}).get("resultPath")
            or os.path.join(os.getcwd(), "results")
        )

        os.makedirs(result_path, exist_ok=True)

        self.db_path = os.path.join(
            result_path,
            "sop_history.db",
        )

        self.lock = threading.RLock()

        # 一次产品/作业上下文。
        # reset 后 session_id 保持不变，
        # run_id 和 attempt_no 改变。
        self.session_id = new_id("SESSION")

        self.attempt_no = 0
        self.current_run_id: str | None = None

        # 当前 Run 内的数据库 ID 映射
        self.step_run_ids: dict[int, str] = {}
        self.cycle_run_ids: dict[
            tuple[int, int],
            str,
        ] = {}

        self._last_sop_snapshot: dict | None = None

        # 暂停/阻塞时间段
        self._pause_started_ms: int | None = None
        self._pause_step_run_id: str | None = None

        self._block_started_ms: int | None = None
        self._block_step_run_id: str | None = None

        self._init_database()

    # =========================================================
    # Database
    # =========================================================

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=5,
        )

        conn.row_factory = sqlite3.Row

        conn.execute(
            "PRAGMA journal_mode=WAL"
        )

        conn.execute(
            "PRAGMA foreign_keys=ON"
        )

        conn.execute(
            "PRAGMA busy_timeout=5000"
        )

        return conn

    def _init_database(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sop_runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,

                    project_name TEXT,
                    sop_name TEXT,
                    sop_version TEXT,
                    sop_config_hash TEXT,
                    sop_config_json TEXT,

                    model_name TEXT,
                    camera_name TEXT,
                    operator_name TEXT,
                    station_name TEXT,

                    trigger_source TEXT,
                    trigger_payload_json TEXT,
                    external_reference TEXT,

                    started_at_ms INTEGER NOT NULL,
                    ended_at_ms INTEGER,

                    execution_status TEXT NOT NULL,
                    quality_status TEXT NOT NULL,

                    total_duration_ms INTEGER DEFAULT 0,
                    active_duration_ms INTEGER DEFAULT 0,
                    paused_duration_ms INTEGER DEFAULT 0,
                    blocked_duration_ms INTEGER DEFAULT 0,

                    ng_count INTEGER DEFAULT 0,
                    reset_count INTEGER DEFAULT 0,

                    last_step_id INTEGER,
                    last_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS sop_step_runs (
                    step_run_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,

                    step_id INTEGER NOT NULL,
                    step_order INTEGER NOT NULL,
                    step_name TEXT,

                    expected_object TEXT,
                    expected_source TEXT,
                    expected_target TEXT,

                    target_count INTEGER DEFAULT 1,
                    completed_count INTEGER DEFAULT 0,

                    started_at_ms INTEGER,
                    completed_at_ms INTEGER,

                    total_duration_ms INTEGER DEFAULT 0,
                    paused_duration_ms INTEGER DEFAULT 0,
                    blocked_duration_ms INTEGER DEFAULT 0,

                    retry_count INTEGER DEFAULT 0,
                    ng_count INTEGER DEFAULT 0,

                    result TEXT NOT NULL,

                    FOREIGN KEY(run_id)
                        REFERENCES sop_runs(run_id)
                );

                CREATE TABLE IF NOT EXISTS sop_cycle_runs (
                    cycle_run_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_run_id TEXT NOT NULL,

                    step_id INTEGER NOT NULL,
                    cycle_no INTEGER NOT NULL,

                    expected_object TEXT,
                    actual_object TEXT,

                    expected_source TEXT,
                    actual_source TEXT,

                    expected_target TEXT,

                    started_at_ms INTEGER,

                    pickup_at_ms INTEGER,
                    source_departed_at_ms INTEGER,
                    target_entered_at_ms INTEGER,
                    released_at_ms INTEGER,
                    completed_at_ms INTEGER,

                    waiting_to_pick_ms INTEGER DEFAULT 0,
                    pickup_duration_ms INTEGER DEFAULT 0,
                    transit_duration_ms INTEGER DEFAULT 0,
                    placement_duration_ms INTEGER DEFAULT 0,
                    total_duration_ms INTEGER DEFAULT 0,

                    retry_count INTEGER DEFAULT 0,
                    ng_count INTEGER DEFAULT 0,

                    result TEXT NOT NULL,

                    FOREIGN KEY(run_id)
                        REFERENCES sop_runs(run_id),

                    FOREIGN KEY(step_run_id)
                        REFERENCES sop_step_runs(step_run_id)
                );

                CREATE TABLE IF NOT EXISTS sop_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,

                    run_id TEXT NOT NULL,
                    step_run_id TEXT,
                    cycle_run_id TEXT,

                    timestamp_ms INTEGER NOT NULL,

                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    code TEXT,

                    message TEXT,
                    details_json TEXT,

                    FOREIGN KEY(run_id)
                        REFERENCES sop_runs(run_id)
                );

                CREATE INDEX IF NOT EXISTS
                    idx_sop_runs_started_at
                ON sop_runs(started_at_ms);

                CREATE INDEX IF NOT EXISTS
                    idx_step_runs_run_id
                ON sop_step_runs(run_id);

                CREATE INDEX IF NOT EXISTS
                    idx_cycle_runs_run_id
                ON sop_cycle_runs(run_id);

                CREATE INDEX IF NOT EXISTS
                    idx_events_run_id
                ON sop_events(run_id);

                CREATE INDEX IF NOT EXISTS
                    idx_events_type
                ON sop_events(event_type);
                """
            )

    # =========================================================
    # Config
    # =========================================================

    def set_sop_config(
        self,
        sop_config: dict | None,
    ) -> None:
        self.sop_config = sop_config or {}

    def _config_hash(self) -> str:
        raw = json_dumps(
            self.sop_config
        ).encode("utf-8")

        return hashlib.sha256(
            raw
        ).hexdigest()

    # =========================================================
    # Run
    # =========================================================

    def start_run(
        self,
        trigger_source: str = "manual",
        trigger_payload: dict | None = None,
        keep_session: bool = False,
    ) -> str:

        with self.lock:

            # 正常情况下不会出现未结束的 Run。
            # 做一个兜底。
            if self.current_run_id:
                self.finish_run(
                    "interrupted",
                    "A new run was started before "
                    "the previous run finished",
                )

            if not keep_session and self.attempt_no > 0:
                self.session_id = new_id(
                    "SESSION"
                )
                self.attempt_no = 0

            self.attempt_no += 1

            run_id = new_id("RUN")
            started = now_ms()

            self.current_run_id = run_id

            self.step_run_ids.clear()
            self.cycle_run_ids.clear()

            self._last_sop_snapshot = None

            self._pause_started_ms = None
            self._pause_step_run_id = None

            self._block_started_ms = None
            self._block_step_run_id = None

            trigger_payload = (
                trigger_payload or {}
            )

            external_reference = (
                self._extract_external_reference(
                    trigger_source,
                    trigger_payload,
                )
            )

            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO sop_runs (
                        run_id,
                        session_id,
                        attempt_no,

                        project_name,
                        sop_name,
                        sop_version,
                        sop_config_hash,
                        sop_config_json,

                        model_name,
                        camera_name,
                        operator_name,
                        station_name,

                        trigger_source,
                        trigger_payload_json,
                        external_reference,

                        started_at_ms,

                        execution_status,
                        quality_status
                    )
                    VALUES (
                        ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?,
                        'running',
                        'ok'
                    )
                    """,
                    (
                        run_id,
                        self.session_id,
                        self.attempt_no,

                        self.project_name,
                        str(
                            self.sop_config.get(
                                "model",
                                self.project_name,
                            )
                        ),
                        str(
                            self.sop_config.get(
                                "version",
                                "",
                            )
                        ),
                        self._config_hash(),
                        json_dumps(
                            self.sop_config
                        ),

                        self.model_name,
                        self.camera_name,
                        get_display_name(),
                        socket.gethostname(),

                        trigger_source,
                        json_dumps(
                            trigger_payload
                        ),
                        external_reference,

                        started,
                    ),
                )

            self._insert_event(
                timestamp_ms=started,
                event_type="RUN_STARTED",
                severity="info",
                code="SOP_RUN_STARTED",
                message="SOP execution started",
                details={
                    "trigger_source":
                        trigger_source,
                    "trigger_payload":
                        trigger_payload,
                },
            )

            return run_id

    def finish_run(
        self,
        execution_status: str,
        reason: str = "",
    ) -> None:

        with self.lock:

            if not self.current_run_id:
                return

            ended = now_ms()

            self._close_pause(ended)
            self._close_block(ended)

            with self._connect() as conn:

                row = conn.execute(
                    """
                    SELECT
                        started_at_ms,
                        paused_duration_ms,
                        blocked_duration_ms,
                        ng_count
                    FROM sop_runs
                    WHERE run_id = ?
                    """,
                    (
                        self.current_run_id,
                    ),
                ).fetchone()

                if not row:
                    self.current_run_id = None
                    return

                total = max(
                    0,
                    ended
                    - int(
                        row["started_at_ms"]
                    ),
                )

                paused = int(
                    row[
                        "paused_duration_ms"
                    ]
                    or 0
                )

                blocked = int(
                    row[
                        "blocked_duration_ms"
                    ]
                    or 0
                )

                # 第一版按简单减法统计。
                # 原始事件都保留，
                # 后续分析可以重新精确计算。
                active = max(
                    0,
                    total
                    - paused
                    - blocked,
                )

                ng_count = int(
                    row["ng_count"] or 0
                )

                if execution_status == "completed":
                    quality_status = (
                        "ok"
                        if ng_count == 0
                        else "with_deviation"
                    )
                else:
                    quality_status = (
                        "incomplete"
                        if ng_count == 0
                        else "with_deviation"
                    )

                conn.execute(
                    """
                    UPDATE sop_runs
                    SET
                        ended_at_ms = ?,
                        execution_status = ?,
                        quality_status = ?,

                        total_duration_ms = ?,
                        active_duration_ms = ?,

                        last_reason = ?
                    WHERE run_id = ?
                    """,
                    (
                        ended,
                        execution_status,
                        quality_status,
                        total,
                        active,
                        reason,
                        self.current_run_id,
                    ),
                )

                # 未完成的工序和 cycle
                # 统一标记为对应终止状态。
                conn.execute(
                    """
                    UPDATE sop_step_runs
                    SET result = ?
                    WHERE run_id = ?
                      AND result IN (
                          'running',
                          'blocked'
                      )
                    """,
                    (
                        execution_status,
                        self.current_run_id,
                    ),
                )

                conn.execute(
                    """
                    UPDATE sop_cycle_runs
                    SET result = ?
                    WHERE run_id = ?
                      AND result IN (
                          'running',
                          'blocked',
                          'retrying'
                      )
                    """,
                    (
                        execution_status,
                        self.current_run_id,
                    ),
                )

            self._insert_event(
                timestamp_ms=ended,
                event_type="RUN_FINISHED",
                severity="info",
                code="SOP_RUN_FINISHED",
                message=reason,
                details={
                    "execution_status":
                        execution_status,
                },
            )

            self.current_run_id = None
            self._last_sop_snapshot = None

    # =========================================================
    # Snapshot consumer
    # =========================================================

    def consume_sop_snapshot(
        self,
        sop: dict | None,
    ) -> None:

        if (
            not self.current_run_id
            or not isinstance(sop, dict)
        ):
            return

        with self.lock:

            timestamp = int(
                float(
                    sop.get(
                        "updated_at",
                        time.time(),
                    )
                )
                * 1000
            )

            previous = (
                self._last_sop_snapshot
                or {}
            )

            prev_steps = {
                int(step.get("id", 0)): step
                for step
                in previous.get(
                    "steps",
                    [],
                )
                if isinstance(step, dict)
            }

            current_steps = (
                sop.get("steps", [])
            )

            for index, step in enumerate(
                current_steps
            ):
                if not isinstance(
                    step,
                    dict,
                ):
                    continue

                step_id = int(
                    step.get("id", 0)
                )

                prev = prev_steps.get(
                    step_id,
                    {},
                )

                self._consume_step(
                    step=step,
                    previous=prev,
                    step_order=index + 1,
                    timestamp_ms=timestamp,
                )

            previous_state = str(
                previous.get(
                    "state",
                    "",
                )
            )

            current_state = str(
                sop.get(
                    "state",
                    "",
                )
            )

            if (
                current_state == "paused"
                and previous_state
                != "paused"
            ):
                self._start_pause(
                    timestamp
                )

            elif (
                previous_state == "paused"
                and current_state
                != "paused"
            ):
                self._close_pause(
                    timestamp
                )

            self._last_sop_snapshot = (
                copy.deepcopy(sop)
            )

            if (
                current_state
                == "completed"
                and previous_state
                != "completed"
            ):
                self.finish_run(
                    "completed",
                    str(
                        sop.get(
                            "reason",
                            "All steps completed",
                        )
                    ),
                )

    def _consume_step(
        self,
        step: dict,
        previous: dict,
        step_order: int,
        timestamp_ms: int,
    ) -> None:

        step_id = int(
            step.get("id", 0)
        )

        state = str(
            step.get(
                "state",
                "",
            )
        )

        previous_state = str(
            previous.get(
                "state",
                "",
            )
        )

        matched_count = int(
            step.get(
                "matched_count",
                0,
            )
            or 0
        )

        previous_matched = int(
            previous.get(
                "matched_count",
                0,
            )
            or 0
        )

        target = max(
            1,
            int(
                step.get(
                    "target",
                    1,
                )
                or 1
            ),
        )

        # -----------------------------------------
        # Step started
        # -----------------------------------------

        if (
            state == "active"
            and previous_state
            not in {
                "active",
                "failed",
            }
        ):
            self._ensure_step(
                step,
                step_order,
                timestamp_ms,
            )

        if state in {
            "active",
            "failed",
            "done",
        }:
            self._ensure_step(
                step,
                step_order,
                timestamp_ms,
            )

        # -----------------------------------------
        # 当前 Cycle
        # -----------------------------------------

        if (
            state == "active"
            and matched_count < target
            and not bool(
                step.get(
                    "awaiting_cycle_reset",
                    False,
                )
            )
        ):
            self._ensure_cycle(
                step,
                matched_count + 1,
                timestamp_ms,
            )

        # -----------------------------------------
        # Pickup
        # -----------------------------------------

        hand_grip = str(
            step.get(
                "hand_grip_state",
                "",
            )
        )

        previous_hand_grip = str(
            previous.get(
                "hand_grip_state",
                "",
            )
        )

        if (
            hand_grip == "gripping"
            and previous_hand_grip
            != "gripping"
        ):
            self._mark_pickup(
                step,
                timestamp_ms,
            )

        # -----------------------------------------
        # Cycle evidence
        # -----------------------------------------

        cycle = (
            step.get("cycle")
            if isinstance(
                step.get("cycle"),
                dict,
            )
            else {}
        )

        prev_cycle = (
            previous.get("cycle")
            if isinstance(
                previous.get("cycle"),
                dict,
            )
            else {}
        )

        if (
            bool(
                cycle.get(
                    "source_departure_seen"
                )
            )
            and not bool(
                prev_cycle.get(
                    "source_departure_seen"
                )
            )
        ):
            self._mark_cycle_time(
                step,
                matched_count + 1,
                "source_departed_at_ms",
                timestamp_ms,
            )

        if (
            bool(
                cycle.get(
                    "target_entry_seen"
                )
            )
            and not bool(
                prev_cycle.get(
                    "target_entry_seen"
                )
            )
        ):
            self._mark_cycle_time(
                step,
                matched_count + 1,
                "target_entered_at_ms",
                timestamp_ms,
            )

        if (
            bool(
                cycle.get(
                    "release_seen"
                )
            )
            and not bool(
                prev_cycle.get(
                    "release_seen"
                )
            )
        ):
            self._mark_cycle_time(
                step,
                matched_count + 1,
                "released_at_ms",
                timestamp_ms,
            )

        # -----------------------------------------
        # Wrong pick
        # -----------------------------------------

        if (
            bool(
                step.get(
                    "wrong_pick_latched",
                    False,
                )
            )
            and not bool(
                previous.get(
                    "wrong_pick_latched",
                    False,
                )
            )
        ):
            self._record_wrong_pick(
                step,
                timestamp_ms,
            )

        # -----------------------------------------
        # Failed / blocked
        # -----------------------------------------

        if (
            state == "failed"
            and previous_state
            != "failed"
        ):
            self._start_block(
                step,
                timestamp_ms,
            )

        if (
            previous_state
            == "failed"
            and state == "active"
        ):
            self._close_block(
                timestamp_ms
            )

            self._increase_retry(
                step,
                matched_count + 1,
            )

        # -----------------------------------------
        # Cycle completed
        # -----------------------------------------

        if matched_count > previous_matched:

            for cycle_no in range(
                previous_matched + 1,
                matched_count + 1,
            ):
                self._complete_cycle(
                    step,
                    cycle_no,
                    timestamp_ms,
                )

        # -----------------------------------------
        # Next hand-based cycle became ready
        # -----------------------------------------

        previous_waiting = bool(
            previous.get(
                "awaiting_cycle_reset",
                False,
            )
        )

        current_waiting = bool(
            step.get(
                "awaiting_cycle_reset",
                False,
            )
        )

        if (
            previous_waiting
            and not current_waiting
            and matched_count < target
        ):
            self._ensure_cycle(
                step,
                matched_count + 1,
                timestamp_ms,
            )

        # -----------------------------------------
        # Step completed
        # -----------------------------------------

        if (
            state == "done"
            and previous_state != "done"
        ):
            self._complete_step(
                step,
                timestamp_ms,
            )

    # =========================================================
    # Step / Cycle helpers
    # =========================================================

    def _ensure_step(
        self,
        step: dict,
        step_order: int,
        timestamp_ms: int,
    ) -> str:

        step_id = int(
            step.get("id", 0)
        )

        existing = (
            self.step_run_ids.get(
                step_id
            )
        )

        if existing:
            return existing

        step_run_id = new_id("STEP")

        context = (
            step.get("context")
            if isinstance(
                step.get("context"),
                dict,
            )
            else {}
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sop_step_runs (
                    step_run_id,
                    run_id,

                    step_id,
                    step_order,
                    step_name,

                    expected_object,
                    expected_source,
                    expected_target,

                    target_count,

                    started_at_ms,

                    result
                )
                VALUES (
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?,
                    ?,
                    'running'
                )
                """,
                (
                    step_run_id,
                    self.current_run_id,

                    step_id,
                    step_order,
                    str(
                        step.get(
                            "name",
                            "",
                        )
                    ),

                    str(
                        context.get(
                            "expectedObject",
                            "",
                        )
                    ),
                    str(
                        context.get(
                            "fromRegion",
                            "",
                        )
                    ),
                    str(
                        context.get(
                            "toRegion",
                            "",
                        )
                    ),

                    int(
                        step.get(
                            "target",
                            1,
                        )
                        or 1
                    ),

                    timestamp_ms,
                ),
            )

        self.step_run_ids[
            step_id
        ] = step_run_id

        self._insert_event(
            timestamp_ms,
            "STEP_STARTED",
            "info",
            "SOP_STEP_STARTED",
            f"Step {step_id} started",
            {
                "step_id": step_id,
                "step_name":
                    step.get("name"),
            },
            step_run_id=step_run_id,
        )

        return step_run_id

    def _ensure_cycle(
        self,
        step: dict,
        cycle_no: int,
        timestamp_ms: int,
    ) -> str:

        step_id = int(
            step.get("id", 0)
        )

        key = (
            step_id,
            cycle_no,
        )

        existing = (
            self.cycle_run_ids.get(
                key
            )
        )

        if existing:
            return existing

        step_run_id = (
            self.step_run_ids.get(
                step_id
            )
        )

        if not step_run_id:
            step_run_id = (
                self._ensure_step(
                    step,
                    step_id,
                    timestamp_ms,
                )
            )

        cycle_run_id = new_id(
            "CYCLE"
        )

        context = (
            step.get("context")
            if isinstance(
                step.get("context"),
                dict,
            )
            else {}
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sop_cycle_runs (
                    cycle_run_id,
                    run_id,
                    step_run_id,

                    step_id,
                    cycle_no,

                    expected_object,
                    expected_source,
                    expected_target,

                    started_at_ms,

                    result
                )
                VALUES (
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?,
                    'running'
                )
                """,
                (
                    cycle_run_id,
                    self.current_run_id,
                    step_run_id,

                    step_id,
                    cycle_no,

                    str(
                        context.get(
                            "expectedObject",
                            "",
                        )
                    ),
                    str(
                        context.get(
                            "fromRegion",
                            "",
                        )
                    ),
                    str(
                        context.get(
                            "toRegion",
                            "",
                        )
                    ),

                    timestamp_ms,
                ),
            )

        self.cycle_run_ids[
            key
        ] = cycle_run_id

        self._insert_event(
            timestamp_ms,
            "CYCLE_STARTED",
            "info",
            "SOP_CYCLE_STARTED",
            f"Cycle {cycle_no} started",
            {
                "step_id": step_id,
                "cycle_no": cycle_no,
            },
            step_run_id=step_run_id,
            cycle_run_id=cycle_run_id,
        )

        return cycle_run_id

    def _mark_pickup(
        self,
        step: dict,
        timestamp_ms: int,
    ) -> None:

        step_id = int(
            step.get("id", 0)
        )

        cycle_no = int(
            step.get(
                "matched_count",
                0,
            )
        ) + 1

        cycle_run_id = (
            self._ensure_cycle(
                step,
                cycle_no,
                timestamp_ms,
            )
        )

        context = (
            step.get("context")
            or {}
        )

        actual_object = (
            step.get(
                "pickup_object_label"
            )
            or context.get(
                "expectedObject"
            )
            or ""
        )

        actual_source = (
            step.get(
                "pickup_origin_region"
            )
            or context.get(
                "fromRegion"
            )
            or ""
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sop_cycle_runs
                SET
                    pickup_at_ms =
                        COALESCE(
                            pickup_at_ms,
                            ?
                        ),

                    actual_object =
                        COALESCE(
                            actual_object,
                            ?
                        ),

                    actual_source =
                        COALESCE(
                            actual_source,
                            ?
                        )
                WHERE cycle_run_id = ?
                """,
                (
                    timestamp_ms,
                    actual_object,
                    actual_source,
                    cycle_run_id,
                ),
            )

        self._insert_event(
            timestamp_ms,
            "PICKUP_DETECTED",
            "info",
            "SOP_PICKUP_DETECTED",
            "Pickup detected",
            {
                "actual_object":
                    actual_object,
                "actual_source":
                    actual_source,
            },
            step_run_id=(
                self.step_run_ids.get(
                    step_id
                )
            ),
            cycle_run_id=cycle_run_id,
        )

    def _mark_cycle_time(
        self,
        step: dict,
        cycle_no: int,
        column: str,
        timestamp_ms: int,
    ) -> None:

        allowed = {
            "source_departed_at_ms",
            "target_entered_at_ms",
            "released_at_ms",
        }

        if column not in allowed:
            return

        cycle_run_id = (
            self._ensure_cycle(
                step,
                cycle_no,
                timestamp_ms,
            )
        )

        # 对 object-only 流程：
        # source departed 可以当作 pickup 时间兜底。
        if (
            column
            == "source_departed_at_ms"
        ):
            sql = f"""
                UPDATE sop_cycle_runs
                SET
                    {column} =
                        COALESCE(
                            {column},
                            ?
                        ),
                    pickup_at_ms =
                        COALESCE(
                            pickup_at_ms,
                            ?
                        )
                WHERE cycle_run_id = ?
            """

            params = (
                timestamp_ms,
                timestamp_ms,
                cycle_run_id,
            )

        else:

            sql = f"""
                UPDATE sop_cycle_runs
                SET
                    {column} =
                        COALESCE(
                            {column},
                            ?
                        )
                WHERE cycle_run_id = ?
            """

            params = (
                timestamp_ms,
                cycle_run_id,
            )

        with self._connect() as conn:
            conn.execute(
                sql,
                params,
            )

    def _complete_cycle(
        self,
        step: dict,
        cycle_no: int,
        completed_at_ms: int,
    ) -> None:

        cycle_run_id = (
            self._ensure_cycle(
                step,
                cycle_no,
                completed_at_ms,
            )
        )

        with self._connect() as conn:

            row = conn.execute(
                """
                SELECT *
                FROM sop_cycle_runs
                WHERE cycle_run_id = ?
                """,
                (
                    cycle_run_id,
                ),
            ).fetchone()

            if not row:
                return

            start = int(
                row["started_at_ms"]
                or completed_at_ms
            )

            pickup = int(
                row["pickup_at_ms"]
                or row[
                    "source_departed_at_ms"
                ]
                or start
            )

            source_departed = int(
                row[
                    "source_departed_at_ms"
                ]
                or pickup
            )

            target_entered = int(
                row[
                    "target_entered_at_ms"
                ]
                or completed_at_ms
            )

            released = int(
                row["released_at_ms"]
                or completed_at_ms
            )

            waiting = max(
                0,
                pickup - start,
            )

            pickup_duration = max(
                0,
                source_departed
                - pickup,
            )

            transit = max(
                0,
                target_entered
                - source_departed,
            )

            placement = max(
                0,
                released
                - target_entered,
            )

            total = max(
                0,
                completed_at_ms
                - start,
            )

            context = (
                step.get("context")
                or {}
            )

            conn.execute(
                """
                UPDATE sop_cycle_runs
                SET
                    completed_at_ms = ?,

                    waiting_to_pick_ms = ?,
                    pickup_duration_ms = ?,
                    transit_duration_ms = ?,
                    placement_duration_ms = ?,
                    total_duration_ms = ?,

                    actual_object =
                        COALESCE(
                            actual_object,
                            ?
                        ),

                    actual_source =
                        COALESCE(
                            actual_source,
                            ?
                        ),

                    result = 'completed'

                WHERE cycle_run_id = ?
                """,
                (
                    completed_at_ms,

                    waiting,
                    pickup_duration,
                    transit,
                    placement,
                    total,

                    str(
                        context.get(
                            "expectedObject",
                            "",
                        )
                    ),

                    str(
                        context.get(
                            "fromRegion",
                            "",
                        )
                    ),

                    cycle_run_id,
                ),
            )

            conn.execute(
                """
                UPDATE sop_step_runs
                SET completed_count =
                    MAX(
                        completed_count,
                        ?
                    )
                WHERE step_run_id = ?
                """,
                (
                    cycle_no,
                    row["step_run_id"],
                ),
            )

        self._insert_event(
            completed_at_ms,
            "CYCLE_COMPLETED",
            "success",
            "SOP_CYCLE_COMPLETED",
            f"Cycle {cycle_no} completed",
            {
                "cycle_no": cycle_no,
            },
            step_run_id=(
                self.step_run_ids.get(
                    int(
                        step.get(
                            "id",
                            0,
                        )
                    )
                )
            ),
            cycle_run_id=cycle_run_id,
        )

    def _complete_step(
        self,
        step: dict,
        completed_at_ms: int,
    ) -> None:

        step_id = int(
            step.get("id", 0)
        )

        step_run_id = (
            self.step_run_ids.get(
                step_id
            )
        )

        if not step_run_id:
            return

        with self._connect() as conn:

            row = conn.execute(
                """
                SELECT started_at_ms
                FROM sop_step_runs
                WHERE step_run_id = ?
                """,
                (
                    step_run_id,
                ),
            ).fetchone()

            total = 0

            if row and row[
                "started_at_ms"
            ]:
                total = max(
                    0,
                    completed_at_ms
                    - int(
                        row[
                            "started_at_ms"
                        ]
                    ),
                )

            conn.execute(
                """
                UPDATE sop_step_runs
                SET
                    completed_at_ms = ?,
                    total_duration_ms = ?,
                    completed_count = ?,
                    result = 'completed'
                WHERE step_run_id = ?
                """,
                (
                    completed_at_ms,
                    total,
                    int(
                        step.get(
                            "matched_count",
                            0,
                        )
                    ),
                    step_run_id,
                ),
            )

        self._insert_event(
            completed_at_ms,
            "STEP_COMPLETED",
            "success",
            "SOP_STEP_COMPLETED",
            f"Step {step_id} completed",
            {
                "step_id": step_id,
                "step_name":
                    step.get("name"),
            },
            step_run_id=step_run_id,
        )

    # =========================================================
    # NG / block / retry
    # =========================================================

    def _record_wrong_pick(
        self,
        step: dict,
        timestamp_ms: int,
    ) -> None:

        step_id = int(
            step.get("id", 0)
        )

        cycle_no = int(
            step.get(
                "matched_count",
                0,
            )
        ) + 1

        cycle_run_id = (
            self._ensure_cycle(
                step,
                cycle_no,
                timestamp_ms,
            )
        )

        reason = str(
            step.get(
                "wrong_pick_reason",
                "",
            )
        )

        actual_object = str(
            step.get(
                "pickup_object_label",
                "",
            )
            or ""
        )

        actual_source = str(
            step.get(
                "pickup_origin_region",
                "",
            )
            or ""
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sop_cycle_runs
                SET
                    actual_object = ?,
                    actual_source = ?
                WHERE cycle_run_id = ?
                """,
                (
                    actual_object,
                    actual_source,
                    cycle_run_id,
                ),
            )

        if "Wrong pickup source" in reason:
            event_type = (
                "WRONG_PICK_SOURCE"
            )
            code = (
                "SOP_WRONG_PICK_SOURCE"
            )
        else:
            event_type = (
                "WRONG_MATERIAL"
            )
            code = (
                "SOP_WRONG_MATERIAL"
            )

        self._insert_event(
            timestamp_ms,
            event_type,
            "error",
            code,
            reason,
            {
                "actual_object":
                    actual_object,
                "actual_source":
                    actual_source,
            },
            step_run_id=(
                self.step_run_ids.get(
                    step_id
                )
            ),
            cycle_run_id=cycle_run_id,
        )

    def _start_block(
        self,
        step: dict,
        timestamp_ms: int,
    ) -> None:

        if self._block_started_ms:
            return

        step_id = int(
            step.get("id", 0)
        )

        step_run_id = (
            self.step_run_ids.get(
                step_id
            )
        )

        self._block_started_ms = (
            timestamp_ms
        )

        self._block_step_run_id = (
            step_run_id
        )

        reason = str(
            step.get(
                "last_reason",
                "",
            )
        )

        with self._connect() as conn:

            conn.execute(
                """
                UPDATE sop_runs
                SET
                    ng_count =
                        ng_count + 1,
                    quality_status =
                        'with_deviation',
                    last_step_id = ?,
                    last_reason = ?
                WHERE run_id = ?
                """,
                (
                    step_id,
                    reason,
                    self.current_run_id,
                ),
            )

            if step_run_id:
                conn.execute(
                    """
                    UPDATE sop_step_runs
                    SET
                        ng_count =
                            ng_count + 1,
                        result = 'blocked'
                    WHERE step_run_id = ?
                    """,
                    (
                        step_run_id,
                    ),
                )

        cycle_no = int(
            step.get(
                "matched_count",
                0,
            )
        ) + 1

        cycle_run_id = (
            self._ensure_cycle(
                step,
                cycle_no,
                timestamp_ms,
            )
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sop_cycle_runs
                SET
                    ng_count =
                        ng_count + 1,
                    result = 'blocked'
                WHERE cycle_run_id = ?
                """,
                (
                    cycle_run_id,
                ),
            )

        self._insert_event(
            timestamp_ms,
            "STEP_BLOCKED",
            "error",
            "SOP_STEP_BLOCKED",
            reason,
            {
                "step_id": step_id,
            },
            step_run_id=step_run_id,
            cycle_run_id=cycle_run_id,
        )

    def _close_block(
        self,
        timestamp_ms: int,
    ) -> None:

        if self._block_started_ms is None:
            return

        duration = max(
            0,
            timestamp_ms
            - self._block_started_ms,
        )

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sop_runs
                SET blocked_duration_ms =
                    blocked_duration_ms + ?
                WHERE run_id = ?
                """,
                (
                    duration,
                    self.current_run_id,
                ),
            )

            if self._block_step_run_id:
                conn.execute(
                    """
                    UPDATE sop_step_runs
                    SET
                        blocked_duration_ms =
                            blocked_duration_ms + ?,
                        result = 'running'
                    WHERE step_run_id = ?
                    """,
                    (
                        duration,
                        self._block_step_run_id,
                    ),
                )

        self._insert_event(
            timestamp_ms,
            "BLOCK_CLEARED",
            "info",
            "SOP_BLOCK_CLEARED",
            "Blocked condition cleared",
            {
                "duration_ms":
                    duration,
            },
            step_run_id=(
                self._block_step_run_id
            ),
        )

        self._block_started_ms = None
        self._block_step_run_id = None

    def _increase_retry(
        self,
        step: dict,
        cycle_no: int,
    ) -> None:

        step_id = int(
            step.get("id", 0)
        )

        step_run_id = (
            self.step_run_ids.get(
                step_id
            )
        )

        cycle_run_id = (
            self.cycle_run_ids.get(
                (
                    step_id,
                    cycle_no,
                )
            )
        )

        with self._connect() as conn:

            if step_run_id:
                conn.execute(
                    """
                    UPDATE sop_step_runs
                    SET retry_count =
                        retry_count + 1
                    WHERE step_run_id = ?
                    """,
                    (
                        step_run_id,
                    ),
                )

            if cycle_run_id:
                conn.execute(
                    """
                    UPDATE sop_cycle_runs
                    SET
                        retry_count =
                            retry_count + 1,
                        result = 'retrying'
                    WHERE cycle_run_id = ?
                    """,
                    (
                        cycle_run_id,
                    ),
                )

    # =========================================================
    # Pause
    # =========================================================

    def _start_pause(
        self,
        timestamp_ms: int,
    ) -> None:

        if self._pause_started_ms:
            return

        self._pause_started_ms = (
            timestamp_ms
        )

        self._pause_step_run_id = (
            self._current_step_run_id()
        )

        self._insert_event(
            timestamp_ms,
            "PAUSED",
            "info",
            "SOP_PAUSED",
            "SOP paused",
            {},
            step_run_id=(
                self._pause_step_run_id
            ),
        )

    def _close_pause(
        self,
        timestamp_ms: int,
    ) -> None:

        if self._pause_started_ms is None:
            return

        duration = max(
            0,
            timestamp_ms
            - self._pause_started_ms,
        )

        with self._connect() as conn:

            conn.execute(
                """
                UPDATE sop_runs
                SET paused_duration_ms =
                    paused_duration_ms + ?
                WHERE run_id = ?
                """,
                (
                    duration,
                    self.current_run_id,
                ),
            )

            if self._pause_step_run_id:
                conn.execute(
                    """
                    UPDATE sop_step_runs
                    SET paused_duration_ms =
                        paused_duration_ms + ?
                    WHERE step_run_id = ?
                    """,
                    (
                        duration,
                        self._pause_step_run_id,
                    ),
                )

        self._insert_event(
            timestamp_ms,
            "RESUMED",
            "info",
            "SOP_RESUMED",
            "SOP resumed",
            {
                "paused_duration_ms":
                    duration,
            },
            step_run_id=(
                self._pause_step_run_id
            ),
        )

        self._pause_started_ms = None
        self._pause_step_run_id = None

    # =========================================================
    # Event helper
    # =========================================================

    def _insert_event(
        self,
        timestamp_ms: int,
        event_type: str,
        severity: str,
        code: str,
        message: str,
        details: dict,
        step_run_id: str | None = None,
        cycle_run_id: str | None = None,
    ) -> None:

        if not self.current_run_id:
            return

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sop_events (
                    run_id,
                    step_run_id,
                    cycle_run_id,

                    timestamp_ms,

                    event_type,
                    severity,
                    code,

                    message,
                    details_json
                )
                VALUES (
                    ?, ?, ?,
                    ?,
                    ?, ?, ?,
                    ?, ?
                )
                """,
                (
                    self.current_run_id,
                    step_run_id,
                    cycle_run_id,

                    timestamp_ms,

                    event_type,
                    severity,
                    code,

                    message,
                    json_dumps(details),
                ),
            )

    def _current_step_run_id(
        self,
    ) -> str | None:

        if not self._last_sop_snapshot:
            return None

        progress = (
            self._last_sop_snapshot.get(
                "progress",
                {},
            )
        )

        index = int(
            progress.get(
                "current_index",
                -1,
            )
        )

        steps = (
            self._last_sop_snapshot.get(
                "steps",
                [],
            )
        )

        if (
            index < 0
            or index >= len(steps)
        ):
            return None

        step_id = int(
            steps[index].get(
                "id",
                0,
            )
        )

        return self.step_run_ids.get(
            step_id
        )

    @staticmethod
    def _extract_external_reference(
        source: str,
        payload: dict,
    ) -> str:

        if source == "usb":
            return str(
                payload.get(
                    "value",
                    "",
                )
            )

        if source == "http":
            parameters = payload.get(
                "parameters",
                {},
            )

            if isinstance(
                parameters,
                dict,
            ):
                values = [
                    str(value)
                    for value
                    in parameters.values()
                    if value is not None
                ]

                if values:
                    return values[0]

        return ""