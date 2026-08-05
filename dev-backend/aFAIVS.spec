# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_submodules,
    get_package_paths,
)


block_cipher = None


# ============================================================
# 项目目录
# ============================================================

# aFAIVS.spec 所在目录，也就是 dev-backend
BACKEND_DIR = Path(SPECPATH).resolve()

# aFAIVS 项目根目录
PROJECT_DIR = BACKEND_DIR.parent

# Vue / Electron 前端目录
FRONTEND_DIR = PROJECT_DIR / "dev-frontend"


def require_path(
    path: Path,
    description: str,
) -> Path:
    """
    在开始打包前检查必要文件。

    避免打包成功后运行时才发现文件缺失。
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{description}不存在：{path}"
        )

    return path


# ============================================================
# 必要应用文件
# ============================================================

MAIN_FILE = require_path(
    BACKEND_DIR / "main.py",
    "后端入口文件",
)

ICON_FILE = require_path(
    BACKEND_DIR / "aFAIVS.ico",
    "程序图标文件",
)

VERSION_FILE = require_path(
    BACKEND_DIR / "version.txt",
    "版本信息文件",
)

FRONTEND_DIST = require_path(
    FRONTEND_DIR / "dist",
    "Vue 构建目录",
)

ELECTRON_DIST = require_path(
    FRONTEND_DIR
    / "out"
    / "afaivs-win32-x64",
    "Electron 构建目录",
)


# ============================================================
# MediaPipe HandLandmarker 模型
# ============================================================

HAND_LANDMARKER_MODEL = require_path(
    BACKEND_DIR
    / "lib"
    / "hand_landmarker.task",
    "MediaPipe 手部模型",
)


# ============================================================
# MediaPipe 0.10.35 动态库
# ============================================================

# 返回 mediapipe 安装目录，例如：
#
# C:\...\venv\Lib\site-packages\mediapipe
#
_, mediapipe_package_dir = get_package_paths(
    "mediapipe"
)

MEDIAPIPE_PACKAGE_DIR = Path(
    mediapipe_package_dir
).resolve()

MEDIAPIPE_C_DIR = (
    MEDIAPIPE_PACKAGE_DIR
    / "tasks"
    / "c"
)

MEDIAPIPE_DLL = require_path(
    MEDIAPIPE_C_DIR
    / "libmediapipe.dll",
    "MediaPipe C 动态库",
)


# ============================================================
# MediaPipe 隐式导入
# ============================================================

# mediapipe.tasks.c 是通过：
#
# importlib.resources.files("mediapipe.tasks.c")
#
# 动态导入的，PyInstaller 无法通过普通 import 分析发现。
mediapipe_hiddenimports = [
    "mediapipe.tasks.c",

    "mediapipe.tasks.python.core.mediapipe_c_bindings",

    "mediapipe.tasks.python.vision.hand_landmarker",

    "mediapipe.tasks.python.vision.core.image",

    "mediapipe.tasks.python.vision.core.image_processing_options",

    "mediapipe.tasks.python.vision.core.vision_task_running_mode",
]


# 收集 MediaPipe Tasks Vision 和 Core 的内部模块。
#
# 这样即使 MediaPipe 后续在模块内部使用动态导入，
# 也不会因为少一个纯 Python 子模块而再次失败。
mediapipe_hiddenimports += collect_submodules(
    "mediapipe.tasks.python.core"
)

mediapipe_hiddenimports += collect_submodules(
    "mediapipe.tasks.python.vision"
)

mediapipe_hiddenimports = sorted(
    set(mediapipe_hiddenimports)
)


# ============================================================
# 二进制文件
# ============================================================

added_binaries = [
    # 必须保持这个目标目录。
    #
    # MediaPipe 运行时会查找：
    #
    # mediapipe/tasks/c/libmediapipe.dll
    (
        str(MEDIAPIPE_DLL),
        "mediapipe/tasks/c",
    ),
]


# ============================================================
# 数据文件
# ============================================================

added_datas = [
    # Vue 静态文件
    (
        str(FRONTEND_DIST),
        "static/dist",
    ),

    # Electron 文件
    (
        str(ELECTRON_DIST),
        "static/afaivs-win32-x64",
    ),

    # MediaPipe 手部模型
    #
    # _base.py 中的运行路径是：
    #
    # PARENT_DIR/lib/hand_landmarker.task
    (
        str(HAND_LANDMARKER_MODEL),
        "lib",
    ),
]


# ============================================================
# Analysis
# ============================================================

a = Analysis(
    [str(MAIN_FILE)],

    pathex=[
        str(BACKEND_DIR),
    ],

    binaries=added_binaries,

    datas=added_datas,

    hiddenimports=mediapipe_hiddenimports,

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[],

    win_no_prefer_redirects=False,

    win_private_assemblies=False,

    cipher=block_cipher,

    noarchive=False,
)


# ============================================================
# PYZ
# ============================================================

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)


# ============================================================
# EXE
# ============================================================

exe = EXE(
    pyz,

    a.scripts,

    [],

    exclude_binaries=True,

    name="aFAIVS",

    # 调试阶段保留 True。
    # 正式发布确认没有问题后可以改成 False。
    debug=True,

    bootloader_ignore_signals=False,

    strip=False,

    upx=True,

    console=True,

    disable_windowed_traceback=False,

    target_arch=None,

    codesign_identity=None,

    entitlements_file=None,

    icon=str(ICON_FILE),

    version=str(VERSION_FILE),
)


# ============================================================
# COLLECT
# ============================================================

coll = COLLECT(
    exe,

    a.binaries,

    a.zipfiles,

    a.datas,

    strip=False,

    upx=True,

    upx_exclude=[],

    name="AI VISION EXPAND",
)