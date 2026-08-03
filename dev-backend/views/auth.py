from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from module._auth import auth_status, create_user, delete_user, list_users, login, logout, require_admin, require_authenticated, set_account_login_enabled, update_user

api_auth = APIRouter(prefix="/auth")


class LoginRequest(BaseModel):employeeId: str
class UserRequest(BaseModel):employeeId: str;name: str;role: str
class LoginSettingRequest(BaseModel):enabled: bool


@api_auth.get("/status")
def get_auth_status(request: Request):return JSONResponse({"status": True,"data": auth_status(str(request.headers.get("X-Session-Token") or "").strip())})


@api_auth.post("/login")
def login_user(payload: LoginRequest):
    try:
        token,user = login(payload.employeeId);return JSONResponse({"status": True,"msg": "Login successful","data": {"token": token,"user": user}})
    except ValueError as exc:return JSONResponse({"status": False,"msg": str(exc)})


@api_auth.post("/logout")
def logout_user(request: Request,user: dict = Depends(require_authenticated)):
    from views.detection import get_runtime
    runtime = get_runtime()
    if runtime and runtime.running:return JSONResponse({"status": False,"code": "DETECTION_ACTIVE","msg": "Logout is not allowed while detection is running"})
    logout(str(request.headers.get("X-Session-Token") or "").strip());return JSONResponse({"status": True,"msg": "Logout successful"})


@api_auth.get("/users")
def query_users(keyword: str = "",admin: dict = Depends(require_admin)):return JSONResponse({"status": True,"data": list_users(keyword)})


@api_auth.post("/users")
def add_user(payload: UserRequest,admin: dict = Depends(require_admin)):
    try:return JSONResponse({"status": True,"msg": "User created successfully","data": create_user(payload.employeeId,payload.name,payload.role)})
    except ValueError as exc:return JSONResponse({"status": False,"msg": str(exc)})


@api_auth.put("/users/{employee_id}")
def modify_user(employee_id: str,payload: UserRequest,admin: dict = Depends(require_admin)):
    try:return JSONResponse({"status": True,"msg": "User updated successfully","data": update_user(employee_id,payload.employeeId,payload.name,payload.role)})
    except ValueError as exc:return JSONResponse({"status": False,"msg": str(exc)})


@api_auth.delete("/users/{employee_id}")
def remove_user(employee_id: str,admin: dict = Depends(require_admin)):
    try:delete_user(employee_id,admin.get("employeeId"));return JSONResponse({"status": True,"msg": "User deleted successfully"})
    except ValueError as exc:return JSONResponse({"status": False,"msg": str(exc)})


@api_auth.put("/settings")
def modify_login_settings(payload: LoginSettingRequest,admin: dict = Depends(require_admin)):
    from views.detection import get_runtime
    runtime = get_runtime()
    if runtime and runtime.running:return JSONResponse({"status": False,"code": "DETECTION_ACTIVE","msg": "Login settings cannot be changed while detection is running"})
    try:set_account_login_enabled(payload.enabled);return JSONResponse({"status": True,"msg": "Login settings updated successfully","data": {"enabled": payload.enabled}})
    except ValueError as exc:return JSONResponse({"status": False,"msg": str(exc)})
