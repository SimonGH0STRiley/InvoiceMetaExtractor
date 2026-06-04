"""FastAPI local server: extraction jobs, progress, export, preview."""

from __future__ import annotations

import base64
import json
import re
import sys
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Dict, List, Set

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles

from api.schemas import (
    DedupeRecordsResponse,
    ExportRequest,
    ExportResponse,
    ExportTableRequest,
    ExtractRequest,
    ExtractStartResponse,
    InvoiceRecordDto,
    OaConfigDto,
    OaConfigResponse,
    PreviewResponse,
    ProgressDto,
    RemoveRecordRequest,
    ReorderRecordsRequest,
    UpdateRecordRequest,
)
from core.excel_exporter import export_records, export_table
from core.input_loader import is_supported, scan_folder
from core.preview_renderer import render_preview
from core.models import InvoiceRecord
from core.pipeline import process_batch


def _resource_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


WEB_DIR = _resource_root() / "web"
DEFAULT_EXPORT_DIR = Path.home() / "Documents" / "InvoiceMetaExtractor"
UPLOAD_DIR = DEFAULT_EXPORT_DIR / "uploads"
OA_CONFIG_PATH = DEFAULT_EXPORT_DIR / "config" / "oa_config.json"

app = FastAPI(title="InvoiceMetaExtractor", version="0.1.0")

_lock = threading.Lock()
_progress = ProgressDto(current=0, total=0, done=True, running=False)
_records: List[InvoiceRecord] = []
_allowed_paths: Set[str] = set()
_worker: threading.Thread | None = None


def _record_to_dto(record: InvoiceRecord) -> InvoiceRecordDto:
    return InvoiceRecordDto(
        source_file=record.source_file,
        row_id=record.row_id or record.source_file,
        status=record.status,
        invoice_type=record.invoice_type,
        invoice_number=record.invoice_number,
        issue_date=record.issue_date,
        seller_name=record.seller_name,
        tax_items=record.tax_items,
        quantity=record.quantity,
        amount=record.amount,
        tax_amount=record.tax_amount,
        tax_rate=record.tax_rate,
        warnings=list(record.warnings),
    )


def _record_key(record: InvoiceRecord) -> str:
    return record.row_id or record.source_file


def _expand_line_item_records(records: list[InvoiceRecord]) -> list[InvoiceRecord]:
    expanded: list[InvoiceRecord] = []
    for record in records:
        base_key = _record_key(record)
        if len(record.line_items) <= 1:
            if len(record.line_items) == 1:
                item = record.line_items[0]
                record = replace(
                    record,
                    row_id=base_key,
                    tax_items=item.name,
                    quantity=item.quantity,
                    amount=item.amount if item.amount is not None else record.amount,
                    tax_amount=item.tax_amount if item.tax_amount is not None else record.tax_amount,
                    tax_rate=item.tax_rate or record.tax_rate,
                    line_items=[],
                )
            else:
                record = replace(record, row_id=record.row_id or record.source_file)
            expanded.append(record)
            continue

        for index, item in enumerate(record.line_items, start=1):
            expanded.append(
                replace(
                    record,
                    row_id=f"{base_key}::item::{index}",
                    tax_items=item.name,
                    quantity=item.quantity,
                    amount=item.amount,
                    tax_amount=item.tax_amount,
                    tax_rate=item.tax_rate,
                    warnings=list(record.warnings),
                    line_items=[],
                )
            )
    return expanded


def _merge_records(
    base_records: list[InvoiceRecord],
    update_records: list[InvoiceRecord],
) -> list[InvoiceRecord]:
    """Preserve current order while replacing or appending newly extracted files."""
    updates_by_source = {_record_key(record): record for record in update_records}
    merged: list[InvoiceRecord] = []
    seen: set[str] = set()

    for record in base_records:
        record_key = _record_key(record)
        replacement = updates_by_source.get(record_key)
        merged.append(replacement or record)
        seen.add(record_key)

    for record in update_records:
        record_key = _record_key(record)
        if record_key not in seen:
            merged.append(record)
            seen.add(record_key)

    return merged


def _invoice_number_key(record: InvoiceRecord) -> str:
    return re.sub(r"\s+", "", record.invoice_number or "")


def _dedupe_records_by_invoice_number(records: list[InvoiceRecord]) -> tuple[list[InvoiceRecord], int]:
    deduped: list[InvoiceRecord] = []
    seen: set[str] = set()
    removed_count = 0

    for record in records:
        invoice_number = _invoice_number_key(record)
        if invoice_number and invoice_number in seen:
            removed_count += 1
            continue
        if invoice_number:
            seen.add(invoice_number)
        deduped.append(record)

    return deduped, removed_count


def _set_progress(**kwargs) -> None:
    global _progress
    data = _progress.model_dump()
    data.update(kwargs)
    _progress = ProgressDto(**data)


def _register_allowed(paths: list[str], *, recursive: bool = False) -> None:
    global _allowed_paths
    allowed: Set[str] = set(_allowed_paths)
    for p in paths:
        path = Path(p).resolve()
        allowed.add(str(path))
        if path.is_dir():
            for fp in scan_folder(path, recursive=recursive):
                allowed.add(str(fp.resolve()))
        elif path.is_file() and is_supported(path):
            allowed.add(str(path))
    _allowed_paths = allowed


def _path_allowed(path: str) -> bool:
    resolved = str(Path(path).resolve())
    return resolved in _allowed_paths


def _safe_upload_name(filename: str, fallback: str) -> str:
    name = Path(filename or fallback).name
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).stem).strip(" .")
    suffix = Path(name).suffix.lower()
    return f"{stem or fallback}{suffix}"


def _load_oa_configs_from_disk() -> list[OaConfigDto]:
    if not OA_CONFIG_PATH.is_file():
        return []
    try:
        data = json.loads(OA_CONFIG_PATH.read_text(encoding="utf-8"))
        items = data.get("configs", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        return [OaConfigDto.model_validate(item) for item in items if isinstance(item, dict)]
    except Exception:
        return []


def _save_oa_configs_to_disk(configs: list[OaConfigDto]) -> None:
    OA_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "configs": [config.model_dump() for config in configs],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    temp_path = OA_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(OA_CONFIG_PATH)


def _start_extract_paths(
    paths: list[Path],
    *,
    dpi: int,
    recursive: bool,
    message: str = "准备提取…",
) -> ExtractStartResponse:
    global _worker

    if not paths:
        raise HTTPException(status_code=400, detail="未提供文件路径")

    with _lock:
        if _progress.running:
            return ExtractStartResponse(started=False, message="已有提取任务正在运行")

    path_strings = [str(path) for path in paths]
    _register_allowed(path_strings, recursive=recursive)

    with _lock:
        _set_progress(
            current=0,
            total=len(paths),
            message=message,
            done=False,
            running=True,
            records=[_record_to_dto(r) for r in _records],
            current_file="",
            page_current=0,
            page_total=0,
        )

    _worker = threading.Thread(
        target=_run_extract_job,
        args=(paths,),
        kwargs={"dpi": dpi, "recursive": recursive},
        daemon=True,
    )
    _worker.start()
    return ExtractStartResponse(started=True, message="提取已开始")


def _run_extract_job(paths: list[Path], *, dpi: int, recursive: bool) -> None:
    global _records, _progress

    with _lock:
        base_records = list(_records)

    def on_ocr_page(name: str, page_current: int, page_total: int) -> None:
        with _lock:
            _set_progress(
                message=f"正在解析：{name} 第 {page_current}/{page_total} 页",
                current_file=name,
                page_current=page_current,
                page_total=page_total,
            )

    collected: List[InvoiceRecord] = []

    def on_progress(current: int, total: int, record: InvoiceRecord) -> None:
        collected.append(record)
        expanded_collected = _expand_line_item_records(collected)
        merged = _merge_records(base_records, expanded_collected)
        with _lock:
            _set_progress(
                current=current,
                total=total,
                message=f"正在处理 ({current}/{total}): {Path(record.source_file).name}",
                done=False,
                running=True,
                records=[_record_to_dto(r) for r in merged],
                current_file=Path(record.source_file).name,
            )

    try:
        results = process_batch(
            paths,
            dpi=dpi,
            recursive=recursive,
            on_progress=on_progress,
            on_ocr_page=on_ocr_page,
        )
        expanded_results = _expand_line_item_records(results)
        merged = _merge_records(base_records, expanded_results)
        with _lock:
            _records = merged
            _set_progress(
                current=len(results),
                total=len(results),
                message="提取完成",
                done=True,
                running=False,
                records=[_record_to_dto(r) for r in merged],
            )
    except Exception as exc:
        with _lock:
            _set_progress(
                message=f"提取失败: {exc}",
                done=True,
                running=False,
            )


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/progress", response_model=ProgressDto)
def get_progress() -> ProgressDto:
    with _lock:
        return _progress


@app.get("/api/oa-config", response_model=OaConfigResponse)
def get_oa_config() -> OaConfigResponse:
    configs = _load_oa_configs_from_disk()
    return OaConfigResponse(configs=configs)


@app.post("/api/oa-config", response_model=OaConfigResponse)
def save_oa_config(req: OaConfigResponse) -> OaConfigResponse:
    _save_oa_configs_to_disk(req.configs)
    configs = _load_oa_configs_from_disk()
    return OaConfigResponse(configs=configs)


@app.post("/api/extract", response_model=ExtractStartResponse)
def start_extract(req: ExtractRequest) -> ExtractStartResponse:
    if not req.paths:
        raise HTTPException(status_code=400, detail="未提供文件路径")
    paths = [Path(p) for p in req.paths]
    return _start_extract_paths(
        paths,
        dpi=req.dpi,
        recursive=req.recursive,
    )


@app.post("/api/extract/upload", response_model=ExtractStartResponse)
async def start_extract_upload(
    files: List[UploadFile] = File(...),
    dpi: int = Query(200, ge=72, le=300),
) -> ExtractStartResponse:
    if not files:
        raise HTTPException(status_code=400, detail="未提供文件")

    with _lock:
        if _progress.running:
            return ExtractStartResponse(started=False, message="已有提取任务正在运行")

    batch_dir = UPLOAD_DIR / datetime.now().strftime("%Y%m%d_%H%M%S") / uuid4().hex
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for index, upload in enumerate(files, start=1):
        safe_name = _safe_upload_name(upload.filename or "", f"invoice_{index}")
        target = batch_dir / safe_name
        if target.exists():
            target = batch_dir / f"{target.stem}_{uuid4().hex[:8]}{target.suffix}"

        data = await upload.read()
        target.write_bytes(data)
        await upload.close()

        if is_supported(target):
            saved_paths.append(target.resolve())
        else:
            target.unlink(missing_ok=True)

    if not saved_paths:
        raise HTTPException(status_code=400, detail="未找到支持的 PDF/图片文件")

    return _start_extract_paths(
        saved_paths,
        dpi=dpi,
        recursive=False,
        message=f"已接收 {len(saved_paths)} 个拖拽文件，准备 OCR…",
    )


@app.post("/api/clear")
def clear_results() -> Dict[str, bool]:
    global _records, _allowed_paths
    with _lock:
        if _progress.running:
            raise HTTPException(status_code=409, detail="提取进行中，无法清空")
        _records = []
        _allowed_paths = set()
        _set_progress(current=0, total=0, message="就绪", done=True, running=False, records=[])
    return {"ok": True}


@app.post("/api/records/remove")
def remove_record(req: RemoveRecordRequest) -> Dict[str, bool]:
    global _records
    with _lock:
        if _progress.running:
            raise HTTPException(status_code=409, detail="提取进行中，无法移除")
        target = req.row_id or req.source_file
        if not target:
            raise HTTPException(status_code=400, detail="未提供记录标识")
        _records = [r for r in _records if _record_key(r) != target and r.source_file != target]
        _set_progress(records=[_record_to_dto(r) for r in _records])
    return {"ok": True}


@app.post("/api/records/reorder")
def reorder_records(req: ReorderRecordsRequest) -> Dict[str, bool]:
    global _records
    with _lock:
        if _progress.running:
            raise HTTPException(status_code=409, detail="提取进行中，无法排序")

        order_values = req.row_ids or req.source_files
        order = {row_id: index for index, row_id in enumerate(order_values)}
        known = [r for r in _records if _record_key(r) in order]
        unknown = [r for r in _records if _record_key(r) not in order]
        known.sort(key=lambda r: order[_record_key(r)])
        _records = known + unknown
        _set_progress(records=[_record_to_dto(r) for r in _records])
    return {"ok": True}


@app.post("/api/records/update", response_model=InvoiceRecordDto)
def update_record(req: UpdateRecordRequest) -> InvoiceRecordDto:
    global _records
    with _lock:
        if _progress.running:
            raise HTTPException(status_code=409, detail="提取进行中，无法编辑")

        target = req.row_id or req.source_file or req.record.row_id or req.record.source_file
        if not target:
            raise HTTPException(status_code=400, detail="未提供记录标识")

        for index, record in enumerate(_records):
            if _record_key(record) == target or record.source_file == target:
                updated = replace(
                    record,
                    invoice_type=req.record.invoice_type,
                    invoice_number=req.record.invoice_number,
                    issue_date=req.record.issue_date,
                    seller_name=req.record.seller_name,
                    tax_items=req.record.tax_items,
                    quantity=req.record.quantity,
                    amount=req.record.amount,
                    tax_amount=req.record.tax_amount,
                    tax_rate=req.record.tax_rate,
                    status=req.record.status,
                    warnings=list(req.record.warnings),
                )
                _records[index] = updated
                records = [_record_to_dto(r) for r in _records]
                _set_progress(records=records, message="记录已更新")
                return _record_to_dto(updated)

    raise HTTPException(status_code=404, detail="未找到要编辑的记录")


@app.post("/api/records/dedupe", response_model=DedupeRecordsResponse)
def dedupe_records() -> DedupeRecordsResponse:
    global _records
    with _lock:
        if _progress.running:
            raise HTTPException(status_code=409, detail="提取进行中，无法去重")

        _records, removed_count = _dedupe_records_by_invoice_number(_records)
        records = [_record_to_dto(r) for r in _records]
        _set_progress(
            records=records,
            message=f"已按发票号码去重，移除 {removed_count} 条重复记录",
        )

    return DedupeRecordsResponse(
        removed_count=removed_count,
        record_count=len(records),
        records=records,
    )


@app.post("/api/export", response_model=ExportResponse)
def export_excel(req: ExportRequest) -> ExportResponse:
    with _lock:
        if not _records:
            raise HTTPException(status_code=400, detail="没有可导出的记录")
        records = list(_records)

    if req.output_path:
        out = Path(req.output_path)
    else:
        DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = DEFAULT_EXPORT_DIR / f"小宝的发票工作台_{stamp}.xlsx"

    path = export_records(records, out)
    return ExportResponse(path=str(path.resolve()), record_count=len(records))


@app.post("/api/export/table", response_model=ExportResponse)
def export_table_excel(req: ExportTableRequest) -> ExportResponse:
    if not req.headers:
        raise HTTPException(status_code=400, detail="未提供表头")

    DEFAULT_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", req.prefix or "表格导出").strip(" .")
    out = DEFAULT_EXPORT_DIR / f"{prefix}{stamp}.xlsx"
    path = export_table(req.headers, req.rows, out, sheet_name=req.sheet_name)
    return ExportResponse(path=str(path.resolve()), record_count=len(req.rows))


@app.get("/api/preview", response_model=PreviewResponse)
def preview(
    path: str = Query(..., description="源文件绝对路径"),
    page: int = Query(0, ge=0),
    max_edge: int = Query(1600, ge=256, le=4096),
    dpi: int = Query(200, ge=72, le=300),
) -> PreviewResponse:
    if not _path_allowed(path):
        raise HTTPException(status_code=403, detail="路径未授权")

    file_path = Path(path)
    if not file_path.is_file() or not is_supported(file_path):
        return PreviewResponse(source_file=path, error="不支持的文件")

    try:
        png_bytes, mime, width, height, page_total = render_preview(
            file_path,
            page_index=page,
            max_edge=max_edge,
            dpi=dpi,
        )
        encoded = base64.b64encode(png_bytes).decode("ascii")
        return PreviewResponse(
            source_file=str(file_path.resolve()),
            mime=mime,
            data_base64=encoded,
            page_index=page,
            page_total=page_total,
            width=width,
            height=height,
        )
    except Exception as exc:
        return PreviewResponse(source_file=path, error=str(exc))


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
