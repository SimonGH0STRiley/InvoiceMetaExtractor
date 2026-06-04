"""Load image files with EXIF orientation correction and size limits."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

MAX_EDGE = 4096


def _apply_exif_orientation(img: Image.Image) -> Image.Image:
    try:
        return ImageOps.exif_transpose(img)
    except Exception:
        return img


def _resize_if_needed(img: Image.Image, max_edge: int = MAX_EDGE) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / longest
    new_size = (int(w * scale), int(h * scale))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def load_image_array(path: Path, *, max_edge: int = MAX_EDGE) -> np.ndarray:
    """Read image file → RGB uint8 numpy array."""
    with Image.open(path) as img:
        img = _apply_exif_orientation(img)
        img = img.convert("RGB")
        img = _resize_if_needed(img, max_edge)
        return np.asarray(img, dtype=np.uint8)


def load_image_page(path: Path, page_index: int = 0) -> tuple[np.ndarray, int, int]:
    """Return (rgb_array, width, height)."""
    arr = load_image_array(path)
    h, w = arr.shape[:2]
    return arr, w, h
