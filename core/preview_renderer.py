"""High-quality preview rendering from original PDF pages or image files."""

from __future__ import annotations

import io
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageOps

from core.image_loader import _apply_exif_orientation

PREVIEW_DPI = 200
MAX_PREVIEW_EDGE = 4096


def _fit_max_edge(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    return img.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))),
        Image.Resampling.LANCZOS,
    )


def _encode_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _render_pdf_page(path: Path, page_index: int, *, dpi: int) -> Image.Image:
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    doc = fitz.open(path)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise ValueError("页码超出范围")
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()


def _load_image_original(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img = _apply_exif_orientation(img)
        return img.convert("RGB")


def count_preview_pages(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        doc = fitz.open(path)
        try:
            return len(doc)
        finally:
            doc.close()
    return 1


def render_preview(
    path: Path,
    *,
    page_index: int = 0,
    max_edge: int = 1600,
    dpi: int = PREVIEW_DPI,
) -> tuple[bytes, str, int, int, int]:
    """
    Render preview PNG from source file.

    Returns: (png_bytes, mime, width, height, page_total)
    """
    path = Path(path).resolve()
    max_edge = min(max(max_edge, 64), MAX_PREVIEW_EDGE)
    ext = path.suffix.lower()

    if ext == ".pdf":
        page_total = count_preview_pages(path)
        img = _render_pdf_page(path, page_index, dpi=dpi)
    else:
        page_total = 1
        if page_index != 0:
            raise ValueError("页码超出范围")
        img = _load_image_original(path)

    img = _fit_max_edge(img, max_edge)
    w, h = img.size
    return _encode_png(img), "image/png", w, h, page_total
