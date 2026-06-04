"""RapidOCR wrapper — unified OcrBlock output, offline models."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

import numpy as np

from core.models import OcrBlock, PageImage

# Project root (for bundled assets when frozen)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ASSETS_MODELS = _PROJECT_ROOT / "assets" / "models"
_DLL_DIRECTORY_HANDLES = []


def _resource_root() -> Path:
    """PyInstaller _MEIPASS or project root."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return _PROJECT_ROOT


def _default_model_dir() -> Path | None:
    root = _resource_root()
    candidates = [
        root / "assets" / "models",
        _ASSETS_MODELS,
    ]
    for d in candidates:
        if d.is_dir() and any(d.iterdir()):
            return d
    return None


def _prepare_onnxruntime_dlls() -> None:
    if sys.platform != "win32":
        return

    root = _resource_root()
    capi_dir = root / "onnxruntime" / "capi"
    if not capi_dir.is_dir():
        return

    search_dirs = [root, capi_dir]
    dll_names = ["onnxruntime_providers_shared.dll", "onnxruntime.dll"]
    if hasattr(os, "add_dll_directory"):
        for directory in search_dirs:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))
    os.environ["PATH"] = os.pathsep.join(
        [str(directory) for directory in search_dirs] + [os.environ.get("PATH", "")]
    )
    for dll_name in dll_names:
        dll_path = capi_dir / dll_name
        if dll_path.is_file():
            try:
                ctypes.WinDLL(str(dll_path))
            except OSError:
                # onnxruntime may still load the DLL through its Python extension.
                pass


class OcrEngine:
    """Local OCR using rapidocr-onnxruntime."""

    def __init__(self, *, model_dir: Path | None = None) -> None:
        self._engine = None
        self._model_dir = model_dir or _default_model_dir()

    def _ensure_engine(self) -> None:
        if self._engine is not None:
            return
        _prepare_onnxruntime_dlls()
        from rapidocr_onnxruntime import RapidOCR

        kwargs: dict = {}
        if self._model_dir:
            det = self._model_dir / "ch_PP-OCRv4_det_infer.onnx"
            rec = self._model_dir / "ch_PP-OCRv4_rec_infer.onnx"
            cls = self._model_dir / "ch_ppocr_mobile_v2.0_cls_infer.onnx"
            if det.is_file():
                kwargs["det_model_path"] = str(det)
            if rec.is_file():
                kwargs["rec_model_path"] = str(rec)
            if cls.is_file():
                kwargs["cls_model_path"] = str(cls)

        # RapidOCR downloads to user cache on first run if paths omitted;
        # for fully offline bundle, place ONNX files under assets/models/.
        self._engine = RapidOCR(**kwargs)

    def run_on_page(self, page: PageImage) -> list[OcrBlock]:
        """OCR one page image."""
        self._ensure_engine()
        result, _ = self._engine(page.image)
        blocks: list[OcrBlock] = []
        if not result:
            return blocks

        for item in result:
            if len(item) < 3:
                continue
            box_pts, text, score = item[0], item[1], float(item[2])
            text = (text or "").strip()
            if not text:
                continue
            box = [(float(x), float(y)) for x, y in box_pts]
            blocks.append(
                OcrBlock(
                    text=text,
                    box=box,
                    score=score,
                    page_index=page.page_index,
                )
            )
        return blocks

    def run_on_pages(self, pages: list[PageImage]) -> list[OcrBlock]:
        """OCR all pages and merge blocks (page_index preserved)."""
        all_blocks: list[OcrBlock] = []
        for page in pages:
            all_blocks.extend(self.run_on_page(page))
        return all_blocks


_default_engine: OcrEngine | None = None


def get_ocr_engine() -> OcrEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = OcrEngine()
    return _default_engine


def run_ocr(pages: list[PageImage], engine: OcrEngine | None = None) -> list[OcrBlock]:
    eng = engine or get_ocr_engine()
    return eng.run_on_pages(pages)
