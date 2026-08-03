import logging
import os
import json
import shutil
import tempfile
import uuid
from copy import deepcopy
from pathlib import Path
import numpy as np
import base64
import cv2
from fastapi.responses import FileResponse, JSONResponse
from fastapi import APIRouter, Request,HTTPException,File, UploadFile, Depends
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from module._base import CONFIG_PATH,STATIC_PATH,DEFAULT_MAIN_CONFIG,SopConfig,get_models_path,JsonFile,get_main_config,DEFAULT_RESOLUTIONS,ConfigUpdater,DEFAULT_BOX_STYLE_CONFIG,DEFAULT_HAND_STYLE_CONFIG
from module._config_encryptor import ConfigEncryptor
from module._model_archive import (
    MAX_MODEL_ARCHIVE_BYTES,
    ModelAlreadyExistsError,
    ModelArchiveError,
    install_model_archive,
)
from module._auth import clear_sessions, has_admin_user, require_admin
from module._step_feedback import validate_sop_step_feedback_config
from module._box_style import normalize_area_fill_alpha
from module._hand_detection import HandTracker
from module._hand_style import normalize_hand_style_config
from module._result_media import (
    normalize_result_media_config,
    validate_result_media_config,
)
from module._result_storage import (
    get_result_storage_status,
    sync_local_results,
)
from module._manual_regions import (
    find_manual_region_references,
    normalize_manual_region_profile,
    normalize_manual_regions_config,
    refresh_sop_manual_region_reference_names,
    validate_sop_manual_region_references,
)
from module._sop_config import (
    normalize_sop_name,
    upsert_sop_definition,
)
from datetime import datetime
from pydantic import BaseModel, Field
from pymodbus.client import ModbusTcpClient
logger = logging.getLogger(__name__)
api_config = APIRouter(dependencies=[Depends(require_admin)])
api_config_public = APIRouter()
config_encryptor = ConfigEncryptor()
MAX_CONFIG_UPLOAD_BYTES = 10 * 1024 * 1024


def _configuration_integer(value, field_name: str) -> int:
    """将json中的值转换为整数，避免小数被截断"""
    if isinstance(value, bool):raise ValueError(f"{field_name} must be an integer.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer.") from None
    if not np.isfinite(number) or not number.is_integer():
        raise ValueError(f"{field_name} must be an integer.")
    return int(number)


def _validate_resolution_dimensions(width_value, height_value) -> tuple[int, int]:
    """验证分辨率的宽高是否合法"""
    width = _configuration_integer(width_value, "width")
    height = _configuration_integer(height_value, "height")
    if width < 320 or height < 240:
        raise ValueError("Resolution must be at least 320x240.")
    if width % 2 or height % 2:
        raise ValueError("Resolution width and height must be even numbers.")
    aspect_ratio = width / height
    if aspect_ratio < 0.5 or aspect_ratio > 2.5:
        raise ValueError("Resolution aspect ratio must be between 0.5 and 2.5.")
    return width, height


def _normalize_camera_resolution(body: dict, resolutions: list) -> tuple[str, dict]:
    """验证并规范化摄像头分辨率等相关配置"""
    cap_name = str(body.get("cap_name") or "").strip()
    if not cap_name:raise ValueError("Camera name is required.")
    width, height = _validate_resolution_dimensions(body.get("width"),body.get("height"))
    if [width, height] not in resolutions:raise ValueError("The selected resolution is not in the resolution list.")
    area = _configuration_integer(body.get("area", 0), "area")
    clarity = _configuration_integer(body.get("clarity", 50), "clarity")
    if area < 0 or (0 < area < 240):raise ValueError("Display area must be 0 or at least 240.")
    if area > max(width, height):raise ValueError(f"Display area cannot exceed {max(width, height)} for this resolution.")
    if area % 2:raise ValueError("Display area must be an even number.")
    if clarity < 1 or clarity > 100: raise ValueError("Display clarity must be between 1 and 100.")
    return cap_name, {"width": width,"height": height,"area": area,"clarity": clarity}


def _hand_preview_points() -> dict[str, list[tuple[float, float]]]:
    left_points = [
        (155, 300),
        (125, 270), (102, 240), (88, 210), (82, 180),
        (142, 250), (138, 205), (136, 160), (134, 115),
        (165, 245), (165, 192), (165, 140), (165, 92),
        (187, 250), (193, 205), (198, 163), (202, 125),
        (207, 260), (220, 225), (231, 195), (240, 168),
    ]
    right_points = [(640 - x, y) for x, y in left_points]
    return {"l": left_points, "r": right_points}


def _normalize_imported_main_config(config_data: object) -> dict:
    """验证并规范化导入的主配置"""
    if not isinstance(config_data, dict):raise ValueError("Main configuration must contain a JSON object.")
    normalized = ConfigUpdater(deepcopy(DEFAULT_MAIN_CONFIG)).update(deepcopy(config_data))
    account_login = normalized.get("accountLogin")
    if not isinstance(account_login,dict) or not isinstance(account_login.get("enabled"),bool):raise ValueError("accountLogin.enabled must be a boolean.")
    if account_login["enabled"] and not has_admin_user():raise ValueError("At least one administrator is required before importing a configuration with account login enabled.")
    paths = normalized.get("paths")
    if not isinstance(paths, dict):raise ValueError("paths must be an object.")
    for field_name in ("modelPath", "sopPath", "resultPath"):
        value = paths.get(field_name)
        if not isinstance(value, str):raise ValueError(f"paths.{field_name} must be a string.")
        paths[field_name] = value.strip()
    if not isinstance(paths.get("saveDetectionDatasets"), bool):raise ValueError("paths.saveDetectionDatasets must be a boolean.")
    raw_resolutions = normalized.get("resolutions")
    if not isinstance(raw_resolutions, list) or not raw_resolutions:raise ValueError("resolutions must be a non-empty array.")
    resolutions: list[list[int]] = []
    for index, resolution in enumerate(raw_resolutions):
        if not isinstance(resolution, (list, tuple)) or len(resolution) != 2:raise ValueError(f"resolutions[{index}] must contain width and height.")
        width, height = _validate_resolution_dimensions(resolution[0],resolution[1] )
        if [width, height] not in resolutions:
            resolutions.append([width, height])
    normalized["resolutions"] = resolutions
    raw_camera_resolutions = normalized.get("cameraResolution")
    if not isinstance(raw_camera_resolutions, dict):raise ValueError("cameraResolution must be an object.")
    camera_resolutions = {}
    for camera_name, camera_config in raw_camera_resolutions.items():
        if not isinstance(camera_config, dict):raise ValueError(f"cameraResolution.{camera_name} must be an object.")
        normalized_camera_name, normalized_camera_config = (_normalize_camera_resolution({"cap_name": camera_name,**camera_config,}, resolutions,))
        camera_resolutions[normalized_camera_name] = normalized_camera_config
    normalized["cameraResolution"] = camera_resolutions
    enable_camera = normalized.get("enableCamera")
    if enable_camera is not None and not isinstance(enable_camera, str):raise ValueError("enableCamera must be a string or null.")
    box_style = normalized.get("boxStyle")
    if not isinstance(box_style, dict):raise ValueError("boxStyle must be an object.")
    box_style["areaFillAlpha"] = normalize_area_fill_alpha(box_style.get("areaFillAlpha"),DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"],)
    normalized["handStyle"] = normalize_hand_style_config(normalized.get("handStyle"),DEFAULT_HAND_STYLE_CONFIG,strict=True)
    normalized["manualRegions"] = normalize_manual_regions_config( normalized.get("manualRegions"),strict=True)
    integration_error = validate_detection_integration_config(normalized)
    if integration_error:raise ValueError(integration_error)
    media_error = validate_result_media_config(normalized)
    if media_error:raise ValueError(media_error)
    normalized["resultMedia"] = normalize_result_media_config(normalized.get("resultMedia"),strict=True)
    return normalized

def _normalize_imported_sop_config(config_data: object) -> dict:
    """验证并规范化导入的SOP配置"""
    if not isinstance(config_data, dict):raise ValueError("SOP configuration must contain a JSON object.")
    normalized = deepcopy(config_data)
    enabled_count = 0
    main_config = get_main_config()
    manual_regions = main_config.get("manualRegions")
    for raw_sop_name, definition in normalized.items():
        sop_name = normalize_sop_name(raw_sop_name)
        if sop_name != raw_sop_name:raise ValueError(f"SOP name '{raw_sop_name}' contains leading or trailing spaces.")
        if not isinstance(definition, dict):raise ValueError(f"SOP '{sop_name}' must be an object.")
        if not str(definition.get("model") or "").strip():raise ValueError(f"SOP '{sop_name}' model is required.")
        if not isinstance(definition.get("steps"), list):raise ValueError(f"SOP '{sop_name}' steps must be an array.")
        if definition.get("enabled") is True:
            enabled_count += 1
        manual_region_error = validate_sop_manual_region_references( {sop_name: definition}, manual_regions,)
        if manual_region_error:raise ValueError(manual_region_error)
        feedback_error = validate_sop_step_feedback_config(definition,main_config)
        if feedback_error: raise ValueError(f"SOP '{sop_name}': {feedback_error}")
    if enabled_count > 1:raise ValueError("Only one SOP configuration may be enabled.")
    return normalized


def _managed_config_path(config_type: str) -> tuple[str, str]:
    if config_type == "main":return CONFIG_PATH, "config.enc"
    if config_type == "sop":return SopConfig().sop_config_path, "sop_config.enc"
    raise HTTPException(status_code=404, detail="Unsupported configuration type.")

def _safe_unlink(file_path: str) -> None:
    """安全删除文件，忽略文件不存在的情况"""
    try:os.unlink(file_path)
    except FileNotFoundError:pass


def _atomic_write_json(target_path: str, config_data: dict) -> str | None:
    """原子性地写入JSON文件，如果目标文件已存在，则创建备份"""
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_path: str | None = None
    if target.exists():
        backup_dir = Path(STATIC_PATH) / "backup" / "config_import"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_name = (
            f"{target.stem}_{datetime.now().strftime('%Y%m%d%H%M%S')}_"
            f"{uuid.uuid4().hex[:8]}{target.suffix}.bak"
        )
        backup_path = str(backup_dir / backup_name)
        shutil.copy2(target, backup_path)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp",) as temp_file:
            temp_path = temp_file.name
            json.dump(config_data, temp_file, ensure_ascii=False, indent=4)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, target)
        temp_path = ""
        return backup_path
    finally:
        if temp_path:
            _safe_unlink(temp_path)


async def _read_limited_upload(file: UploadFile,maximum_bytes: int,) -> bytes:
    """读取上传的文件内容，限制最大字节数"""
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > maximum_bytes:raise ValueError(f"Uploaded file exceeds the {maximum_bytes // (1024 * 1024)} MB limit.")
        chunks.append(chunk)
    return b"".join(chunks)


@api_config.get("/get_config")
def get_config():
    config_datas = get_main_config()
    sop_config = SopConfig()
    sop_config_datas = sop_config.get()
    if "resolutions" not in config_datas:
        config_datas["resolutions"] = DEFAULT_RESOLUTIONS
    return JSONResponse(content={"status": True, "datas": config_datas,"sops":sop_config_datas})


@api_config.get("/config-files/{config_type}/download")
async def download_configuration_file(config_type: str):
    temp_encrypted_path = ""
    try:
        source_path, download_name = _managed_config_path(config_type)
        if not os.path.isfile(source_path):raise HTTPException(status_code=404,detail="Configuration file does not exist.")
        with tempfile.NamedTemporaryFile(delete=False,suffix=".enc") as temp_file:
            temp_encrypted_path = temp_file.name
        config_encryptor.encrypt_file(source_path=source_path,target_path=temp_encrypted_path,method="aes_like")
        return FileResponse(
            path=temp_encrypted_path,
            filename=download_name,
            media_type="application/octet-stream",
            headers={"X-Encryption-Method": "aes_like"},
            background=BackgroundTask(_safe_unlink,temp_encrypted_path),
        )
    except HTTPException:
        if temp_encrypted_path:
            _safe_unlink(temp_encrypted_path)
        raise
    except Exception as exc:
        if temp_encrypted_path:
            _safe_unlink(temp_encrypted_path)
        logger.exception("Failed to download %s configuration: %s",config_type,exc)
        raise HTTPException(status_code=500,detail="Failed to download configuration file.") from exc


@api_config.post("/config-files/{config_type}/upload")
async def upload_configuration_file(config_type: str,file: UploadFile = File(...),):
    try:
        _managed_config_path(config_type)
        filename = os.path.basename(str(file.filename or "").replace("\\", "/"))
        suffix = Path(filename).suffix.lower()
        if suffix not in {".json", ".enc"}:return JSONResponse({"status": False, "code": "INVALID_CONFIG_FILE_TYPE", "msg": "Only .json and .enc configuration files are allowed."})
        content = await _read_limited_upload(file, MAX_CONFIG_UPLOAD_BYTES,)
        if not content:raise ValueError("Uploaded configuration file is empty.")
        if suffix == ".json":
            config_data = json.loads(content.decode("utf-8-sig"))
        else:
            config_data = config_encryptor.decrypt_config_from_memory(content,method="aes_like",)["data"]
        if config_type == "main":
            config_data = _normalize_imported_main_config(config_data)
        else:
            config_data = _normalize_imported_sop_config(config_data)
        target_path, _ = _managed_config_path(config_type)
        backup_path = _atomic_write_json(target_path, config_data)
        if config_type == "main":clear_sessions()
        return JSONResponse({"status": True, "msg": "Configuration file imported successfully.", "data": {"configType": config_type, "sourceFilename": filename, "backupCreated": backup_path is not None, "backupFilename": (Path(backup_path).name if backup_path else None),},})
    except (UnicodeDecodeError,json.JSONDecodeError,ValueError) as exc:
        return JSONResponse({"status": False, "code": "INVALID_CONFIG_FILE", "msg": str(exc),})  
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to import %s configuration: %s",config_type,exc)
        return JSONResponse({"status": False,"code": "CONFIG_IMPORT_FAILED","msg": f"Failed to import configuration file: {exc}",})
    finally:
        await file.close()


@api_config.post("/models/upload")
async def upload_model_archive(file: UploadFile = File(...),overwrite: bool = False,):
    temp_archive_path = ""
    try:
        filename = os.path.basename(str(file.filename or "").replace("\\", "/"))
        if Path(filename).suffix.lower() != ".zip":return JSONResponse({"status": False,"code": "INVALID_MODEL_PACKAGE","msg": "Only ZIP model packages are allowed.",})
        with tempfile.NamedTemporaryFile(delete=False,suffix=".zip") as temp_archive:
            temp_archive_path = temp_archive.name
            total_bytes = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_MODEL_ARCHIVE_BYTES:raise ModelArchiveError("Model package exceeds the 1 GB upload limit.")
                temp_archive.write(chunk)
            temp_archive.flush()
            os.fsync(temp_archive.fileno())
        if total_bytes == 0:raise ModelArchiveError("Uploaded model package is empty.")
        result = await run_in_threadpool(install_model_archive,temp_archive_path,filename,get_models_path(),overwrite=overwrite)
        return JSONResponse({"status": True,"msg": "Model package imported successfully.","data": result,})
    except ModelAlreadyExistsError as exc:
        return JSONResponse({"status": False,"code": "MODEL_ALREADY_EXISTS","msg": str(exc),"data": {"modelName": exc.model_name},})
    except ModelArchiveError as exc:
        return JSONResponse({"status": False,"code": "INVALID_MODEL_PACKAGE","msg": str(exc),})
    except Exception as exc:
        logger.exception("Failed to import model package: %s", exc)
        return JSONResponse({"status": False,"code": "MODEL_IMPORT_FAILED","msg": f"Failed to import model package: {exc}",})
    finally:
        await file.close()
        if temp_archive_path:
            _safe_unlink(temp_archive_path)


@api_config.post("/manual_regions/save")
async def save_manual_regions(request: Request):
    """手动绘制的固定区域的接口"""
    try:
        body = await request.json()
        if not isinstance(body, dict): raise ValueError("Invalid manual region request.")
        camera_name = str(body.get("cameraName") or "").strip()
        if not camera_name:raise ValueError("Camera name is required.")
        profile = normalize_manual_region_profile(
            {
                "referenceWidth": body.get("referenceWidth"),
                "referenceHeight": body.get("referenceHeight"),
                "regions": body.get("regions"),
            },
            strict=True,
        )
        config_datas = get_main_config()
        manual_regions = normalize_manual_regions_config(config_datas.get("manualRegions"))
        cameras = manual_regions.setdefault("cameras", {})
        previous_profile = cameras.get(camera_name, {"regions": []})
        previous_ids = {
            str(region.get("id") or "")
            for region in previous_profile.get("regions", [])
            if isinstance(region, dict)
        }
        next_ids = {str(region.get("id") or "") for region in profile["regions"]}

        sop_config = SopConfig()
        sop_map = sop_config.get()
        for removed_id in sorted(previous_ids - next_ids):
            references = find_manual_region_references(sop_map,camera_name=camera_name,region_id=removed_id)
            if references:return JSONResponse({"status": False,"msg": f"Manual region '{removed_id}' is still referenced by SOP steps: {', '.join(references)}","references": references,})
        cameras[camera_name] = profile
        manual_regions = normalize_manual_regions_config(manual_regions,strict=True)
        manual_region_error = validate_sop_manual_region_references(sop_map,manual_regions)
        if manual_region_error:return JSONResponse({"status": False,"msg": manual_region_error,})
        config_datas["manualRegions"] = manual_regions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        refreshed_sops, changed = refresh_sop_manual_region_reference_names(sop_map,manual_regions)
        if changed:
            sop_config.set(refreshed_sops)
        return JSONResponse({"status": True,"msg": "Manual regions saved successfully.","datas": manual_regions,"sops": refreshed_sops,"applyMode": "next_detection_start",})
    except ValueError as exc:
        return JSONResponse(content={"status": False, "msg": str(exc)})
    except Exception:
        logger.exception("Failed to save manual regions")
        return JSONResponse({"status": False,"msg": "Failed to save manual regions.",})


@api_config.delete("/manual_regions/delete")
async def delete_manual_region(request: Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):raise ValueError("Invalid manual region request.")
        camera_name = str(body.get("cameraName") or "").strip()
        region_id = str(body.get("regionId") or "").strip()
        if not camera_name or not region_id:raise ValueError("cameraName and regionId are required.")
        sop_config = SopConfig()
        sop_map = sop_config.get()
        references = find_manual_region_references(sop_map,camera_name=camera_name,region_id=region_id)
        if references:return JSONResponse({"status": False,"msg": f"Manual region is still referenced by SOP steps: {', '.join(references)}","references": references,})
        config_datas = get_main_config()
        manual_regions = normalize_manual_regions_config(config_datas.get("manualRegions"))
        profile = manual_regions["cameras"].get(camera_name)
        if profile is None:return JSONResponse({"status": False,"msg": f"Manual region camera '{camera_name}' was not found.",})
        before_count = len(profile["regions"])
        profile["regions"] = [region for region in profile["regions"] if region.get("id") != region_id]
        if len(profile["regions"]) == before_count:return JSONResponse({"status": False,"msg": f"Manual region '{region_id}' was not found.",})
        config_datas["manualRegions"] = manual_regions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse({"status": True,"msg": "Manual region deleted successfully.","datas": manual_regions,})
    except ValueError as exc:
        return JSONResponse(content={"status": False, "msg": str(exc)})
    except Exception:
        logger.exception("Failed to delete manual region")
        return JSONResponse({"status": False,"msg": "Failed to delete manual region.",})
@api_config.post("/set_box_style_config")
async def set_box_style_config(request: Request):
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        area_fill_alpha = box_style_config.get("areaFillAlpha",DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"])
        try:
            area_fill_alpha = float(area_fill_alpha)
        except (TypeError, ValueError):
            return JSONResponse(content={"status": False, "msg": "areaFillAlpha must be a number between 0 and 1"})
        if not np.isfinite(area_fill_alpha) or not 0 <= area_fill_alpha <= 1:
            return JSONResponse(content={"status": False, "msg": "areaFillAlpha must be between 0 and 1"})
        box_style_config = {
            **box_style_config,
            "areaFillAlpha": round(area_fill_alpha, 2),
        }
        config_datas = get_main_config()
        config_datas["boxStyle"] = box_style_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse(content={"status": True, "msg": "Box style configuration set successfully"})
    except Exception as e:
        logger.exception(f"Error setting box style configuration: {e}")
        return JSONResponse(content={"status": False, "msg": "Failed to set box style configuration"})
@api_config.post("/display_box_style_config")
async def display_box_style_config(request: Request):
    try:
        body = await request.json()
        box_style_config = body.get("boxStyle")
        if not box_style_config:return JSONResponse(content={"status": False, "msg": "Missing boxStyle parameter"})
        box_thickness = box_style_config.get("boxThickness", 3)
        font_thickness = box_style_config.get("fontThickness", 2)
        font_scale = box_style_config.get("fontScale", 0.5)
        from_area_fill = box_style_config.get("fromAreaFill", False)
        target_area_fill = box_style_config.get("targetAreaFill", False)
        area_fill_alpha = normalize_area_fill_alpha(
            box_style_config.get("areaFillAlpha"),
            DEFAULT_BOX_STYLE_CONFIG["areaFillAlpha"],
        )
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (150,150), (0, 255, 0), thickness=box_thickness)
        (textSizeW, textSizeH), baseline = cv2.getTextSize('Example', cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
        cv2.putText(img, 'Example', (50, 50-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness=font_thickness, lineType=cv2.LINE_AA)
        overlay = img.copy()
        if from_area_fill:
            cv2.rectangle(overlay, (200, 50), (300,150), (0, 255, 255), thickness=cv2.FILLED)
        if target_area_fill:
            cv2.rectangle(overlay, (50, 250), (150,350), (0, 0, 255), thickness=cv2.FILLED)
        if from_area_fill or target_area_fill:
            cv2.addWeighted(overlay,area_fill_alpha,img,1.0 - area_fill_alpha,0,dst=img)
        cv2.rectangle(img, (200, 50), (300,150), (0, 255, 255), thickness=box_thickness)
        cv2.putText(img, 'Start', (200, 50-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 255), thickness=font_thickness, lineType=cv2.LINE_AA)
        cv2.rectangle(img, (50, 250), (150,350), (0, 0, 255), thickness=box_thickness)
        cv2.putText(img, 'Target', (50, 250-textSizeH), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness=font_thickness, lineType=cv2.LINE_AA)
        _, img_encoded = cv2.imencode('.webp', img, [int(cv2.IMWRITE_WEBP_QUALITY), 90])
        img_base64 = base64.b64encode(img_encoded).decode('utf-8')
        result_img = f"data:image/webp;base64,{img_base64}"
        return JSONResponse({"status": True, "frame": result_img, "msg": "Example image generated successfully"})
    except Exception as e:
        logger.exception(f"Error displaying box style configuration: {e}")
        return JSONResponse(content={"status": False, "msg": "Failed to display box style configuration"})


@api_config.post("/set_hand_style_config")
async def set_hand_style_config(request: Request):
    try:
        body = await request.json()
        hand_style_config = body.get("handStyle")
        if not isinstance(hand_style_config, dict):return JSONResponse({"status": False, "msg": "Missing handStyle parameter"})
        try:
            hand_style_config = normalize_hand_style_config(hand_style_config,DEFAULT_HAND_STYLE_CONFIG,strict=True)
        except ValueError as exc:
            return JSONResponse(content={"status": False, "msg": str(exc)})
        config_datas = get_main_config()
        config_datas["handStyle"] = hand_style_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return JSONResponse({"status": True, "msg": "Hand style configuration set successfully", "datas": hand_style_config})
    except Exception as exc:
        logger.exception(f"Error setting hand style configuration: {exc}")
        return JSONResponse({"status": False, "msg": "Failed to set hand style configuration"})
            
@api_config.post("/display_hand_style_config")
async def display_hand_style_config(request: Request):
    try:
        body = await request.json()
        hand_style_config = body.get("handStyle")
        if not isinstance(hand_style_config, dict):return JSONResponse({"status": False, "msg": "Missing handStyle parameter"})
        try:
            hand_style_config = normalize_hand_style_config(hand_style_config, DEFAULT_HAND_STYLE_CONFIG,strict=True)
        except ValueError as exc:
            return JSONResponse(content={"status": False, "msg": str(exc)})
        image = np.full((360, 640, 3), 32, dtype=np.uint8)
        cv2.putText(image,"LEFT HAND",(95, 38),cv2.FONT_HERSHEY_SIMPLEX,0.75,(230, 230, 230),2,lineType=cv2.LINE_AA)
        cv2.putText(image,"RIGHT HAND",(405, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.75,(230, 230, 230),2,lineType=cv2.LINE_AA)
        HandTracker.draw_hands(image,_hand_preview_points(),hand_style_config)
        encoded, buffer = cv2.imencode(".webp",image,[int(cv2.IMWRITE_WEBP_QUALITY), 90])
        if not encoded:raise RuntimeError("Failed to encode hand style preview")
        frame = f"data:image/webp;base64,{base64.b64encode(buffer).decode('utf-8')}"
        return JSONResponse({"status": True, "frame": frame, "msg": "Hand style preview generated successfully"})
    except Exception as exc:
        logger.exception(f"Error displaying hand style configuration: {exc}")
        return JSONResponse({"status": False, "msg": "Failed to display hand style configuration"})


@api_config.get("/open_models_folder")
def open_models_folder():
    try:
        models_path = get_models_path()
        if not os.path.exists(models_path):
            os.makedirs(models_path)
        os.startfile(models_path)
        return JSONResponse({"status":True})
    except Exception as e:
        logger.exception(f"Error opening models folder")
        return JSONResponse(content={"status":False,"msg":"Failed to open models folder"})
@api_config.get("/get_models")
def get_models():
    try:
        models_path = get_models_path()
        os.makedirs(models_path, exist_ok=True)
        model_status = {}
        for model_dir in os.listdir(models_path):
            model_folder = os.path.join(models_path, model_dir)
            if os.path.isdir(model_folder):
                onnx_file = None
                for file in os.listdir(model_folder):
                    if file.lower().endswith(".onnx"):
                        onnx_file = os.path.join(model_folder, file)
                        break
                cache_file = os.path.join(model_folder, "cache.json")
                model_status[model_dir] = (
                    bool(onnx_file)
                    and os.path.exists(onnx_file)
                    and os.path.exists(cache_file)
                )
        return JSONResponse(content={"status":True,"datas": model_status})
    except Exception as e:
        logger.exception("Error getting models")
        return JSONResponse(content={"status":False,"msg":"Failed to getting model"})
@api_config.delete("/delete_model")
async def delete_model(request: Request):
    data = await request.json()
    model = data.get("model")
    try:
        if not model:return JSONResponse(content={"status":False,"msg":"Missing model parameter"})
        referenced_by = [
            sop_name
            for sop_name, definition in SopConfig().get().items()
            if isinstance(definition, dict) and definition.get("model") == model
        ]
        if referenced_by:return JSONResponse({"status": False, "msg": f"Model '{model}' is still referenced by SOP: " + ", ".join(referenced_by)})
        models_path = get_models_path()
        model_folder = os.path.join(models_path, model)
        if not os.path.exists(model_folder):return JSONResponse(content={"status":True,"msg":"Model folder does not exist"})
        # 删除模型文件夹及其内容
        for root, dirs, files in os.walk(model_folder, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(model_folder)
        return JSONResponse(content={"status":True,"msg":"Successfully deleted model folder"})
    except Exception as e:
        logger.exception(f"Error deleting model folder: {model}")
        return JSONResponse(content={"status":False,"msg":"Failed to delete model folder"})
@api_config.get("/model/labels")
def get_model_labels(model: str):
    try:
        labels = {}
        model_folder = os.path.join(get_models_path(), model)
        if not os.path.exists(model_folder):
            logger.error(f"Model folder does not exist: {model_folder}")
            return JSONResponse(content={"status":False,"msg":"Model folder does not exist"})
        label_file = os.path.join(model_folder, "cache.json")
        if not os.path.exists(label_file):
            logger.error(f"Label file does not exist: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Label file does not exist"})
        cache_datas = JsonFile(label_file).read_json_file()
        if not cache_datas:
            logger.error(f"Cache data is empty: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Label file data is empty"})
        labels = cache_datas.get("labeling")
        if not labels:
            logger.error(f"Labeling data is empty: {label_file}")
            return JSONResponse(content={"status":False,"msg":"Labeling data is empty"})
        return JSONResponse(content={"status":True,"datas": labels})
    except Exception as e:
        logger.exception(f"Error getting model labels")
        return JSONResponse(content={"status":False,"msg":"Failed to getting model labels"})
@api_config.post("/model/labels/set")
async def set_model_labels(request: Request):
    try:
        data = await request.json()
        model = data.get("model")
        labels = data.get("labels")
        if not model or not labels or len(labels) == 0:
            logger.error(f"Missing model or labels: {model}, {labels}")
            return JSONResponse(content={"status":False,"msg":"Missing parameters"})
        model_folder = os.path.join(get_models_path(), model)
        if not os.path.exists(model_folder):
            return JSONResponse(content={"status":False,"msg":"Model does not exist"})
        label_file = os.path.join(model_folder, "cache.json")
        json_file = JsonFile(label_file)
        cache_datas = json_file.read_json_file()
        cache_datas['labeling'] = labels
        json_file.write_json_file(cache_datas)
        return JSONResponse(content={"status":True,"msg":"Successfully set model labels"})
    except Exception as e:
        logger.exception(f"Error setting model labels")
        return JSONResponse(content={"status":False,"msg":"Failed to set model labels"})
@api_config.post("/set_config/paths")
async def set_config_paths(request: Request):
    try:
        data = await request.json()
        model_path = data.get("modelPath")
        results_path = data.get("resultPath")
        sops_path =data.get("sopPath")
        save_datasets = data.get("saveDetectionDatasets", False)
        if model_path and not os.path.exists(model_path):
            try:
                os.makedirs(model_path)
            except Exception as e:
                logger.error(f"Failed to create model path: {model_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"Model path is not available"})
        if sops_path and not os.path.exists(sops_path):
            try:
                os.makedirs(sops_path)
            except Exception as e:
                logger.error(f"Failed to create sops path: {sops_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"SOP path is not available"})
        if results_path and not os.path.exists(results_path):
            try:
                os.makedirs(results_path)
            except Exception as e:
                logger.error(f"Failed to create results path: {results_path}, error: {e}")
                return JSONResponse(content={"status":False,"msg":"Results path is not available"})
        config_data = get_main_config()
        config_data["paths"] = {
            "modelPath": model_path,
            "sopPath": sops_path,
            "resultPath": results_path,
            "saveDetectionDatasets": save_datasets
        }
        json_file = JsonFile(CONFIG_PATH)
        json_file.write_json_file(config_data)
        return JSONResponse(content={"status":True,"msg":"Successfully set paths"})
    except Exception as e:
        logger.exception(f"Error setting config paths")
        return JSONResponse(content={"status":False,"msg":"Failed to set paths"})
    
@api_config.post("/set_cap_resolutions")
async def set_cap_resolutions(request: Request):
    cap_name = ""
    try:
        body = await request.json()
        if not isinstance(body, dict):return {"status": False,"msg":"Invalid request body."}
        config_datas = get_main_config()
        resolutions = config_datas.get("resolutions",DEFAULT_RESOLUTIONS,)
        cap_name,resolution_config = _normalize_camera_resolution(body,resolutions )
        camera_resolutions = config_datas.setdefault("cameraResolution",{})

        camera_resolutions[cap_name] = resolution_config
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {
            "status": True,
            "msg":"Camera settings saved. They will take effect the next time the camera starts.",
            "data":resolution_config,
            "applyMode":"next_start",
        }
    except ValueError as e:
        return { "status": False,"msg": str(e)}
    except Exception as e:
        logger.exception(f"Error setting camera resolutions for {cap_name}")
        return {"status": False,"msg": str(e)}
@api_config.post("/set_resolutions/list")
async def set_resolutions_list(request:Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return {"status": False, "msg": "Invalid request body."}
        width, height = _validate_resolution_dimensions(
            body.get("width"),
            body.get("height"),
        )
        config_datas = get_main_config()
        resolutions = config_datas.get("resolutions", [])
        newResolution = [width, height]
        if newResolution in resolutions:return {"status": False, "msg": "Resolution already exists."}
        #将新的分辨率按宽度从小到大插入到resolutions中
        inserted = False
        for i, res in enumerate(resolutions):
            if newResolution[0] < res[0]:
                resolutions.insert(i, newResolution)
                inserted = True
                break
        if not inserted:
            resolutions.append(newResolution)
        config_datas["resolutions"] = resolutions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {"status": True, "msg": "Resolutions set successfully.","data":resolutions}
    except ValueError as e:
        return {"status": False, "msg": str(e)}
    except Exception as e:
        logger.exception("Error setting resolutions")
        return {"status": False, "msg": str(e)}
@api_config.delete("/delete_resolution/list")
async def delete_resolution_list(request:Request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return {"status": False, "msg": "Invalid request body."}
        width, height = _validate_resolution_dimensions(
            body.get("width"),
            body.get("height"),
        )
        config_datas = get_main_config()
        resolutions = config_datas.get("resolutions", [])
        targetResolution = [width, height]
        if targetResolution not in resolutions:return {"status": False, "msg": "Resolution not found."}
        camera_resolutions = config_datas.get("cameraResolution", {})
        used_by = [
            camera_name
            for camera_name, camera_config in camera_resolutions.items()
            if isinstance(camera_config, dict)
            and camera_config.get("width") == width
            and camera_config.get("height") == height
        ]
        if used_by:return {"status": False,"msg": "Resolution is currently used by camera(s): " + ", ".join(used_by)}
        resolutions.remove(targetResolution)
        config_datas["resolutions"] = resolutions
        JsonFile(CONFIG_PATH).write_json_file(config_datas)
        return {"status": True, "msg": "Resolution deleted successfully.","data":resolutions}
    except ValueError as e:
        return {"status": False, "msg": str(e)}
    except Exception as e:
        logger.exception("Error deleting resolution")
        return {"status": False, "msg": str(e)}
@api_config.post("/set_sop_config")
async def set_sop_config(request:Request):
    try:
        body = await request.json()
        sop_config = SopConfig()
        sop_config_datas = sop_config.get()
        sop_config_datas, sop_name, definition = upsert_sop_definition(
            sop_config_datas,
            body,
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        model_name = definition["model"]
        if not os.path.isdir(os.path.join(get_models_path(), model_name)):
            return {"status": False,"msg": f"Model folder '{model_name}' was not found."}
        main_config = get_main_config()
        manual_region_error = validate_sop_manual_region_references(definition, main_config.get("manualRegions"))
        if manual_region_error:return {"status": False, "msg": manual_region_error}
        validation_error = validate_sop_step_feedback_config(definition,main_config )
        if validation_error:return {"status": False, "msg": validation_error}
        sop_config.set(sop_config_datas)
        return {"status": True,"datas": sop_config_datas,"sopName": sop_name,"msg": "SOP configuration set successfully."}
    except ValueError as e:
        return {"status": False, "msg": str(e)}
    except Exception as e:
        logger.exception(f"Error setting SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
@api_config.delete("/delete_sop_config")
async def delete_sop_config(request:Request):
    try:
        body = await request.json()
        sop_name = normalize_sop_name(body.get("sopName", body.get("model")))
        sop_config = SopConfig()
        sop_config_datas = sop_config.get()
        if not sop_config_datas or sop_name not in sop_config_datas:
            return { "status": False,"msg": f"SOP configuration '{sop_name}' was not found."}
        del sop_config_datas[sop_name]
        sop_config.set(sop_config_datas)
        return {"status": True,"datas": sop_config_datas,"msg": "SOP configuration deleted successfully."}
    except ValueError as e:
        return {"status": False, "msg": str(e)}
    except Exception as e:
        logger.exception(f"Error deleting SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
@api_config.post("/update_sop_config")
async def update_sop_config(request:Request):
    try:
        body = await request.json()
        sop_name = normalize_sop_name(body.get("sopName", body.get("model")))
        fields = body.get("fields", [])
        values = body.get("values", [])
        if not fields or not values or len(fields) != len(values):return {"status": False, "msg": "Fields and values must be provided and have the same length."}
        sop_config_datas = SopConfig().get()
        if not sop_config_datas or sop_name not in sop_config_datas:
            return {"status": False, "msg": f"SOP configuration '{sop_name}' was not found."}
        for field, value in zip(fields, values):
            sop_config_datas[sop_name][field] = value
            if field == "enabled" and value is True:
                for other_sop_name in sop_config_datas:
                    if other_sop_name != sop_name:
                        sop_config_datas[other_sop_name]["enabled"] = False
        SopConfig().set(sop_config_datas)
        return {"status": True,"datas": sop_config_datas,"msg": "SOP configuration updated successfully."}
    except ValueError as e:
        return {"status": False, "msg": str(e)}
    except Exception as e:
        logger.exception(f"Error updating SOP configuration: {e}")
        return {"status": False, "msg": str(e)}
MAX_RESULT_FEEDBACK_ENDPOINTS = 5
MAX_HTTP_TRIGGER_PARAMETERS = 3
MAX_MODBUS_TRIGGER_SIGNALS = 3
MODBUS_BIT_TYPES = {"coil", "discreteInput"}
MODBUS_REGISTER_TYPES = {"holdingRegister", "inputRegister"}


def _is_integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_detection_integration_config(body: dict) -> str:
    """验证 触发和反馈配置的有效性。"""
    integration = body.get("detectionIntegration")
    if integration is None: return ""
    if not isinstance(integration, dict): return "detectionIntegration must be an object"
    triggers = integration.get("triggers")
    if triggers is not None:
        if not isinstance(triggers, dict):return "detectionIntegration.triggers must be an object"
        http_parameters = triggers.get("httpParameters")
        if http_parameters is not None:
            if not isinstance(http_parameters, list):return "triggers.httpParameters must be an array"
            if len(http_parameters) > MAX_HTTP_TRIGGER_PARAMETERS:return f"A maximum of {MAX_HTTP_TRIGGER_PARAMETERS} HTTP trigger parameters is allowed"
            parameter_names = set()
            for parameter in http_parameters:
                if not isinstance(parameter, str):return "Each HTTP trigger parameter must be a string"
                name = parameter.strip()
                if not name:return "HTTP trigger parameter name cannot be empty"
                if name in parameter_names:return "HTTP trigger parameter names must be unique"
                parameter_names.add(name)
        if triggers.get("httpApi") is True and not http_parameters:
            return "At least one HTTP trigger parameter is required when HTTP API trigger is enabled"
        scanner_length = triggers.get("usbScannerLength")
        if scanner_length is not None:
            if not isinstance(scanner_length, dict):return "triggers.usbScannerLength must be an object"
            min_length = scanner_length.get("min")
            max_length = scanner_length.get("max")
            if not _is_integer(min_length) or not _is_integer(max_length):return "USB scanner minimum and maximum lengths must be integers"
            if min_length < 1 or max_length < min_length or max_length > 9999:return "USB scanner length requires 1 <= min <= max <= 9999"
        modbus_signals = triggers.get("modbusSignals")
        if modbus_signals is not None:
            if not isinstance(modbus_signals, list):return "triggers.modbusSignals must be an array"
            if len(modbus_signals) > MAX_MODBUS_TRIGGER_SIGNALS:return f"A maximum of {MAX_MODBUS_TRIGGER_SIGNALS} Modbus trigger signals is allowed"
            for signal in modbus_signals:
                if not isinstance(signal, dict):return "Each Modbus trigger signal must be an object"
                slave_address = signal.get("slaveAddress")
                address = signal.get("address")
                data_type = signal.get("dataType")
                trigger_value = signal.get("triggerValue")
                if not _is_integer(slave_address) or not 1 <= slave_address <= 247:return "Modbus slave address must be an integer between 1 and 247"
                if not _is_integer(address) or not 0 <= address <= 65535:return "Modbus trigger address must be an integer between 0 and 65535"
                if data_type in MODBUS_BIT_TYPES:
                    if not isinstance(trigger_value, bool):return "Modbus coil and discrete input trigger values must be boolean"
                elif data_type in MODBUS_REGISTER_TYPES:
                    if not _is_integer(trigger_value) or not 0 <= trigger_value <= 65535:return "Modbus register trigger value must be an integer between 0 and 65535"
                else:return "Unsupported Modbus data type"
        if triggers.get("modbus") is True and not modbus_signals:
            return "At least one Modbus trigger signal is required when Modbus trigger is enabled"
    result_feedback = integration.get("resultFeedback")
    if result_feedback is None:return ""
    if not isinstance(result_feedback, dict):return "resultFeedback must be an object"
    endpoints = result_feedback.get("endpoints")
    if endpoints is None:return ""
    if not isinstance(endpoints, list):return "resultFeedback.endpoints must be an array"
    if len(endpoints) > MAX_RESULT_FEEDBACK_ENDPOINTS:return f"A maximum of {MAX_RESULT_FEEDBACK_ENDPOINTS} result feedback endpoints is allowed"
    if any(not isinstance(endpoint, dict) for endpoint in endpoints):return "Each result feedback endpoint must be an object"
    return ""

@api_config.post("/modify_config") 
async def modify_config(request:Request):
    """_summary_:通用配置更新接口，
    需要保证和配置的框架一致，否则会导致配置文件错乱

    Args:
        request (Request): body = await request.json()

    Returns:
        _type_: _description_
    """
    try:
        body = await request.json()
        if not isinstance(body, dict):
            return {"status": False, "msg": "Configuration payload must be an object"}
        if "accountLogin" in body:return {"status": False,"msg": "Please change account login through User Management"}
        validation_error = validate_detection_integration_config(body)
        if validation_error:
            return {"status": False, "msg": validation_error}
        validation_error = validate_result_media_config(body)
        if validation_error:
            return {"status": False, "msg": validation_error}
        if "resultMedia" in body:
            body["resultMedia"] = normalize_result_media_config(body["resultMedia"],strict=True)
        updater = ConfigUpdater(get_main_config())
        updated_config = updater.update(body)
        JsonFile(CONFIG_PATH).write_json_file(updated_config)
        return {"status": True, "msg": "Configuration modified successfully."}
    except Exception as e:
        logger.error(f"Error modifying configuration: {e}")
        return {"status": False, "msg": str(e)}


@api_config.get("/result_storage/status")
def result_storage_status():
    """反馈当前结果存储的状态，包括是否可用、路径、剩余空间等信息。"""
    try:
        return {"status": True,"data": get_result_storage_status(),}
    except Exception as exc:
        logger.exception("Failed to read result storage status")
        return {"status": False, "msg": str(exc)}


@api_config.post("/result_storage/sync")
def result_storage_sync():
    """
    检测是否有因为网络异常导致结果没有正常上传到网盘的结果。
    FastAPI 在其工作线程池中运行此同步端点，因此网络和
    SQLite I/O 不会阻塞 asyncio 事件循环或检测线程。
    """
    try:
        summary = sync_local_results()
        return {
            "status": summary["failedRunCount"] == 0,
            "msg": (
                "Local results synchronized successfully"
                if summary["failedRunCount"] == 0
                else "Some local results could not be synchronized"
            ),
            "data": summary,
        }
    except Exception as exc:
        logger.exception("Failed to synchronize local results")
        return {"status": False, "msg": str(exc)}


class ModbusConnectionRequest(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    timeout: float = Field(gt=0, le=60)
@api_config.post("/modbus/test_connection")
def test_modbus_connection(payload: ModbusConnectionRequest):
    """测试指定地址能否建立 Modbus TCP 连接，不读取任何寄存器。"""
    host = payload.host.strip()
    if not host:return JSONResponse(content={"status": False, "msg": "Modbus host is required"})
    client = ModbusTcpClient(host=host,port=payload.port,timeout=payload.timeout)
    try:
        if client.connect():return JSONResponse(content={"status": True,"msg": f"Connected to Modbus TCP server {host}:{payload.port}",})
        return JSONResponse(content={"status": False,"msg": f"Unable to connect to Modbus TCP server {host}:{payload.port}"})
    except Exception as exc:
        logger.exception("Failed to test Modbus TCP connection to %s:%s", host, payload.port)
        return JSONResponse(content={"status": False, "msg": str(exc)})
    finally:
        try:
            client.close()
        except Exception:
            logger.exception("Failed to close Modbus TCP test client")

@api_config_public.post("/http/response_test")
async def http_response_test(request: Request):
    """测试 HTTP 响应，返回请求的 JSON 数据和状态码。"""
    try:
        body = await request.json()
        print("body",body)
        return JSONResponse(content={"status": True, "msg": "HTTP response test successful", "data": body})
    except Exception as e:
        logger.error(f"Error in HTTP response test: {e}")
        return JSONResponse(content={"status": False, "msg": str(e)})
