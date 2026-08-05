from __future__ import annotations

import ctypes
import logging
import os
import queue
import shutil
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from module._base import LOCAL_RESULTS_PATH, RESULTS_PATH, get_main_config

logger = logging.getLogger(__name__)

_SYNC_LOCK = threading.Lock()
_AUTO_SYNC_LOCK = threading.Lock()
_AUTO_SYNC_THREAD: threading.Thread | None = None


@dataclass(frozen=True)
class ResultStorageLocation:
    configured_path: str
    active_path: str
    local_path: str
    using_local_fallback: bool
    fallback_reason: str


def _normalized_path(path: str) -> str:
    return os.path.normcase(
        os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    )


def _same_path(first: str, second: str) -> bool:
    return _normalized_path(first) == _normalized_path(second)


def is_network_path(path: str) -> bool:
    normalized = str(path or "").strip()
    if normalized.startswith(("\\\\", "//")):
        return True

    if os.name != "nt":
        return False

    drive, _ = os.path.splitdrive(os.path.abspath(normalized))
    if not drive:
        return False
    try:
        # DRIVE_REMOTE = 4. This also identifies a mapped network drive.
        return ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\") == 4
    except Exception:
        return False


def probe_storage_path(path: str, timeout: float = 2.0) -> tuple[bool, str]:
    """
    Test both directory access and an actual file write.

    Network filesystem calls can block inside the operating system. The probe
    therefore runs in a daemon thread and has a bounded wait time.
    """
    result: queue.Queue[tuple[bool, str]] = queue.Queue(maxsize=1)
    probe_name = f".afaivs-storage-probe-{uuid.uuid4().hex}.tmp"

    def worker() -> None:
        probe_path = ""
        try:
            os.makedirs(path, exist_ok=True)
            probe_path = os.path.join(path, probe_name)
            with open(probe_path, "wb") as probe_file:
                probe_file.write(b"aFAIVS")
                probe_file.flush()
                os.fsync(probe_file.fileno())
            os.remove(probe_path)
            result.put_nowait((True, ""))
        except Exception as exc:
            if probe_path:
                try:
                    if os.path.exists(probe_path):
                        os.remove(probe_path)
                except OSError:
                    pass
            try:
                result.put_nowait((False, str(exc)))
            except queue.Full:
                pass

    thread = threading.Thread(
        target=worker,
        name="result-storage-probe",
        daemon=True,
    )
    thread.start()
    thread.join(max(0.1, timeout))
    if thread.is_alive():
        return False, f"Storage path access timed out after {timeout:g}s"
    try:
        return result.get_nowait()
    except queue.Empty:
        return False, "Storage path probe did not return a result"


def resolve_result_storage(
    configured_path: str | None = None,
) -> ResultStorageLocation:
    raw_configured = str(configured_path or RESULTS_PATH)
    configured_is_network = is_network_path(raw_configured)
    configured = _normalized_path(raw_configured)
    local = _normalized_path(LOCAL_RESULTS_PATH)

    if _same_path(configured, local):
        os.makedirs(local, exist_ok=True)
        return ResultStorageLocation(configured, local, local, False, "")

    # A user-selected result path is deliberately treated as a destination
    # rather than the live database. Runs are first committed locally and
    # copied to the destination after completion. This remains safe if a NAS,
    # mapped drive, removable disk, or other custom path disappears midway
    # through a run.
    if configured_is_network or not _same_path(configured, RESULTS_PATH):
        os.makedirs(local, exist_ok=True)
        return ResultStorageLocation(
            configured,
            local,
            local,
            True,
            (
                "network_path_uses_local_spool"
                if configured_is_network
                else "custom_path_uses_local_spool"
            ),
        )

    available, reason = probe_storage_path(configured)
    if available:
        return ResultStorageLocation(configured, configured, local, False, "")

    os.makedirs(local, exist_ok=True)
    logger.warning(
        "Result path '%s' is unavailable; using '%s': %s",
        configured,
        local,
        reason,
    )
    return ResultStorageLocation(
        configured,
        local,
        local,
        True,
        reason or "configured_path_unavailable",
    )


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _clone_schema(source: sqlite3.Connection, target: sqlite3.Connection) -> None:
    rows = source.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index')
          AND sql IS NOT NULL
          AND name NOT LIKE 'sqlite_%'
        ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name
        """
    ).fetchall()
    for row in rows:
        exists = target.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = ? AND name = ?
            """,
            (row["type"], row["name"]),
        ).fetchone()
        if exists:
            continue
        target.execute(row["sql"])


def _insert_row(
    conn: sqlite3.Connection,
    table: str,
    row: sqlite3.Row | dict[str, Any],
    *,
    exclude: set[str] | None = None,
) -> sqlite3.Cursor:
    values = dict(row)
    for field in exclude or set():
        values.pop(field, None)
    columns = list(values)
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    return conn.execute(
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})',
        [values[column] for column in columns],
    )


def _copy_file_atomic(source: str, target: str) -> int:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    source_size = os.path.getsize(source)
    if os.path.exists(target):
        if os.path.getsize(target) == source_size:
            return source_size

    temp_path = f"{target}.sync-{uuid.uuid4().hex}.part"
    try:
        with open(source, "rb") as source_file, open(temp_path, "wb") as copied_file:
            shutil.copyfileobj(source_file, copied_file, length=1024 * 1024)
            copied_file.flush()
            os.fsync(copied_file.fileno())
        if os.path.getsize(temp_path) != source_size:raise OSError(f"Copied result file size mismatch: {source}")
        try:shutil.copystat(source, temp_path)
        except OSError:logger.debug("Unable to copy result file metadata from %s to %s",source,temp_path,exc_info=True)
        os.replace(temp_path, target)
        return source_size
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def _safe_media_path(root: str, relative_path: str) -> str:
    absolute = os.path.abspath(
        os.path.join(root, *str(relative_path).replace("\\", "/").split("/"))
    )
    if os.path.commonpath([_normalized_path(root), _normalized_path(absolute)]) != (
        _normalized_path(root)
    ):
        raise ValueError(f"Invalid media relative path: {relative_path}")
    return absolute


def _sync_run(
    source_root: str,
    target_root: str,
    source_catalog: sqlite3.Connection,
    target_catalog: sqlite3.Connection,
    catalog_row: sqlite3.Row,
) -> tuple[int, int]:
    run_id = str(catalog_row["run_id"])
    storage_file = str(catalog_row["storage_file"])
    source_db_path = _safe_media_path(source_root, storage_file)
    target_db_path = _safe_media_path(target_root, storage_file)
    if not os.path.isfile(source_db_path):
        raise FileNotFoundError(f"Local history database is missing: {storage_file}")

    os.makedirs(os.path.dirname(target_db_path), exist_ok=True)
    source_db = _connect(source_db_path)
    try:
        pending = source_db.execute(
            """
            SELECT COUNT(*) AS total
            FROM sop_media
            WHERE run_id = ? AND storage_status = 'pending'
            """,
            (run_id,),
        ).fetchone()["total"]
        if pending:
            raise RuntimeError("Media files for this run are still being written")

        run_row = source_db.execute(
            "SELECT * FROM sop_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise RuntimeError(f"Run '{run_id}' is missing from {storage_file}")
        if str(run_row["execution_status"]) == "running":
            raise RuntimeError("The run is still active")

        steps = source_db.execute(
            "SELECT * FROM sop_step_runs WHERE run_id = ? ORDER BY step_order",
            (run_id,),
        ).fetchall()
        cycles = source_db.execute(
            """
            SELECT * FROM sop_cycle_runs
            WHERE run_id = ?
            ORDER BY step_id, cycle_no
            """,
            (run_id,),
        ).fetchall()
        events = source_db.execute(
            "SELECT * FROM sop_events WHERE run_id = ? ORDER BY event_id",
            (run_id,),
        ).fetchall()
        media = source_db.execute(
            "SELECT * FROM sop_media WHERE run_id = ? ORDER BY created_at_ms",
            (run_id,),
        ).fetchall()

        copied_bytes = 0
        for item in media:
            if item["storage_status"] != "available":
                continue
            source_file = _safe_media_path(source_root, item["relative_path"])
            target_file = _safe_media_path(target_root, item["relative_path"])
            if not os.path.isfile(source_file):
                raise FileNotFoundError(
                    f"Local evidence file is missing: {item['relative_path']}"
                )
            copied_bytes += _copy_file_atomic(source_file, target_file)

        target_db = _connect(target_db_path)
        try:
            _clone_schema(source_db, target_db)
            target_db.execute("BEGIN IMMEDIATE")
            target_db.execute("DELETE FROM sop_media WHERE run_id = ?", (run_id,))
            target_db.execute("DELETE FROM sop_events WHERE run_id = ?", (run_id,))
            target_db.execute("DELETE FROM sop_cycle_runs WHERE run_id = ?", (run_id,))
            target_db.execute("DELETE FROM sop_step_runs WHERE run_id = ?", (run_id,))
            target_db.execute("DELETE FROM sop_runs WHERE run_id = ?", (run_id,))

            _insert_row(target_db, "sop_runs", run_row)
            for row in steps:
                _insert_row(target_db, "sop_step_runs", row)
            for row in cycles:
                _insert_row(target_db, "sop_cycle_runs", row)

            event_id_map: dict[int, int] = {}
            for row in events:
                old_event_id = int(row["event_id"])
                cursor = _insert_row(
                    target_db,
                    "sop_events",
                    row,
                    exclude={"event_id"},
                )
                event_id_map[old_event_id] = int(cursor.lastrowid)

            for row in media:
                media_values = dict(row)
                old_event_id = media_values.get("event_id")
                if old_event_id is not None:
                    media_values["event_id"] = event_id_map.get(
                        int(old_event_id)
                    )
                _insert_row(target_db, "sop_media", media_values)
            target_db.commit()
        except Exception:
            target_db.rollback()
            raise
        finally:
            target_db.close()

        target_catalog.execute(
            "DELETE FROM sop_run_catalog WHERE run_id = ?",
            (run_id,),
        )
        _insert_row(target_catalog, "sop_run_catalog", catalog_row)
        target_catalog.commit()

        # Only remove local data after files, monthly database and catalog have
        # all been committed successfully.
        source_db.execute("BEGIN IMMEDIATE")
        source_db.execute("DELETE FROM sop_media WHERE run_id = ?", (run_id,))
        source_db.execute("DELETE FROM sop_events WHERE run_id = ?", (run_id,))
        source_db.execute("DELETE FROM sop_cycle_runs WHERE run_id = ?", (run_id,))
        source_db.execute("DELETE FROM sop_step_runs WHERE run_id = ?", (run_id,))
        source_db.execute("DELETE FROM sop_runs WHERE run_id = ?", (run_id,))
        source_db.commit()

        source_catalog.execute(
            "DELETE FROM sop_run_catalog WHERE run_id = ?",
            (run_id,),
        )
        source_catalog.commit()

        for item in media:
            source_file = _safe_media_path(source_root, item["relative_path"])
            try:
                if os.path.isfile(source_file):
                    os.remove(source_file)
            except OSError:
                logger.warning("Unable to remove synced local file %s", source_file)
        return len(media), copied_bytes
    finally:
        source_db.close()


def _pending_summary(local_root: str) -> dict:
    catalog_path = os.path.join(local_root, "sop_catalog.db")
    if not os.path.isfile(catalog_path):
        return {
            "pending": False,
            "pendingRunCount": 0,
            "pendingMediaCount": 0,
            "pendingBytes": 0,
        }

    run_count = 0
    media_count = 0
    try:
        with _connect(catalog_path) as catalog:
            run_count = int(
                catalog.execute(
                    "SELECT COUNT(*) AS total FROM sop_run_catalog"
                ).fetchone()["total"]
            )
            media_count = int(
                catalog.execute(
                    """
                    SELECT COALESCE(SUM(media_count), 0) AS total
                    FROM sop_run_catalog
                    """
                ).fetchone()["total"]
            )
    except (sqlite3.Error, OSError):
        logger.exception("Unable to read local result catalog")

    total_bytes = 0
    try:
        for directory, _, filenames in os.walk(local_root):
            for filename in filenames:
                try:
                    total_bytes += os.path.getsize(
                        os.path.join(directory, filename)
                    )
                except OSError:
                    pass
    except OSError:
        pass

    return {
        "pending": run_count > 0,
        "pendingRunCount": run_count,
        "pendingMediaCount": media_count,
        "pendingBytes": total_bytes,
    }


def get_result_storage_status() -> dict:
    configured = (
        get_main_config().get("paths", {}).get("resultPath") or RESULTS_PATH
    )
    configured = _normalized_path(configured)
    local = _normalized_path(LOCAL_RESULTS_PATH)
    available, error = probe_storage_path(configured)
    pending = _pending_summary(local)
    return {
        "configuredPath": configured,
        "localPath": local,
        "configuredPathAvailable": available,
        "configuredPathError": error,
        "syncInProgress": _SYNC_LOCK.locked(),
        **pending,
    }


def sync_local_results(configured_path: str | None = None) -> dict:
    configured = configured_path or (
        get_main_config().get("paths", {}).get("resultPath") or RESULTS_PATH
    )
    target_root = _normalized_path(configured)
    source_root = _normalized_path(LOCAL_RESULTS_PATH)
    if _same_path(source_root, target_root):
        raise ValueError("The configured result path is the local fallback path")

    if not _SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("A local result synchronization is already running")

    try:
        available, error = probe_storage_path(target_root, timeout=5.0)
        if not available:
            raise OSError(
                f"The configured result path is unavailable: {error}"
            )

        source_catalog_path = os.path.join(source_root, "sop_catalog.db")
        if not os.path.isfile(source_catalog_path):
            return {
                "syncedRunCount": 0,
                "syncedMediaCount": 0,
                "syncedBytes": 0,
                "failedRunCount": 0,
                "errors": [],
            }

        os.makedirs(target_root, exist_ok=True)
        target_catalog_path = os.path.join(target_root, "sop_catalog.db")
        source_catalog = _connect(source_catalog_path)
        target_catalog = _connect(target_catalog_path)
        try:
            _clone_schema(source_catalog, target_catalog)
            catalog_rows = source_catalog.execute(
                """
                SELECT *
                FROM sop_run_catalog
                WHERE execution_status <> 'running'
                ORDER BY started_at_ms
                """
            ).fetchall()
            summary = {
                "syncedRunCount": 0,
                "syncedMediaCount": 0,
                "syncedBytes": 0,
                "failedRunCount": 0,
                "errors": [],
            }
            for catalog_row in catalog_rows:
                try:
                    media_count, copied_bytes = _sync_run(
                        source_root,
                        target_root,
                        source_catalog,
                        target_catalog,
                        catalog_row,
                    )
                    summary["syncedRunCount"] += 1
                    summary["syncedMediaCount"] += media_count
                    summary["syncedBytes"] += copied_bytes
                except Exception as exc:
                    logger.exception(
                        "Failed to synchronize local run %s",
                        catalog_row["run_id"],
                    )
                    summary["failedRunCount"] += 1
                    summary["errors"].append(
                        {
                            "runId": catalog_row["run_id"],
                            "message": str(exc),
                        }
                    )
            return summary
        finally:
            target_catalog.close()
            source_catalog.close()
    finally:
        _SYNC_LOCK.release()


def request_auto_sync(configured_path: str) -> None:
    global _AUTO_SYNC_THREAD

    if _same_path(configured_path, LOCAL_RESULTS_PATH):
        return

    with _AUTO_SYNC_LOCK:
        if _AUTO_SYNC_THREAD and _AUTO_SYNC_THREAD.is_alive():
            return

        def worker() -> None:
            try:
                sync_local_results(configured_path)
            except Exception:
                # Offline network paths are expected here. Pending local data
                # remains visible in Config and can be retried by the user.
                logger.info(
                    "Automatic local result synchronization was deferred",
                    exc_info=True,
                )

        _AUTO_SYNC_THREAD = threading.Thread(
            target=worker,
            name="result-storage-auto-sync",
            daemon=True,
        )
        _AUTO_SYNC_THREAD.start()
