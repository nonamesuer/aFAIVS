from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from module._base import STATIC_PATH, SopConfig


MAX_AUDIO_FILE_BYTES = 20 * 1024 * 1024
AUDIO_RESOURCE_ID_PATTERN = re.compile(r"^audio_[0-9a-f]{32}$")
AUDIO_RESOURCE_DIR = os.path.join(STATIC_PATH, "audio_resources")
AUDIO_RESOURCE_MANIFEST = os.path.join(AUDIO_RESOURCE_DIR, "audio_resources.json")
SUPPORTED_AUDIO_EXTENSIONS = {".mp3": "audio/mpeg", ".wav": "audio/wav"}
_LOCK = threading.RLock()


def _now_iso() -> str:return datetime.now(timezone.utc).isoformat()


def _ensure_storage() -> None:
    os.makedirs(AUDIO_RESOURCE_DIR,exist_ok=True)
    if not os.path.isfile(AUDIO_RESOURCE_MANIFEST):_write_manifest_unlocked({"version":1,"resources":[]})


def _read_manifest_unlocked() -> dict[str,Any]:
    _ensure_storage()
    try:
        with open(AUDIO_RESOURCE_MANIFEST,"r",encoding="utf-8") as file:data = json.load(file)
    except (OSError,json.JSONDecodeError) as exc:raise ValueError("Unable to read the audio resource manifest") from exc
    resources = data.get("resources",[]) if isinstance(data,dict) else []
    if not isinstance(resources,list):raise ValueError("Invalid audio resource manifest structure")
    return {"version":1,"resources":[deepcopy(item) for item in resources if isinstance(item,dict)]}


def _write_manifest_unlocked(data: dict[str,Any]) -> None:
    os.makedirs(AUDIO_RESOURCE_DIR,exist_ok=True);temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",delete=False,dir=AUDIO_RESOURCE_DIR,prefix=".audio_resources.",suffix=".tmp") as file:temp_path = file.name;json.dump(data,file,ensure_ascii=False,indent=4);file.flush();os.fsync(file.fileno())
        os.replace(temp_path,AUDIO_RESOURCE_MANIFEST);temp_path = ""
    finally:
        if temp_path and os.path.exists(temp_path):os.unlink(temp_path)


def _validate_audio_content(extension: str,content: bytes) -> None:
    if not content:raise ValueError("The uploaded audio file is empty")
    if len(content) > MAX_AUDIO_FILE_BYTES:raise ValueError(f"Audio file exceeds the {MAX_AUDIO_FILE_BYTES // (1024 * 1024)} MB limit")
    if extension == ".wav" and not (len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE"):raise ValueError("The uploaded file is not a valid WAV file")
    if extension == ".mp3" and not (content[:3] == b"ID3" or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)):raise ValueError("The uploaded file is not a valid MP3 file")


def _normalize_display_name(value: Any,original_name: str) -> str:
    name = str(value or "").strip() or Path(original_name).stem.strip()
    if not name:raise ValueError("Audio resource name is required")
    if len(name) > 80:raise ValueError("Audio resource name must not exceed 80 characters")
    return name


def _audio_references(audio_id: str,sop_config: dict[str,Any] | None = None) -> list[dict[str,Any]]:
    references: list[dict[str,Any]] = []
    for sop_name,definition in (sop_config if isinstance(sop_config,dict) else SopConfig().get()).items():
        if not isinstance(definition,dict):continue
        completion_audio = (definition.get("sopCompletionFeedback") or {}).get("audio",{})
        if isinstance(completion_audio,dict) and completion_audio.get("audioId") == audio_id:references.append({"sopName":sop_name,"scope":"sop_completed","stepId":None,"stepName":""})
        for step in definition.get("steps",[]):
            if not isinstance(step,dict):continue
            audio = (((step.get("context") or {}).get("resultFeedback") or {}).get("audio") or {})
            if not isinstance(audio,dict):continue
            if audio.get("errorAudioId") == audio_id:references.append({"sopName":sop_name,"scope":"operation_error","stepId":step.get("id"),"stepName":step.get("name") or ""})
            if audio.get("completionAudioId") == audio_id:references.append({"sopName":sop_name,"scope":"step_success","stepId":step.get("id"),"stepName":step.get("name") or ""})
    return references


def list_audio_resources(*,include_references: bool = False) -> list[dict[str,Any]]:
    with _LOCK:resources = _read_manifest_unlocked()["resources"]
    sop_config = SopConfig().get() if include_references else None
    result = []
    for resource in resources:
        item = deepcopy(resource);item["fileAvailable"] = os.path.isfile(os.path.join(AUDIO_RESOURCE_DIR,str(item.get("fileName") or "")))
        if include_references:item["references"] = _audio_references(str(item.get("id") or ""),sop_config)
        result.append(item)
    return sorted(result,key=lambda item:str(item.get("createdAt") or ""),reverse=True)


def audio_resource_ids() -> set[str]:return {str(item.get("id")) for item in list_audio_resources() if item.get("id") and item.get("fileAvailable")}


def get_audio_resource(audio_id: str) -> dict[str,Any]:
    if not AUDIO_RESOURCE_ID_PATTERN.fullmatch(str(audio_id or "")):raise ValueError("Invalid audio resource ID")
    resource = next((item for item in list_audio_resources() if item.get("id") == audio_id),None)
    if resource is None:raise FileNotFoundError("Audio resource was not found")
    return resource


def get_audio_resource_file(audio_id: str) -> tuple[str,dict[str,Any]]:
    resource = get_audio_resource(audio_id);file_path = os.path.abspath(os.path.join(AUDIO_RESOURCE_DIR,str(resource.get("fileName") or "")))
    if os.path.commonpath([os.path.abspath(AUDIO_RESOURCE_DIR),file_path]) != os.path.abspath(AUDIO_RESOURCE_DIR):raise ValueError("Invalid audio resource path")
    if not os.path.isfile(file_path):raise FileNotFoundError("Audio resource file was not found")
    return file_path,resource


def create_audio_resource(filename: str,content: bytes,display_name: Any = "") -> dict[str,Any]:
    original_name = os.path.basename(str(filename or "").strip());extension = Path(original_name).suffix.lower()
    if extension not in SUPPORTED_AUDIO_EXTENSIONS:raise ValueError("Only MP3 and WAV audio files are allowed")
    _validate_audio_content(extension,content);name = _normalize_display_name(display_name,original_name);audio_id = f"audio_{uuid.uuid4().hex}";stored_name = f"{audio_id}{extension}";file_path = os.path.join(AUDIO_RESOURCE_DIR,stored_name);temp_path = "";now = _now_iso()
    resource = {"id":audio_id,"name":name,"fileName":stored_name,"originalName":original_name,"mimeType":SUPPORTED_AUDIO_EXTENSIONS[extension],"extension":extension[1:],"size":len(content),"createdAt":now,"updatedAt":now}
    with _LOCK:
        _ensure_storage()
        try:
            with tempfile.NamedTemporaryFile(mode="wb",delete=False,dir=AUDIO_RESOURCE_DIR,prefix=f".{audio_id}.",suffix=".tmp") as file:temp_path = file.name;file.write(content);file.flush();os.fsync(file.fileno())
            os.replace(temp_path,file_path);temp_path = "";manifest = _read_manifest_unlocked();manifest["resources"].append(resource);_write_manifest_unlocked(manifest)
        except Exception:
            if os.path.isfile(file_path):os.unlink(file_path)
            raise
        finally:
            if temp_path and os.path.exists(temp_path):os.unlink(temp_path)
    return deepcopy(resource)


def rename_audio_resource(audio_id: str,name: Any) -> dict[str,Any]:
    with _LOCK:
        manifest = _read_manifest_unlocked();resource = next((item for item in manifest["resources"] if item.get("id") == audio_id),None)
        if resource is None:raise FileNotFoundError("Audio resource was not found")
        resource["name"] = _normalize_display_name(name,str(resource.get("originalName") or "audio"));resource["updatedAt"] = _now_iso();_write_manifest_unlocked(manifest);return deepcopy(resource)


def delete_audio_resource(audio_id: str) -> None:
    references = _audio_references(audio_id)
    if references:raise RuntimeError(f"Audio resource is referenced by {len(references)} SOP feedback configuration(s)")
    with _LOCK:
        manifest = _read_manifest_unlocked();resource = next((item for item in manifest["resources"] if item.get("id") == audio_id),None)
        if resource is None:raise FileNotFoundError("Audio resource was not found")
        manifest["resources"] = [item for item in manifest["resources"] if item.get("id") != audio_id];_write_manifest_unlocked(manifest);file_path = os.path.join(AUDIO_RESOURCE_DIR,str(resource.get("fileName") or ""))
        if os.path.isfile(file_path):os.unlink(file_path)
