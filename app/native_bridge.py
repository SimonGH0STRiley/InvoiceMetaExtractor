"""Native file dialogs for pywebview js_api."""

from __future__ import annotations

from pathlib import Path
from typing import List

SUPPORTED_GLOB = ("*.pdf", "*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp", "*.tif", "*.tiff")

FILE_DIALOG_TYPES = [
    ("PDF 与图片", " ".join(SUPPORTED_GLOB)),
    ("PDF", "*.pdf"),
    ("图片", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
]


class NativeBridge:
    """Exposed to frontend via pywebview js_api."""

    def select_paths(self) -> List[str]:
        """Multi-select PDF/image invoice files."""
        return self._pick_files()

    def select_files(self) -> List[str]:
        """Alias for multi-select files."""
        return self._pick_files()

    def _pick_files(self) -> List[str]:
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError:
            return []

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        paths = filedialog.askopenfilenames(
            title="选择发票文件（PDF/图片，可多选）",
            filetypes=FILE_DIALOG_TYPES,
        )
        root.destroy()
        return list(paths)

    def open_export_folder(self, path: str) -> None:
        import os

        p = Path(path)
        target = p.parent if p.is_file() else p
        if target.exists():
            os.startfile(str(target))  # noqa: S606 — Windows only
