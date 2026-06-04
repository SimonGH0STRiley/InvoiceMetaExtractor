import { HttpClient, HttpErrorResponse } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { firstValueFrom } from "rxjs";

import {
  DedupeRecordsResponse,
  ExportResponse,
  ExportTableRequest,
  ExtractStartResponse,
  InvoiceRecord,
  OaConfigResponse,
  OaReimbursementProjectConfig,
  PreviewResponse,
  ProgressDto,
} from "../models/invoice.models";

@Injectable({ providedIn: "root" })
export class InvoiceApiService {
  constructor(private readonly http: HttpClient) {}

  getProgress(): Promise<ProgressDto> {
    return this.get<ProgressDto>("/api/progress");
  }

  startExtract(paths: string[]): Promise<ExtractStartResponse> {
    return this.post<ExtractStartResponse>("/api/extract", {
      paths,
      dpi: 200,
      recursive: false,
    });
  }

  uploadAndExtract(files: File[]): Promise<ExtractStartResponse> {
    const formData = new FormData();
    for (const file of files) {
      formData.append("files", file, file.name);
    }
    return this.post<ExtractStartResponse>("/api/extract/upload", formData);
  }

  clear(): Promise<unknown> {
    return this.post("/api/clear", {});
  }

  reorderRecords(rowIds: string[], sourceFiles: string[]): Promise<unknown> {
    return this.post("/api/records/reorder", {
      row_ids: rowIds,
      source_files: sourceFiles,
    });
  }

  removeRecord(rowId: string, sourceFile: string): Promise<unknown> {
    return this.post("/api/records/remove", {
      row_id: rowId,
      source_file: sourceFile,
    });
  }

  updateRecord(
    rowId: string,
    sourceFile: string,
    record: InvoiceRecord
  ): Promise<InvoiceRecord> {
    return this.post<InvoiceRecord>("/api/records/update", {
      row_id: rowId,
      source_file: sourceFile,
      record,
    });
  }

  dedupeRecords(): Promise<DedupeRecordsResponse> {
    return this.post<DedupeRecordsResponse>("/api/records/dedupe", {});
  }

  getOaConfig(): Promise<OaConfigResponse> {
    return this.get<OaConfigResponse>("/api/oa-config");
  }

  saveOaConfig(
    configs: OaReimbursementProjectConfig[]
  ): Promise<OaConfigResponse> {
    return this.post<OaConfigResponse>("/api/oa-config", { configs });
  }

  exportExcel(): Promise<ExportResponse> {
    return this.post<ExportResponse>("/api/export", {});
  }

  exportTable(request: ExportTableRequest): Promise<ExportResponse> {
    return this.post<ExportResponse>("/api/export/table", request);
  }

  preview(
    sourceFile: string,
    page: number,
    maxEdge: number
  ): Promise<PreviewResponse> {
    const params = new URLSearchParams({
      path: sourceFile,
      page: String(page),
      max_edge: String(maxEdge),
      dpi: "200",
    });
    return this.get<PreviewResponse>(`/api/preview?${params}`);
  }

  errorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const detail =
        typeof error.error?.detail === "string" ? error.error.detail : "";
      return detail || error.statusText || error.message;
    }
    return error instanceof Error ? error.message : String(error);
  }

  private async get<T>(url: string): Promise<T> {
    try {
      return await firstValueFrom(this.http.get<T>(url));
    } catch (error) {
      throw new Error(this.errorMessage(error));
    }
  }

  private async post<T = unknown>(url: string, body: unknown): Promise<T> {
    try {
      return await firstValueFrom(this.http.post<T>(url, body));
    } catch (error) {
      throw new Error(this.errorMessage(error));
    }
  }
}
