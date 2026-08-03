from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from module._base import CONFIG_PATH, JsonFile, get_display_name, get_main_config, get_users_path, resolve_users_path

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
VALID_ROLES = {ROLE_ADMIN, ROLE_OPERATOR}
EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_LOCK = threading.RLock()
_SESSIONS: dict[str, str] = {}
_ACTIVE_TOKEN: str | None = None


def _now_iso() -> str:return datetime.now(timezone.utc).isoformat()


def _normalize_employee_id(value) -> str:
    employee_id = str(value or "").strip()
    if not EMPLOYEE_ID_PATTERN.fullmatch(employee_id):raise ValueError("Employee ID may contain only letters, numbers, underscores, periods and hyphens, up to 32 characters")
    return employee_id


def _normalize_name(value) -> str:
    name = str(value or "").strip()
    if not name or len(name) > 64:raise ValueError("Name is required and must not exceed 64 characters")
    return name


def _normalize_role(value) -> str:
    role = str(value or "").strip().lower()
    if role not in VALID_ROLES:raise ValueError("Role must be admin or operator")
    return role


def _read_users_file_unlocked(users_path: str) -> list[dict]:
    if not os.path.isfile(users_path):return []
    try:
        with open(users_path,"r",encoding="utf-8") as file:data = json.load(file)
    except (json.JSONDecodeError,OSError) as exc:raise ValueError(f"Unable to read users file: {users_path}") from exc
    users = data.get("users", []) if isinstance(data, dict) else data
    if not isinstance(users,list):raise ValueError(f"Invalid users file structure: {users_path}")
    return [deepcopy(user) for user in users if isinstance(user,dict)]


def _read_users_unlocked() -> list[dict]:return _read_users_file_unlocked(get_users_path())


def _write_users_file(users_path: str,users: list[dict]) -> None:
    os.makedirs(os.path.dirname(users_path),exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",delete=False,dir=os.path.dirname(users_path),prefix=".users.",suffix=".tmp") as file:
            temp_path = file.name;json.dump({"users": users},file,ensure_ascii=False,indent=4);file.flush();os.fsync(file.fileno())
        os.replace(temp_path,users_path);temp_path = ""
    finally:
        if temp_path and os.path.exists(temp_path):os.unlink(temp_path)


def _write_users_unlocked(users: list[dict]) -> None:_write_users_file(get_users_path(),users)


def prepare_users_storage(user_directory: str | None) -> dict:
    source_path = get_users_path();target_path = resolve_users_path(user_directory)
    if os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(os.path.abspath(target_path)):return {"path": target_path,"migrated": False,"backup": None}
    with _LOCK:
        os.makedirs(os.path.dirname(target_path),exist_ok=True);source_exists = os.path.isfile(source_path);target_exists = os.path.isfile(target_path);backup_path = None
        if source_exists:
            source_users = _read_users_file_unlocked(source_path)
            if target_exists:backup_path = os.path.join(os.path.dirname(target_path),f"users.backup.{datetime.now().strftime('%Y%m%d%H%M%S%f')}.json");shutil.copy2(target_path,backup_path)
            _write_users_file(target_path,source_users)
        elif target_exists:_write_users_file(target_path,_read_users_file_unlocked(target_path))
        else:_write_users_file(target_path,[])
        return {"path": target_path,"migrated": source_exists,"backup": backup_path}


def list_users(keyword: str = "") -> list[dict]:
    normalized_keyword = str(keyword or "").strip().casefold()
    with _LOCK:users = _read_users_unlocked()
    if normalized_keyword:users = [user for user in users if normalized_keyword in str(user.get("employeeId") or "").casefold() or normalized_keyword in str(user.get("name") or "").casefold()]
    return sorted(users,key=lambda user: str(user.get("employeeId") or "").casefold())


def has_admin_user() -> bool:return any(user.get("role") == ROLE_ADMIN for user in list_users())


def get_user(employee_id: str) -> dict | None:
    normalized = str(employee_id or "").strip().casefold()
    return next((user for user in list_users() if str(user.get("employeeId") or "").casefold() == normalized),None)


def create_user(employee_id, name, role) -> dict:
    employee_id = _normalize_employee_id(employee_id);name = _normalize_name(name);role = _normalize_role(role);now = _now_iso()
    with _LOCK:
        users = _read_users_unlocked()
        if any(str(user.get("employeeId") or "").casefold() == employee_id.casefold() for user in users):raise ValueError(f"Employee ID '{employee_id}' already exists")
        user = {"employeeId": employee_id,"name": name,"role": role,"createdAt": now,"updatedAt": now};users.append(user);_write_users_unlocked(users);return deepcopy(user)


def update_user(original_employee_id, employee_id, name, role) -> dict:
    global _ACTIVE_TOKEN
    original_employee_id = _normalize_employee_id(original_employee_id);employee_id = _normalize_employee_id(employee_id);name = _normalize_name(name);role = _normalize_role(role)
    with _LOCK:
        users = _read_users_unlocked();target_index = next((index for index,user in enumerate(users) if str(user.get("employeeId") or "").casefold() == original_employee_id.casefold()),None)
        if target_index is None:raise ValueError(f"Employee ID '{original_employee_id}' does not exist")
        if any(index != target_index and str(user.get("employeeId") or "").casefold() == employee_id.casefold() for index,user in enumerate(users)):raise ValueError(f"Employee ID '{employee_id}' already exists")
        previous = users[target_index]
        if previous.get("role") == ROLE_ADMIN and role != ROLE_ADMIN and sum(1 for user in users if user.get("role") == ROLE_ADMIN) <= 1:raise ValueError("The last administrator cannot be changed to an operator")
        updated = {**previous,"employeeId": employee_id,"name": name,"role": role,"updatedAt": _now_iso()};users[target_index] = updated;_write_users_unlocked(users)
        for token,session_employee_id in list(_SESSIONS.items()):
            if session_employee_id.casefold() == original_employee_id.casefold():_SESSIONS[token] = employee_id
        return deepcopy(updated)


def delete_user(employee_id, current_employee_id: str | None = None) -> None:
    employee_id = _normalize_employee_id(employee_id)
    with _LOCK:
        users = _read_users_unlocked();target = next((user for user in users if str(user.get("employeeId") or "").casefold() == employee_id.casefold()),None)
        if target is None:raise ValueError(f"Employee ID '{employee_id}' does not exist")
        if current_employee_id and employee_id.casefold() == current_employee_id.casefold():raise ValueError("The currently logged-in user cannot be deleted")
        if target.get("role") == ROLE_ADMIN and sum(1 for user in users if user.get("role") == ROLE_ADMIN) <= 1:raise ValueError("The last administrator cannot be deleted")
        users = [user for user in users if str(user.get("employeeId") or "").casefold() != employee_id.casefold()];_write_users_unlocked(users)
        for token,session_employee_id in list(_SESSIONS.items()):
            if session_employee_id.casefold() == employee_id.casefold():_SESSIONS.pop(token,None)


def is_account_login_enabled() -> bool:return bool((get_main_config().get("accountLogin") or {}).get("enabled",False))


def set_account_login_enabled(enabled: bool) -> None:
    global _ACTIVE_TOKEN
    if not isinstance(enabled,bool):raise ValueError("enabled must be a boolean")
    if enabled and not has_admin_user():raise ValueError("At least one administrator is required before account login can be enabled")
    with _LOCK:
        config = get_main_config();config["accountLogin"] = {"enabled": enabled};JsonFile(CONFIG_PATH).write_json_file(config);_SESSIONS.clear();_ACTIVE_TOKEN = None


def _token_from_request(request: Request) -> str:return str(request.headers.get("X-Session-Token") or "").strip()


def _session_user(token: str) -> dict | None:
    if not token:return None
    with _LOCK:employee_id = _SESSIONS.get(token)
    return get_user(employee_id) if employee_id else None


def login(employee_id: str) -> tuple[str,dict]:
    global _ACTIVE_TOKEN
    if not is_account_login_enabled():raise ValueError("Account login is not enabled")
    user = get_user(_normalize_employee_id(employee_id))
    if user is None:raise ValueError("Employee ID does not exist")
    token = uuid.uuid4().hex
    with _LOCK:_SESSIONS.clear();_SESSIONS[token] = user["employeeId"];_ACTIVE_TOKEN = token
    return token,user


def logout(token: str) -> None:
    global _ACTIVE_TOKEN
    with _LOCK:_SESSIONS.pop(token,None);_ACTIVE_TOKEN = None if token == _ACTIVE_TOKEN else _ACTIVE_TOKEN


def clear_sessions() -> None:
    global _ACTIVE_TOKEN
    with _LOCK:_SESSIONS.clear();_ACTIVE_TOKEN = None


def get_active_user() -> dict | None:
    with _LOCK:token = _ACTIVE_TOKEN
    return _session_user(token or "")


def get_current_operator_name() -> str:
    if not is_account_login_enabled():return get_display_name()
    user = get_active_user();return str(user.get("name") or "") if user else ""


def auth_status(token: str = "") -> dict:
    enabled = is_account_login_enabled()
    if not enabled:return {"loginEnabled": False,"authenticated": True,"user": {"employeeId": "","name": get_display_name(),"role": ROLE_ADMIN,"source": "system"}}
    user = _session_user(token)
    return {"loginEnabled": True,"authenticated": user is not None,"user": user}


def request_user(request: Request) -> dict | None:return auth_status(_token_from_request(request)).get("user")


def require_authenticated(request: Request) -> dict:
    status = auth_status(_token_from_request(request))
    if not status["authenticated"]:raise HTTPException(status_code=401,detail="Please log in first")
    return status["user"]


def require_admin(request: Request) -> dict:
    user = require_authenticated(request)
    if user.get("role") != ROLE_ADMIN:raise HTTPException(status_code=403,detail="Administrator permission is required")
    return user


def ensure_operator_available() -> tuple[bool,str]:
    if not is_account_login_enabled():return True,get_display_name()
    user = get_active_user();return (True,str(user.get("name") or "")) if user else (False,"")
