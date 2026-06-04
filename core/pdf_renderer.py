"""Render PDF pages to raster images via PyMuPDF."""

from __future__ import annotations

from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from core.models import PageImage


def render_pdf_pages(path: Path, *, dpi: int = 200) -> list[PageImage]:
    """Render all PDF pages to RGB PageImage list."""
    pages: list[PageImage] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    doc = fitz.open(path)
    try:
        for i in range(len(doc)):
            page = doc.load_page(i)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            # pix.samples is RGB bytes
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            pages.append(
                PageImage(
                    image=img.copy(),
                    page_index=i,
                    source_path=path,
                    width=pix.width,
                    height=pix.height,
                )
            )
    finally:
        doc.close()

    return pages


def pixmap_to_pil(pix: fitz.Pixmap) -> Image.Image:
    """Utility: convert pixmap to PIL (debug / export)."""
    mode = "RGB" if pix.n < 4 else "RGBA"
    return Image.frombytes(mode, (pix.width, pix.height), pix.samples)
