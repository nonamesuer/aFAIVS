from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import threading
import uuid
import zipfile
from pathlib import PurePosixPath

MAX_MODEL_ARCHIVE_BYTES = 1024 * 1024 * 1024
MAX_MODEL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MODEL_ARCHIVE_FILES = 10
MAX_COMPRESSION_RATIO = 250
MAX_MODEL_NAME_LENGTH = 100

MODEL_ARCHIVE_PATTERN = re.compile(r"^(?:[A-Za-z0-9])?FAIVSModel[^_]+_(?P<project>[\w.-]+)_(?P<timestamp>\d{14})\.zip$",re.IGNORECASE | re.UNICODE,)
MODEL_NAME_PATTERN = re.compile(r"^[\w.-]+$", re.UNICODE)
WINDOWS_RESERVED_NAMES = {"CON","PRN","AUX","NUL",*(f"COM{index}" for index in range(1, 10)),*(f"LPT{index}" for index in range(1, 10)),}
MODEL_INSTALL_LOCK = threading.Lock()
class ModelArchiveError(ValueError):
    pass

class ModelAlreadyExistsError(ModelArchiveError):
    def __init__(self, model_name: str):
        super().__init__(f"Model '{model_name}' already exists")
        self.model_name = model_name
def normalize_model_name(value: str) -> str:
    model_name = str(value or "").strip()
    if not model_name:raise ModelArchiveError("Model project name is missing")
    if len(model_name) > MAX_MODEL_NAME_LENGTH:raise ModelArchiveError(f"Model project name must not exceed {MAX_MODEL_NAME_LENGTH} characters")
    if model_name in {".", ".."} or model_name.endswith((".", " ")) or not MODEL_NAME_PATTERN.fullmatch(model_name):
        raise ModelArchiveError(
            "Model project name may contain only letters, numbers, "
            "underscores, hyphens and periods"
        )
    if model_name.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        raise ModelArchiveError("Model project name is reserved by Windows")
    return model_name


def model_name_from_archive_filename(filename: str) -> str:
    safe_filename = os.path.basename(
        str(filename or "").replace("\\", "/")
    )
    match = MODEL_ARCHIVE_PATTERN.fullmatch(safe_filename)
    if match is None:
        raise ModelArchiveError(
            "Invalid model package filename. Expected "
            "[prefix]FAIVSModel{model_times_name}_{project_name}_YYYYMMDDHHMMSS.zip"
        )
    return normalize_model_name(match.group("project"))

def _validate_member(member: zipfile.ZipInfo) -> PurePosixPath:
    member_name = member.filename.replace("\\", "/")
    path = PurePosixPath(member_name)
    if (
        not member_name
        or member_name.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or ":" in path.parts[0]
    ):
        raise ModelArchiveError(f"Unsafe ZIP entry: {member.filename}")
    mode = member.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise ModelArchiveError("Symbolic links are not allowed in model packages")
    return path


def _validate_archive(
    archive: zipfile.ZipFile,
) -> tuple[zipfile.ZipInfo, zipfile.ZipInfo]:
    members = [member for member in archive.infolist() if not member.is_dir()]
    if not members:
        raise ModelArchiveError("Model package is empty")
    if len(members) > MAX_MODEL_ARCHIVE_FILES:
        raise ModelArchiveError(f"Model package may contain at most {MAX_MODEL_ARCHIVE_FILES} files")

    total_size = 0
    onnx_members: list[zipfile.ZipInfo] = []
    cache_members: list[zipfile.ZipInfo] = []
    for member in members:
        path = _validate_member(member)
        total_size += member.file_size
        if total_size > MAX_MODEL_UNCOMPRESSED_BYTES:
            raise ModelArchiveError("Uncompressed model package is too large")
        if member.compress_size == 0 and member.file_size:
            raise ModelArchiveError("Invalid compressed model entry")
        if (
            member.compress_size
            and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise ModelArchiveError("Model package compression ratio is unsafe")

        filename = path.name
        if filename.lower() == "cache.json":
            cache_members.append(member)
        elif filename.lower().endswith(".onnx"):
            onnx_members.append(member)
        else:
            raise ModelArchiveError(
                "Model package may contain only one ONNX file and cache.json"
            )

    if len(onnx_members) != 1:
        raise ModelArchiveError(
            "Model package must contain exactly one ONNX file"
        )
    if len(cache_members) != 1:
        raise ModelArchiveError(
            "Model package must contain exactly one cache.json"
        )
    if onnx_members[0].file_size <= 0:
        raise ModelArchiveError("ONNX model file is empty")
    return onnx_members[0], cache_members[0]


def _copy_archive_member(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    target_path: str,
) -> None:
    with archive.open(member, "r") as source, open(target_path, "wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)
        target.flush()
        os.fsync(target.fileno())


def _install_model_archive(archive_path: str,original_filename: str,models_path: str,*,overwrite: bool = False,) -> dict:
    model_name = model_name_from_archive_filename(original_filename)
    os.makedirs(models_path, exist_ok=True)
    models_root = os.path.abspath(models_path)
    destination = os.path.abspath(os.path.join(models_root, model_name))
    if os.path.commonpath([models_root, destination]) != models_root:
        raise ModelArchiveError("Invalid model destination")
    if os.path.lexists(destination):
        if os.path.islink(destination):
            raise ModelArchiveError("Existing model path is a symbolic link")
        if not os.path.isdir(destination):
            raise ModelArchiveError(
                "Existing model path is not a directory"
            )
        if not overwrite:
            raise ModelAlreadyExistsError(model_name)

    work_root = tempfile.mkdtemp(prefix=".model-upload-", dir=models_root)
    staged_model = os.path.join(work_root, "model")
    os.makedirs(staged_model)
    backup_path = ""
    try:
        try:
            archive = zipfile.ZipFile(archive_path, "r")
        except zipfile.BadZipFile as exc:
            raise ModelArchiveError("Uploaded file is not a valid ZIP package") from exc
        with archive:
            onnx_member, cache_member = _validate_archive(archive)
            onnx_name = PurePosixPath(
                onnx_member.filename.replace("\\", "/")
            ).name
            onnx_path = os.path.join(staged_model, onnx_name)
            cache_path = os.path.join(staged_model, "cache.json")
            _copy_archive_member(archive, onnx_member, onnx_path)
            _copy_archive_member(archive, cache_member, cache_path)

        try:
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                cache_data = json.load(cache_file)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelArchiveError("cache.json is not valid UTF-8 JSON") from exc
        if not isinstance(cache_data, dict):
            raise ModelArchiveError("cache.json must contain a JSON object")
        labeling = cache_data.get("labeling")
        if not isinstance(labeling, dict) or not labeling:
            raise ModelArchiveError(
                "cache.json must contain a non-empty labeling object"
            )

        if os.path.lexists(destination):
            backup_path = os.path.join(
                models_root,
                f".{model_name}.backup-{uuid.uuid4().hex}",
            )
            os.replace(destination, backup_path)
        try:
            os.replace(staged_model, destination)
        except Exception:
            if backup_path and os.path.exists(backup_path):
                os.replace(backup_path, destination)
                backup_path = ""
            raise
        if backup_path:
            shutil.rmtree(backup_path)
            backup_path = ""

        return {
            "modelName": model_name,
            "onnxFile": onnx_name,
            "labelCount": len(labeling),
            "overwritten": overwrite,
        }
    finally:
        if backup_path and os.path.exists(backup_path):
            if not os.path.exists(destination):
                os.replace(backup_path, destination)
            else:
                shutil.rmtree(backup_path)
        shutil.rmtree(work_root, ignore_errors=True)


def install_model_archive(archive_path: str,original_filename: str, models_path: str,*,overwrite: bool = False,) -> dict:
    """Serialize installs so two uploads cannot replace the same model at once."""
    with MODEL_INSTALL_LOCK:
        return _install_model_archive(archive_path,original_filename, models_path,overwrite=overwrite)
