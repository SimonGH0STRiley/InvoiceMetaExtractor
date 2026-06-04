"""Invoice metadata extraction pipeline (OCR + layout-aware semantic extraction)."""

from core.models import InvoiceRecord, OcrBlock, PageImage

__all__ = [
    "InvoiceRecord",
    "OcrBlock",
    "PageImage",
    "process_file",
    "process_batch",
]


def __getattr__(name: str):
    if name in ("process_file", "process_batch"):
        from core.pipeline import process_batch, process_file

        return process_file if name == "process_file" else process_batch
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
