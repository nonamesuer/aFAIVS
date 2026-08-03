from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from module._base import LOCAL_RESULTS_PATH,RESULTS_PATH,get_main_config
from module._result_storage import probe_storage_path

CATALOG_NAME = "sop_catalog.db"
MAX_EXPORT_ROWS = 50000
VALID_EXECUTION_STATUSES = {"running","completed","stopped","reset","failed","cancelled"}
VALID_QUALITY_STATUSES = {"ok","with_deviation","incomplete","ng"}
_STORAGE_CACHE_LOCK = threading.Lock()
_STORAGE_CACHE: tuple[float,dict] | None = None


def _normalized_path(path: str) -> str:return os.path.normcase(os.path.abspath(os.path.expanduser(os.path.expandvars(path))))


def _same_path(first: str,second: str) -> bool:return _normalized_path(first) == _normalized_path(second)


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path,timeout=10);conn.row_factory = sqlite3.Row;conn.execute("PRAGMA busy_timeout=10000");conn.execute("PRAGMA query_only=ON")
    return conn


def _table_exists(conn: sqlite3.Connection,table: str) -> bool:return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None


def _table_columns(conn: sqlite3.Connection,table: str) -> set[str]:return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()} if _table_exists(conn,table) else set()


def _safe_path(root: str,relative_path: str) -> str:
    absolute = os.path.abspath(os.path.join(root,*str(relative_path or "").replace("\\","/").split("/")))
    try:
        if os.path.commonpath([_normalized_path(root),_normalized_path(absolute)]) != _normalized_path(root):raise ValueError("Invalid result path")
    except ValueError as exc:raise ValueError("Invalid result path") from exc
    return absolute


def _json_value(value: Any,default):
    if value in (None,""):return default
    try:return json.loads(value)
    except (TypeError,json.JSONDecodeError):return default


def _camel_key(value: str) -> str:
    parts = value.split("_");return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _camel_row(row: sqlite3.Row | dict) -> dict:return {_camel_key(str(key)): value for key,value in dict(row).items()}


def _configured_path() -> str:return _normalized_path(str((get_main_config().get("paths") or {}).get("resultPath") or RESULTS_PATH))


def _storage_snapshot() -> dict:
    global _STORAGE_CACHE
    with _STORAGE_CACHE_LOCK:
        if _STORAGE_CACHE and _STORAGE_CACHE[0] > time.monotonic():return {**_STORAGE_CACHE[1],"roots":[dict(item) for item in _STORAGE_CACHE[1]["roots"]]}
    configured = _configured_path();local = _normalized_path(LOCAL_RESULTS_PATH);same = _same_path(configured,local)
    if same:available,error = True,""
    else:available,error = probe_storage_path(configured,timeout=1.5)
    roots = []
    if available and os.path.isfile(os.path.join(configured,CATALOG_NAME)):roots.append({"key":"configured","path":configured})
    if not same and os.path.isfile(os.path.join(local,CATALOG_NAME)):roots.append({"key":"local","path":local})
    if same and os.path.isfile(os.path.join(local,CATALOG_NAME)) and not roots:roots.append({"key":"configured","path":local})
    snapshot = {"configuredPath":configured,"localPath":local,"configuredAvailable":available,"configuredError":error,"usingLocalData":any(item["key"] == "local" for item in roots),"roots":roots}
    with _STORAGE_CACHE_LOCK:_STORAGE_CACHE = (time.monotonic() + 3.0,snapshot)
    return {**snapshot,"roots":[dict(item) for item in roots]}


def _parse_values(value: str | list[str] | None,allowed: set[str]) -> list[str]:
    values = value if isinstance(value,list) else str(value or "").split(",")
    return [item for item in (str(entry).strip().lower() for entry in values) if item in allowed]


def normalize_filters(filters: dict | None = None) -> dict:
    filters = filters or {};start_ms = int(filters.get("startMs") or 0);end_ms = int(filters.get("endMs") or 0)
    return {"keyword":str(filters.get("keyword") or "").strip(),"startMs":max(0,start_ms),"endMs":max(0,end_ms),"sopName":str(filters.get("sopName") or "").strip(),"cameraName":str(filters.get("cameraName") or "").strip(),"executionStatuses":_parse_values(filters.get("executionStatus"),VALID_EXECUTION_STATUSES),"qualityStatuses":_parse_values(filters.get("qualityStatus"),VALID_QUALITY_STATUSES),"hasMedia":filters.get("hasMedia") if isinstance(filters.get("hasMedia"),bool) else None}


def _where(filters: dict,catalog_columns: set[str] | None = None) -> tuple[str,list]:
    clauses = ["1=1"];params: list[Any] = []
    if filters["startMs"]:clauses.append("started_at_ms >= ?");params.append(filters["startMs"])
    if filters["endMs"]:clauses.append("started_at_ms <= ?");params.append(filters["endMs"])
    if filters["sopName"]:clauses.append("sop_name = ?");params.append(filters["sopName"])
    if filters["cameraName"]:clauses.append("camera_name = ?");params.append(filters["cameraName"])
    if filters["executionStatuses"]:clauses.append(f"execution_status IN ({','.join('?' for _ in filters['executionStatuses'])})");params.extend(filters["executionStatuses"])
    if filters["qualityStatuses"]:clauses.append(f"quality_status IN ({','.join('?' for _ in filters['qualityStatuses'])})");params.extend(filters["qualityStatuses"])
    if filters["hasMedia"] is not None:
        if catalog_columns is None or "has_media" in catalog_columns:clauses.append("has_media = ?");params.append(1 if filters["hasMedia"] else 0)
        elif filters["hasMedia"]:clauses.append("0=1")
    if filters["keyword"]:
        keyword = f"%{filters['keyword']}%";clauses.append("(run_id LIKE ? OR COALESCE(external_reference,'') LIKE ? OR COALESCE(sop_name,'') LIKE ? OR COALESCE(project_name,'') LIKE ? OR COALESCE(model_name,'') LIKE ? OR COALESCE(camera_name,'') LIKE ?)");params.extend([keyword] * 6)
    return " AND ".join(clauses),params


def _catalog_rows(root: dict,filters: dict,limit: int) -> tuple[int,list[dict]]:
    catalog_path = os.path.join(root["path"],CATALOG_NAME)
    with _connect(catalog_path) as conn:
        where,params = _where(filters,_table_columns(conn,"sop_run_catalog"))
        total = int(conn.execute(f"SELECT COUNT(*) AS total FROM sop_run_catalog WHERE {where}",params).fetchone()["total"])
        rows = conn.execute(f"SELECT * FROM sop_run_catalog WHERE {where} ORDER BY started_at_ms DESC LIMIT ?",[*params,limit]).fetchall()
    result = []
    for row in rows:item = dict(row);item["_rootKey"] = root["key"];item["_rootPath"] = root["path"];result.append(item)
    return total,result


def _enrich_rows(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str,str],list[dict]] = defaultdict(list)
    for row in rows:groups[(row["_rootPath"],str(row.get("storage_file") or ""))].append(row)
    for (root,storage_file),items in groups.items():
        database_path = _safe_path(root,storage_file);run_ids = [str(item["run_id"]) for item in items];placeholders = ",".join("?" for _ in run_ids)
        if not os.path.isfile(database_path):continue
        try:
            with _connect(database_path) as conn:
                run_rows = {str(row["run_id"]):dict(row) for row in conn.execute(f"SELECT * FROM sop_runs WHERE run_id IN ({placeholders})",run_ids).fetchall()}
                step_rows = {str(row["run_id"]):dict(row) for row in conn.execute(f"SELECT run_id,COUNT(*) AS total_steps,SUM(CASE WHEN result='completed' THEN 1 ELSE 0 END) AS completed_steps,SUM(ng_count) AS step_ng_count FROM sop_step_runs WHERE run_id IN ({placeholders}) GROUP BY run_id",run_ids).fetchall()}
            for item in items:item["_run"] = run_rows.get(str(item["run_id"]),{});item["_steps"] = step_rows.get(str(item["run_id"]),{})
        except sqlite3.Error:item["_databaseError"] = True
    return [_summary_item(row) for row in rows]


def _summary_item(catalog: dict) -> dict:
    run = catalog.get("_run") or {};steps = catalog.get("_steps") or {}
    return {"runId":catalog.get("run_id"),"storageSource":catalog.get("_rootKey"),"storageFile":catalog.get("storage_file"),"projectName":catalog.get("project_name") or run.get("project_name"),"sopName":catalog.get("sop_name") or run.get("sop_name"),"modelName":catalog.get("model_name") or run.get("model_name"),"cameraName":catalog.get("camera_name") or run.get("camera_name"),"externalReference":catalog.get("external_reference") or run.get("external_reference"),"startedAtMs":catalog.get("started_at_ms") or run.get("started_at_ms"),"endedAtMs":catalog.get("ended_at_ms") or run.get("ended_at_ms"),"executionStatus":catalog.get("execution_status") or run.get("execution_status"),"qualityStatus":catalog.get("quality_status") or run.get("quality_status"),"operatorName":run.get("operator_name") or "","stationName":run.get("station_name") or "","triggerSource":run.get("trigger_source") or "","totalDurationMs":int(run.get("total_duration_ms") or 0),"activeDurationMs":int(run.get("active_duration_ms") or 0),"pausedDurationMs":int(run.get("paused_duration_ms") or 0),"blockedDurationMs":int(run.get("blocked_duration_ms") or 0),"ngCount":int(run.get("ng_count") or steps.get("step_ng_count") or 0),"resetCount":int(run.get("reset_count") or 0),"lastStepId":run.get("last_step_id"),"lastReason":run.get("last_reason") or "","totalSteps":int(steps.get("total_steps") or 0),"completedSteps":int(steps.get("completed_steps") or 0),"mediaCount":int(catalog.get("media_count") or 0),"ngMediaCount":int(catalog.get("ng_media_count") or 0),"hasMedia":bool(catalog.get("has_media")),"coverMediaId":catalog.get("cover_media_id"),"databaseAvailable":not bool(catalog.get("_databaseError"))}


def query_results(filters: dict | None = None,page: int = 1,page_size: int = 20) -> dict:
    filters = normalize_filters(filters);page = max(1,int(page));page_size = max(1,int(page_size));required = page * page_size;snapshot = _storage_snapshot();total = 0;rows: list[dict] = []
    for root in snapshot["roots"]:
        root_total,root_rows = _catalog_rows(root,filters,required);total += root_total;rows.extend(root_rows)
    deduplicated = [] ;seen = set()
    for row in sorted(rows,key=lambda item:int(item.get("started_at_ms") or 0),reverse=True):
        if row["run_id"] in seen:continue
        seen.add(row["run_id"]);deduplicated.append(row)
    offset = (page - 1) * page_size;items = _enrich_rows(deduplicated[offset:offset + page_size])
    return {"items":items,"page":page,"pageSize":page_size,"total":total,"hasMore":offset + len(items) < total,"storage":{key:value for key,value in snapshot.items() if key != "roots"}}


def result_overview(filters: dict | None = None) -> dict:
    filters = normalize_filters(filters);snapshot = _storage_snapshot();summary = {"total":0,"completed":0,"ok":0,"deviation":0,"incomplete":0,"running":0,"withMedia":0,"mediaCount":0};trend: dict[str,dict] = {};sops: dict[str,dict] = {};options = {"sopNames":set(),"cameraNames":set()}
    for root in snapshot["roots"]:
        with _connect(os.path.join(root["path"],CATALOG_NAME)) as conn:
            columns = _table_columns(conn,"sop_run_catalog");where,params = _where(filters,columns);with_media_sql = "SUM(CASE WHEN has_media=1 THEN 1 ELSE 0 END)" if "has_media" in columns else "0";media_count_sql = "COALESCE(SUM(media_count),0)" if "media_count" in columns else "0"
            row = conn.execute(f"SELECT COUNT(*) total,SUM(CASE WHEN execution_status='completed' THEN 1 ELSE 0 END) completed,SUM(CASE WHEN execution_status='running' THEN 1 ELSE 0 END) running,SUM(CASE WHEN execution_status='completed' AND quality_status='ok' THEN 1 ELSE 0 END) ok,SUM(CASE WHEN quality_status='with_deviation' THEN 1 ELSE 0 END) deviation,SUM(CASE WHEN quality_status='incomplete' THEN 1 ELSE 0 END) incomplete,{with_media_sql} with_media,{media_count_sql} media_count FROM sop_run_catalog WHERE {where}",params).fetchone()
            for key in ("total","completed","running","ok","deviation","incomplete"):summary[key] += int(row[key] or 0)
            summary["withMedia"] += int(row["with_media"] or 0);summary["mediaCount"] += int(row["media_count"] or 0)
            for item in conn.execute(f"SELECT date(started_at_ms/1000,'unixepoch','localtime') day,COUNT(*) total,SUM(CASE WHEN execution_status='completed' AND quality_status='ok' THEN 1 ELSE 0 END) ok,SUM(CASE WHEN quality_status='with_deviation' THEN 1 ELSE 0 END) deviation FROM sop_run_catalog WHERE {where} GROUP BY day ORDER BY day",params).fetchall():
                day = str(item["day"]);target = trend.setdefault(day,{"day":day,"total":0,"ok":0,"deviation":0});target["total"] += int(item["total"] or 0);target["ok"] += int(item["ok"] or 0);target["deviation"] += int(item["deviation"] or 0)
            for item in conn.execute(f"SELECT COALESCE(sop_name,'') sop_name,COUNT(*) total,SUM(CASE WHEN execution_status='completed' AND quality_status='ok' THEN 1 ELSE 0 END) ok,SUM(CASE WHEN quality_status='with_deviation' THEN 1 ELSE 0 END) deviation FROM sop_run_catalog WHERE {where} GROUP BY sop_name ORDER BY total DESC LIMIT 12",params).fetchall():
                name = str(item["sop_name"] or "-");target = sops.setdefault(name,{"name":name,"total":0,"ok":0,"deviation":0});target["total"] += int(item["total"] or 0);target["ok"] += int(item["ok"] or 0);target["deviation"] += int(item["deviation"] or 0)
            for item in conn.execute("SELECT DISTINCT sop_name FROM sop_run_catalog WHERE COALESCE(sop_name,'')<>'' ORDER BY sop_name").fetchall():options["sopNames"].add(str(item["sop_name"]))
            for item in conn.execute("SELECT DISTINCT camera_name FROM sop_run_catalog WHERE COALESCE(camera_name,'')<>'' ORDER BY camera_name").fetchall():options["cameraNames"].add(str(item["camera_name"]))
    summary["completionRate"] = round(summary["completed"] * 100 / summary["total"],1) if summary["total"] else 0;summary["firstPassRate"] = round(summary["ok"] * 100 / summary["completed"],1) if summary["completed"] else 0
    return {"summary":summary,"trend":sorted(trend.values(),key=lambda item:item["day"]),"sopRanking":sorted(sops.values(),key=lambda item:item["total"],reverse=True)[:8],"options":{"sopNames":sorted(options["sopNames"]),"cameraNames":sorted(options["cameraNames"])},"storage":{key:value for key,value in snapshot.items() if key != "roots"}}


def _find_catalog(run_id: str) -> tuple[dict,dict]:
    snapshot = _storage_snapshot()
    for root in snapshot["roots"]:
        with _connect(os.path.join(root["path"],CATALOG_NAME)) as conn:row = conn.execute("SELECT * FROM sop_run_catalog WHERE run_id=?",(run_id,)).fetchone()
        if row:return root,dict(row)
    raise FileNotFoundError(f"Result '{run_id}' was not found")


def result_detail(run_id: str) -> dict:
    root,catalog = _find_catalog(str(run_id or "").strip());database_path = _safe_path(root["path"],catalog.get("storage_file"))
    if not os.path.isfile(database_path):raise FileNotFoundError("Result database was not found")
    with _connect(database_path) as conn:
        run_row = conn.execute("SELECT * FROM sop_runs WHERE run_id=?",(run_id,)).fetchone()
        if not run_row:raise FileNotFoundError(f"Result '{run_id}' was not found")
        step_rows = conn.execute("SELECT * FROM sop_step_runs WHERE run_id=? ORDER BY step_order",(run_id,)).fetchall();cycle_rows = conn.execute("SELECT * FROM sop_cycle_runs WHERE run_id=? ORDER BY step_id,cycle_no",(run_id,)).fetchall();event_rows = conn.execute("SELECT * FROM sop_events WHERE run_id=? ORDER BY timestamp_ms,event_id",(run_id,)).fetchall();media_rows = conn.execute("SELECT * FROM sop_media WHERE run_id=? ORDER BY captured_at_ms,created_at_ms",(run_id,)).fetchall() if _table_exists(conn,"sop_media") else []
    run = _camel_row(run_row);run["sopConfig"] = _json_value(run.pop("sopConfigJson",None),{});run["triggerPayload"] = _json_value(run.pop("triggerPayloadJson",None),{})
    cycles_by_step: dict[str,list] = defaultdict(list)
    for row in cycle_rows:cycle = _camel_row(row);cycles_by_step[str(cycle.get("stepRunId") or "")].append(cycle)
    steps = []
    for row in step_rows:step = _camel_row(row);step["cycles"] = cycles_by_step.get(str(step.get("stepRunId") or ""),[]);steps.append(step)
    events = []
    for row in event_rows:event = _camel_row(row);event["details"] = _json_value(event.pop("detailsJson",None),{});events.append(event)
    media = []
    for row in media_rows:item = _camel_row(row);item["fileAvailable"] = item.get("storageStatus") == "available" and os.path.isfile(_safe_path(root["path"],str(item.get("relativePath") or "")));media.append(item)
    return {"run":run,"steps":steps,"cycles":[_camel_row(row) for row in cycle_rows],"events":events,"media":media,"catalog":_summary_item({**catalog,"_rootKey":root["key"],"_rootPath":root["path"],"_run":dict(run_row),"_steps":{"total_steps":len(steps),"completed_steps":sum(1 for step in steps if step.get("result") == "completed")}}),"storage":{"source":root["key"],"path":root["path"],"database":catalog.get("storage_file")}}


def result_media_path(run_id: str,media_id: str) -> tuple[str,str,str]:
    root,catalog = _find_catalog(run_id);database_path = _safe_path(root["path"],catalog.get("storage_file"))
    with _connect(database_path) as conn:row = conn.execute("SELECT relative_path,mime_type,storage_status FROM sop_media WHERE run_id=? AND media_id=?",(run_id,media_id)).fetchone()
    if not row or row["storage_status"] != "available":raise FileNotFoundError("Result media is unavailable")
    path = _safe_path(root["path"],row["relative_path"])
    if not os.path.isfile(path):raise FileNotFoundError("Result media file was not found")
    return path,str(row["mime_type"] or "application/octet-stream"),os.path.basename(path)


def export_results_csv(filters: dict | None = None) -> tuple[str,int,bool]:
    result = query_results(filters,1,MAX_EXPORT_ROWS);items = result["items"];truncated = result["total"] > MAX_EXPORT_ROWS
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8-sig",newline="",delete=False,suffix=".csv") as file:
        writer = csv.writer(file);writer.writerow(["SN","Run ID","SOP","Project","Model","Camera","Operator","Station","Trigger","Started At","Ended At","Execution Status","Quality Status","Total Duration (ms)","Active Duration (ms)","Paused Duration (ms)","Blocked Duration (ms)","NG Count","Reset Count","Completed Steps","Total Steps","Media Count","Last Reason","Storage Source"])
        for item in items:writer.writerow([item["externalReference"],item["runId"],item["sopName"],item["projectName"],item["modelName"],item["cameraName"],item["operatorName"],item["stationName"],item["triggerSource"],_format_csv_time(item["startedAtMs"]),_format_csv_time(item["endedAtMs"]),item["executionStatus"],item["qualityStatus"],item["totalDurationMs"],item["activeDurationMs"],item["pausedDurationMs"],item["blockedDurationMs"],item["ngCount"],item["resetCount"],item["completedSteps"],item["totalSteps"],item["mediaCount"],item["lastReason"],item["storageSource"]])
    return file.name,len(items),truncated


def _format_csv_time(timestamp_ms) -> str:return datetime.fromtimestamp(int(timestamp_ms) / 1000).astimezone().isoformat(timespec="milliseconds") if timestamp_ms else ""
