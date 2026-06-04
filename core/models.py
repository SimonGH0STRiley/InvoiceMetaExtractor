"""Shared data models for the extraction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class PageImage:
    """Single page raster loaded from PDF render or image file."""

    image: np.ndarray  # RGB uint8, shape (H, W, 3)
    page_index: int  # 0-based
    source_path: Path
    width: int
    height: int


@dataclass
class OcrBlock:
    """One OCR text region with bounding box."""

    text: str
    box: list[tuple[float, float]]  # four corners (x, y) in pixel coords
    score: float
    page_index: int

    @property
    def center(self) -> tuple[float, float]:
        xs = [p[0] for p in self.box]
        ys = [p[1] for p in self.box]
        return (sum(xs) / len(xs), sum(ys) / len(ys))

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """Axis-aligned bounding box: xmin, ymin, xmax, ymax."""
        xs = [p[0] for p in self.box]
        ys = [p[1] for p in self.box]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def mid_y(self) -> float:
        _, ymin, _, ymax = self.bbox
        return (ymin + ymax) / 2

    @property
    def mid_x(self) -> float:
        xmin, _, xmax, _ = self.bbox
        return (xmin + xmax) / 2


@dataclass
class InvoiceLineItem:
    """One invoice detail row extracted from the item table."""

    name: str
    quantity: str = ""
    amount: float | None = None
    tax_amount: float | None = None
    tax_rate: str = ""


@dataclass
class InvoiceRecord:
    """Extracted invoice fields for one source file."""

    source_file: str
    status: str  # success | partial | failed
    row_id: str = ""
    invoice_type: str = ""
    invoice_number: str = ""
    issue_date: str = ""
    seller_name: str = ""
    tax_items: str = ""  # 税目/项目名称，多项以；分隔
    quantity: str = ""
    amount: float | None = None
    tax_amount: float | None = None
    tax_rate: str = ""
    warnings: list[str] = field(default_factory=list)
    raw_ocr_text: str = ""
    line_items: list[InvoiceLineItem] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Full pipeline output for one file."""

    record: InvoiceRecord
    blocks: list[OcrBlock] = field(default_factory=list)
    pages: list[PageImage] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
