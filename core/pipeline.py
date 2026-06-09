"""Main pipeline: load → OCR → layout extract → validate."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.field_extractor import extract_fields
from core.input_loader import is_supported, load_pages, scan_folder
from core.models import ExtractionResult, InvoiceRecord, OcrBlock, PageImage
from core.ocr_engine import get_ocr_engine
from core.validator import validate_record

OcrPageCallback = Callable[[str, int, int], None]
ProgressCallback = Callable[[int, int, InvoiceRecord], None]

def _ocr_pages(
    pages: list[PageImage],
    *,
    source_label: str = "",
    on_ocr_page: OcrPageCallback | None = None,
) -> list[OcrBlock]:
    engine = get_ocr_engine()
    all_blocks: list[OcrBlock] = []
    total = len(pages)
    for page in pages:
        if on_ocr_page:
            on_ocr_page(source_label, page.page_index + 1, total)
        all_blocks.extend(engine.run_on_page(page))
    return all_blocks


def _blocks_for_single_page(blocks: list[OcrBlock], page_index: int) -> list[OcrBlock]:
    """Rebase one PDF page's OCR blocks to page 0 for page-local extraction."""
    return [
        OcrBlock(
            text=block.text,
            box=list(block.box),
            score=block.score,
            page_index=0,
        )
        for block in blocks
        if block.page_index == page_index
    ]


def process_file_records(
    path: Path,
    *,
    dpi: int = 150,
    on_ocr_page: OcrPageCallback | None = None,
) -> list[InvoiceRecord]:
    """Process a single input file, returning one record per invoice page."""
    path = Path(path).resolve()
    if not is_supported(path):
        return [
            InvoiceRecord(
                source_file=str(path),
                status="failed",
                warnings=[f"不支持的文件类型: {path.suffix}"],
            )
        ]

    try:
        pages = load_pages(path, dpi=dpi)
        blocks = _ocr_pages(
            pages,
            source_label=path.name,
            on_ocr_page=on_ocr_page,
        )

        records: list[InvoiceRecord] = []
        page_indices = [page.page_index for page in pages]
        if len(page_indices) <= 1:
            record = extract_fields(blocks, source_file=str(path))
            records.append(validate_record(record))
        else:
            for page_index in page_indices:
                page_blocks = _blocks_for_single_page(blocks, page_index)
                if not page_blocks:
                    continue
                record = extract_fields(page_blocks, source_file=str(path))
                record.row_id = f"{path}::page::{page_index + 1}"
                records.append(validate_record(record))

        return records
    except Exception as exc:
        return [
            InvoiceRecord(
                source_file=str(path),
                status="failed",
                warnings=[f"处理失败: {exc}"],
            )
        ]


def process_file(
    path: Path,
    *,
    dpi: int = 150,
    on_ocr_page: OcrPageCallback | None = None,
) -> InvoiceRecord:
    """Process a single PDF or image file and return the first record."""
    records = process_file_records(path, dpi=dpi, on_ocr_page=on_ocr_page)
    return records[0]


def process_file_full(path: Path, *, dpi: int = 150) -> ExtractionResult:
    """Process file and return full result with blocks/pages."""
    path = Path(path).resolve()
    pages = load_pages(path, dpi=dpi)
    blocks = _ocr_pages(pages, source_label=path.name)
    record = extract_fields(blocks, source_file=str(path))
    record = validate_record(record)
    return ExtractionResult(record=record, blocks=blocks, pages=pages)


def _resolve_paths(paths: list[Path], *, recursive: bool = False) -> list[Path]:
    resolved: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            resolved.extend(scan_folder(p, recursive=recursive))
        elif p.is_file() and is_supported(p):
            resolved.append(p.resolve())
    return resolved


def process_batch(
    paths: list[Path],
    *,
    dpi: int = 150,
    recursive: bool = False,
    on_progress: ProgressCallback | None = None,
    on_ocr_page: OcrPageCallback | None = None,
) -> list[InvoiceRecord]:
    """Batch process files and folders."""
    files = _resolve_paths(paths, recursive=recursive)
    total = len(files)
    results: list[InvoiceRecord] = []

    for i, fp in enumerate(files, start=1):
        file_records = process_file_records(fp, dpi=dpi, on_ocr_page=on_ocr_page)
        for record in file_records:
            results.append(record)
            if on_progress:
                on_progress(i, total, record)

    return results


def main() -> None:
    """CLI entry for quick testing."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="小宝的发票工作台")
    parser.add_argument("paths", nargs="+", help="PDF/图片文件或文件夹")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--recursive", action="store_true")
    args = parser.parse_args()

    records = process_batch(
        [Path(p) for p in args.paths],
        dpi=args.dpi,
        recursive=args.recursive,
    )
    for r in records:
        print(json.dumps({
            "source_file": r.source_file,
            "status": r.status,
            "invoice_type": r.invoice_type,
            "invoice_number": r.invoice_number,
            "issue_date": r.issue_date,
            "buyer_name": r.buyer_name,
            "seller_name": r.seller_name,
            "tax_items": r.tax_items,
            "quantity": r.quantity,
            "amount": r.amount,
            "tax_amount": r.tax_amount,
            "tax_rate": r.tax_rate,
            "warnings": r.warnings,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
