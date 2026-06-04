"""Request/response models for the local API."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field


class InvoiceRecordDto(BaseModel):
    source_file: str
    row_id: str = ""
    status: str
    invoice_type: str = ""
    invoice_number: str = ""
    issue_date: str = ""
    seller_name: str = ""
    tax_items: str = ""
    quantity: str = ""
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_rate: str = ""
    warnings: List[str] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    paths: List[str]
    dpi: int = 200
    recursive: bool = False


class ExportRequest(BaseModel):
    output_path: Optional[str] = None


class ExportTableRequest(BaseModel):
    prefix: str
    sheet_name: str = "导出结果"
    headers: List[str]
    rows: List[List[Any]] = Field(default_factory=list)


class OaConfigDto(BaseModel):
    id: str
    name: str = ""
    code: str = ""
    regexp: str = ""


class OaConfigResponse(BaseModel):
    configs: List[OaConfigDto] = Field(default_factory=list)


class RemoveRecordRequest(BaseModel):
    source_file: Optional[str] = None
    row_id: Optional[str] = None


class ReorderRecordsRequest(BaseModel):
    source_files: List[str]
    row_ids: List[str] = Field(default_factory=list)


class UpdateRecordRequest(BaseModel):
    source_file: Optional[str] = None
    row_id: Optional[str] = None
    record: InvoiceRecordDto


class DedupeRecordsResponse(BaseModel):
    removed_count: int
    record_count: int
    records: List[InvoiceRecordDto] = Field(default_factory=list)


class ProgressDto(BaseModel):
    current: int
    total: int
    message: str = ""
    done: bool = False
    running: bool = False
    records: List[InvoiceRecordDto] = Field(default_factory=list)
    current_file: str = ""
    page_current: int = 0
    page_total: int = 0


class ExtractStartResponse(BaseModel):
    started: bool
    message: str = ""


class ExportResponse(BaseModel):
    path: str
    record_count: int


class PreviewResponse(BaseModel):
    source_file: str
    mime: str = "image/png"
    data_base64: str = ""
    page_index: int = 0
    page_total: int = 1
    width: int = 0
    height: int = 0
    error: str = ""
