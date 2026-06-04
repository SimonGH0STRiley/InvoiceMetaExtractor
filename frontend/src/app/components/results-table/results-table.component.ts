import { CommonModule } from "@angular/common";
import {
  CdkDragDrop,
  DragDropModule,
  moveItemInArray,
} from "@angular/cdk/drag-drop";
import { Component, EventEmitter, Input, Output } from "@angular/core";
import { FormsModule } from "@angular/forms";

import { NzButtonModule } from "ng-zorro-antd/button";
import { NzDatePickerModule } from "ng-zorro-antd/date-picker";
import { NzDropDownModule } from "ng-zorro-antd/dropdown";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { NzTooltipModule } from "ng-zorro-antd/tooltip";
import { NzWatermarkModule } from "ng-zorro-antd/watermark";

import { InvoiceRecord } from "../../models/invoice.models";
import {
  basename,
  formatNumber,
  recordKey,
  recordPageIndex,
} from "../../shared/record-utils";

type SortKey = "" | "issue_date" | "amount" | "tax_amount" | "tax_rate";
type SortOrder = "ascend" | "descend" | null;
type NumericFilterKey = "amount" | "tax_amount" | "tax_rate";
type NumericRangeSide = "min" | "max";
type EditableTextField =
  | "invoice_type"
  | "invoice_number"
  | "issue_date"
  | "seller_name"
  | "tax_items"
  | "quantity"
  | "tax_rate";
type EditableNumberField = "amount" | "tax_amount";

@Component({
  selector: "app-results-table",
  standalone: true,
  imports: [
    CommonModule,
    DragDropModule,
    FormsModule,
    NzButtonModule,
    NzDatePickerModule,
    NzDropDownModule,
    NzIconModule,
    NzInputModule,
    NzPopconfirmModule,
    NzSelectModule,
    NzTableModule,
    NzTagModule,
    NzTooltipModule,
    NzWatermarkModule,
  ],
  templateUrl: "./results-table.component.html",
  styleUrl: "./results-table.component.css",
})
export class ResultsTableComponent {
  @Input({ required: true }) records: InvoiceRecord[] = [];
  @Input({ required: true }) extracting = false;
  @Input({ required: true }) selectedSource = "";
  @Input({ required: true }) selectedPage = 0;
  @Input({ required: true }) selectionStatus = "";

  @Output() rowSelected = new EventEmitter<InvoiceRecord>();
  @Output() cellCopied = new EventEmitter<string>();
  @Output() recordsReordered = new EventEmitter<InvoiceRecord[]>();
  @Output() recordUpdated = new EventEmitter<InvoiceRecord>();
  @Output() recordRemoved = new EventEmitter<InvoiceRecord>();

  readonly statusOptions = [
    { label: "成功", value: "success" },
    { label: "部分", value: "partial" },
    { label: "失败", value: "failed" },
  ];
  readonly invoiceTypeFilters = [
    { text: "专用发票", value: "专用发票" },
    { text: "普通发票", value: "普通发票" },
  ];
  readonly invoiceTypeOptions = ["专用发票", "普通发票"];
  readonly sortDirections: SortOrder[] = ["ascend", "descend", null];

  editingRowKey = "";
  editingRecord: InvoiceRecord | null = null;
  editingIssueDateValue: Date | null = null;
  invoiceTypeFilter = "";
  invoiceNumberQuery = "";
  sellerQuery = "";
  taxItemsQuery = "";
  amountRange = { min: "", max: "" };
  taxAmountRange = { min: "", max: "" };
  taxRateRange = { min: "", max: "" };
  sortKey: SortKey = "";
  sortOrder: SortOrder = null;

  get displayedRecords(): InvoiceRecord[] {
    const filtered = this.records.filter((record) =>
      this.recordMatchesFilters(record)
    );
    if (!this.sortKey || !this.sortOrder) {
      return filtered;
    }

    return filtered
      .map((record, index) => ({ record, index }))
      .sort((left, right) => {
        const compare = this.compareRecords(
          left.record,
          right.record,
          this.sortKey
        );
        const direction = this.sortOrder === "ascend" ? 1 : -1;
        return compare === 0 ? left.index - right.index : compare * direction;
      })
      .map((item) => item.record);
  }

  get hasTableTransform(): boolean {
    return this.hasActiveFilters || Boolean(this.sortKey && this.sortOrder);
  }

  get tableSummaryText(): string {
    const summary = this.selectionStatus;
    if (!this.hasActiveFilters) {
      return summary;
    }
    const countText = `筛选显示 ${this.displayedRecords.length}/${this.records.length} 条`;
    return [summary, countText].filter(Boolean).join(" · ");
  }

  private get hasActiveFilters(): boolean {
    return Boolean(
      this.invoiceTypeFilter ||
        this.invoiceNumberQuery.trim() ||
        this.sellerQuery.trim() ||
        this.taxItemsQuery.trim() ||
        this.amountRange.min ||
        this.amountRange.max ||
        this.taxAmountRange.min ||
        this.taxAmountRange.max ||
        this.taxRateRange.min ||
        this.taxRateRange.max
    );
  }

  basename(path: string): string {
    return basename(path);
  }

  formatNumber(value: number | null): string {
    return formatNumber(value);
  }

  trackByRow(_: number, record: InvoiceRecord): string {
    return recordKey(record);
  }

  isSelected(record: InvoiceRecord): boolean {
    return (
      record.source_file === this.selectedSource &&
      recordPageIndex(record) === this.selectedPage
    );
  }

  isEditing(record: InvoiceRecord): boolean {
    return recordKey(record) === this.editingRowKey;
  }

  statusLabel(status: string): string {
    return (
      this.statusOptions.find((option) => option.value === status)?.label ||
      status ||
      "未知"
    );
  }

  statusColor(status: string): string {
    if (status === "success") return "success";
    if (status === "partial") return "warning";
    if (status === "failed") return "error";
    return "default";
  }

  validationText(record: InvoiceRecord): string {
    return record.warnings?.length || record.status !== "success"
      ? "需检查"
      : "通过";
  }

  validationColor(record: InvoiceRecord): string {
    return record.warnings?.length || record.status !== "success"
      ? "warning"
      : "success";
  }

  eventValue(event: Event): string {
    const target = event.target;
    return target instanceof HTMLInputElement ||
      target instanceof HTMLSelectElement
      ? target.value
      : "";
  }

  setInvoiceTypeFilter(value: string): void {
    this.invoiceTypeFilter = value;
  }

  setInvoiceTypeFilterFromNz(values: string[]): void {
    this.invoiceTypeFilter = values[0] || "";
  }

  setTextFilter(
    field: "invoiceNumberQuery" | "sellerQuery" | "taxItemsQuery",
    value: string
  ): void {
    this[field] = value;
  }

  setNumericRange(
    field: NumericFilterKey,
    side: NumericRangeSide,
    value: string
  ): void {
    this.rangeFor(field)[side] = value;
  }

  clearNumericRange(field: NumericFilterKey): void {
    const range = this.rangeFor(field);
    range.min = "";
    range.max = "";
  }

  clearFilters(): void {
    this.invoiceTypeFilter = "";
    this.invoiceNumberQuery = "";
    this.sellerQuery = "";
    this.taxItemsQuery = "";
    this.amountRange = { min: "", max: "" };
    this.taxAmountRange = { min: "", max: "" };
    this.taxRateRange = { min: "", max: "" };
  }

  setSortOrder(key: SortKey, order: string | null): void {
    if (!key) return;
    if (order === "ascend" || order === "descend") {
      this.sortKey = key;
      this.sortOrder = order;
      return;
    }

    if (this.sortKey === key) {
      this.sortKey = "";
      this.sortOrder = null;
    }
  }

  sortOrderFor(key: SortKey): SortOrder {
    return this.sortKey === key ? this.sortOrder : null;
  }

  selectRow(record: InvoiceRecord): void {
    this.rowSelected.emit(record);
  }

  copyCell(event: MouseEvent, value: string | number | null | undefined): void {
    event.stopPropagation();
    const text =
      value === null || value === undefined ? "" : String(value).trim();
    if (!text) return;
    this.cellCopied.emit(text);
  }

  startEdit(event: MouseEvent, record: InvoiceRecord): void {
    event.stopPropagation();
    if (this.extracting) return;
    this.editingRowKey = recordKey(record);
    this.editingRecord = {
      ...record,
      warnings: [...(record.warnings || [])],
    };
    this.editingIssueDateValue = this.parseIssueDateValue(record.issue_date);
  }

  cancelEdit(event: MouseEvent): void {
    event.stopPropagation();
    this.editingRowKey = "";
    this.editingRecord = null;
    this.editingIssueDateValue = null;
  }

  saveEdit(event: MouseEvent): void {
    event.stopPropagation();
    if (!this.editingRecord) return;
    this.recordUpdated.emit({
      ...this.editingRecord,
      warnings: [...(this.editingRecord.warnings || [])],
    });
    this.editingRowKey = "";
    this.editingRecord = null;
    this.editingIssueDateValue = null;
  }

  updateEditingText(field: EditableTextField, value: string): void {
    if (!this.editingRecord) return;
    this.editingRecord = { ...this.editingRecord, [field]: value };
  }

  updateEditingNumber(field: EditableNumberField, value: string): void {
    if (!this.editingRecord) return;
    const trimmed = value.trim();
    const parsed = trimmed ? Number(trimmed) : null;
    this.editingRecord = {
      ...this.editingRecord,
      [field]: parsed !== null && Number.isFinite(parsed) ? parsed : null,
    };
  }

  updateEditingDate(value: Date | null): void {
    if (!this.editingRecord) return;
    this.editingIssueDateValue = value;
    this.editingRecord = {
      ...this.editingRecord,
      issue_date: value ? this.formatDateValue(value) : "",
    };
  }

  dropRecord(event: CdkDragDrop<InvoiceRecord[]>): void {
    if (
      this.extracting ||
      this.editingRowKey ||
      this.hasTableTransform ||
      event.previousIndex === event.currentIndex
    )
      return;
    const reordered = [...this.records];
    moveItemInArray(reordered, event.previousIndex, event.currentIndex);
    this.recordsReordered.emit(reordered);
  }

  private recordMatchesFilters(record: InvoiceRecord): boolean {
    if (
      this.invoiceTypeFilter &&
      record.invoice_type !== this.invoiceTypeFilter
    ) {
      return false;
    }
    if (!this.includesQuery(record.invoice_number, this.invoiceNumberQuery)) {
      return false;
    }
    if (!this.includesQuery(record.seller_name, this.sellerQuery)) {
      return false;
    }
    if (!this.includesQuery(record.tax_items, this.taxItemsQuery)) {
      return false;
    }
    if (!this.inRange(record.amount, this.amountRange)) {
      return false;
    }
    if (!this.inRange(record.tax_amount, this.taxAmountRange)) {
      return false;
    }
    return this.inRange(this.parseTaxRate(record.tax_rate), this.taxRateRange);
  }

  private includesQuery(value: string, query: string): boolean {
    const q = query.trim().toLowerCase();
    return (
      !q ||
      String(value || "")
        .toLowerCase()
        .includes(q)
    );
  }

  private inRange(
    value: number | null,
    range: { min: string; max: string }
  ): boolean {
    const min = this.parseFilterNumber(range.min);
    const max = this.parseFilterNumber(range.max);
    if (min === null && max === null) return true;
    if (value === null || !Number.isFinite(value)) return false;
    if (min !== null && value < min) return false;
    if (max !== null && value > max) return false;
    return true;
  }

  private compareRecords(
    left: InvoiceRecord,
    right: InvoiceRecord,
    key: SortKey
  ): number {
    if (key === "issue_date") {
      return this.compareNullableNumbers(
        this.parseDate(left.issue_date),
        this.parseDate(right.issue_date)
      );
    }
    if (key === "amount") {
      return this.compareNullableNumbers(left.amount, right.amount);
    }
    if (key === "tax_amount") {
      return this.compareNullableNumbers(left.tax_amount, right.tax_amount);
    }
    if (key === "tax_rate") {
      return this.compareNullableNumbers(
        this.parseTaxRate(left.tax_rate),
        this.parseTaxRate(right.tax_rate)
      );
    }
    return 0;
  }

  private compareNullableNumbers(
    left: number | null,
    right: number | null
  ): number {
    const leftMissing = left === null || !Number.isFinite(left);
    const rightMissing = right === null || !Number.isFinite(right);
    if (leftMissing && rightMissing) return 0;
    if (leftMissing) return 1;
    if (rightMissing) return -1;
    return left - right;
  }

  private parseDate(value: string): number | null {
    const time = Date.parse(value);
    return Number.isFinite(time) ? time : null;
  }

  private formatDateValue(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  private parseIssueDateValue(value: string): Date | null {
    if (!value) return null;
    const parts = value.split("-").map((part) => Number(part));
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part)))
      return null;
    const [year, month, day] = parts;
    return new Date(year, month - 1, day);
  }

  private parseTaxRate(value: string): number | null {
    const text = String(value || "").trim();
    if (text.includes("免税") || text.includes("不征税")) return 0;
    const match = text.match(/-?\d+(?:\.\d+)?/);
    if (!match) return null;
    const parsed = Number(match[0]);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private parseFilterNumber(value: string): number | null {
    if (!value.trim()) return null;
    const parsed = Number(value.replace(/[%％,，]/g, "").trim());
    return Number.isFinite(parsed) ? parsed : null;
  }

  private rangeFor(field: NumericFilterKey): { min: string; max: string } {
    if (field === "amount") return this.amountRange;
    if (field === "tax_amount") return this.taxAmountRange;
    return this.taxRateRange;
  }
}
