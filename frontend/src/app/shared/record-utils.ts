import { InvoiceRecord } from "../models/invoice.models";

export function basename(path: string): string {
  return path.replace(/\\/g, "/").split("/").pop() || path;
}

export function recordKey(record: InvoiceRecord): string {
  return record.row_id || record.source_file;
}

export function recordPageIndex(record: InvoiceRecord): number {
  const match = String(record.row_id || "").match(/::page::(\d+)/);
  const pageNumber = match ? Number(match[1]) : 1;
  return Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber - 1 : 0;
}

export function formatNumber(value: number | null): string {
  if (value === null || value === undefined) return "";
  return Number.isFinite(value)
    ? value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
    : String(value);
}

export function statsText(records: InvoiceRecord[]): string {
  if (!records.length) return "";
  const ok = records.filter((record) => record.status === "success").length;
  const partial = records.filter(
    (record) => record.status === "partial"
  ).length;
  const fail = records.filter((record) => record.status === "failed").length;

  return [
    `共 ${records.length} 个文件`,
    ok ? `${ok} 个文件成功解析` : "",
    partial ? `解析了 ${partial} 个文件` : "",
    fail ? `${fail} 个文件解析失败` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
