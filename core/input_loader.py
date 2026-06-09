"""Unified input loading: PDF and image files → list[PageImage]."""

from __future__ import annotations

from pathlib import Path

from core.image_loader import load_image_page
from core.models import PageImage
from core.pdf_renderer import render_pdf_pages

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
}

IMAGE_EXTENSIONS = SUPPORTED_EXTENSIONS - {".pdf"}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def input_type_for(path: Path) -> str:
    return "pdf" if path.suffix.lower() == ".pdf" else "image"


def load_pages(path: Path, *, dpi: int = 150) -> list[PageImage]:
    """PDF → multi-page render; image → single-page list."""
    path = Path(path).resolve()
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文件类型: {ext}")

    if ext == ".pdf":
        return render_pdf_pages(path, dpi=dpi)

    arr, w, h = load_image_page(path)
    return [
        PageImage(
            image=arr,
            page_index=0,
            source_path=path,
            width=w,
            height=h,
        )
    ]


def scan_folder(
    folder: Path,
    *,
    recursive: bool = False,
) -> list[Path]:
    """Collect supported invoice files from a directory."""
    folder = Path(folder).resolve()
    if not folder.is_dir():
        return []

    paths: list[Path] = []
    pattern = "**/*" if recursive else "*"
    for p in sorted(folder.glob(pattern)):
        if p.is_file() and is_supported(p):
            paths.append(p)
    return paths
