export interface InvoiceRecord {
  source_file: string;
  row_id: string;
  status: string;
  invoice_type: string;
  invoice_number: string;
  issue_date: string;
  buyer_name: string;
  seller_name: string;
  tax_items: string;
  quantity: string;
  amount: number | null;
  tax_amount: number | null;
  tax_rate: string;
  warnings: string[];
}

export interface OaReimbursementProjectConfig {
  id: string;
  name: string;
  code: string;
  regexp: string;
}

export interface OaConfigResponse {
  configs: OaReimbursementProjectConfig[];
}

export interface AppConfigResponse {
  ocr_dpi: number;
}

export interface ProgressDto {
  current: number;
  total: number;
  message: string;
  done: boolean;
  running: boolean;
  records: InvoiceRecord[];
  current_file: string;
  page_current: number;
  page_total: number;
}

export interface ExtractStartResponse {
  started: boolean;
  message: string;
}

export interface ExportResponse {
  path: string;
  record_count: number;
}

export interface ExportTableRequest {
  prefix: string;
  sheet_name: string;
  headers: string[];
  rows: Array<Array<string | number | null>>;
}

export interface DedupeRecordsResponse {
  removed_count: number;
  record_count: number;
  records: InvoiceRecord[];
}

export interface PreviewResponse {
  source_file: string;
  mime: string;
  data_base64: string;
  page_index: number;
  page_total: number;
  width: number;
  height: number;
  error: string;
}

export interface PreviewState {
  sourceFile: string;
  page: number;
  pageTotal: number;
  imageSrc: string;
  meta: string;
  placeholder: string;
  loading: boolean;
}

export type SelectionResult =
  | string[]
  | { paths?: string[] }
  | null
  | undefined;

export interface NativeBridgeApi {
  select_paths?: () => Promise<SelectionResult>;
  selectPaths?: () => Promise<SelectionResult>;
  select_files?: () => Promise<SelectionResult>;
  selectFiles?: () => Promise<SelectionResult>;
  open_export_folder?: (path: string) => Promise<void>;
  openExportFolder?: (path: string) => Promise<void>;
}

declare global {
  interface Window {
    pywebview?: {
      api?: NativeBridgeApi;
    };
  }
}
