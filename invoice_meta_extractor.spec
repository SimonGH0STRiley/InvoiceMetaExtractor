# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


ROOT = Path(SPECPATH)
APP_NAME = "InvoiceMetaExtractor"
ICON_PATH = ROOT / "frontend" / "public" / "icons" / "app-icon.ico"


def _add_tree(relative_path: str) -> list[tuple[str, str]]:
    source = ROOT / relative_path
    if not source.exists():
        return []
    return [(str(source), relative_path)]


def _add_file(relative_path: str, dest: str = ".") -> list[tuple[str, str]]:
    source = ROOT / relative_path
    if not source.is_file():
        return []
    return [(str(source), dest)]


def _safe_collect_data(package: str) -> list[tuple[str, str]]:
    try:
        return collect_data_files(package)
    except Exception:
        return []


def _safe_collect_dlls(package: str) -> list[tuple[str, str]]:
    try:
        return collect_dynamic_libs(package)
    except Exception:
        return []


def _safe_collect_submodules(package: str) -> list[str]:
    try:
        return collect_submodules(package)
    except Exception:
        return []


def _safe_copy_metadata(package: str) -> list[tuple[str, str]]:
    try:
        return copy_metadata(package)
    except Exception:
        return []


datas = []
datas += _add_tree("web")
datas += _add_tree("assets")
datas += _add_file("README.md")
datas += _safe_collect_data("rapidocr_onnxruntime")
datas += _safe_collect_data("onnxruntime")

for metadata_package in (
    "fastapi",
    "numpy",
    "onnxruntime",
    "openpyxl",
    "Pillow",
    "PyMuPDF",
    "pywebview",
    "python-multipart",
    "rapidocr-onnxruntime",
    "uvicorn",
):
    datas += _safe_copy_metadata(metadata_package)


binaries = []
for binary_package in (
    "onnxruntime",
    "rapidocr_onnxruntime",
    "fitz",
):
    binaries += _safe_collect_dlls(binary_package)


hiddenimports = [
    "api.server",
    "app.launcher",
    "app.native_bridge",
    "core.pipeline",
    "fastapi",
    "fitz",
    "numpy",
    "onnxruntime",
    "openpyxl",
    "PIL",
    "PIL.Image",
    "rapidocr_onnxruntime",
    "starlette",
    "uvicorn",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]

for submodule_package in (
    "api",
    "app",
    "core",
    "rapidocr_onnxruntime",
    "uvicorn",
    "webview",
):
    hiddenimports += _safe_collect_submodules(submodule_package)


a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["node_modules", "tests", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    exclude_binaries=False,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON_PATH),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
