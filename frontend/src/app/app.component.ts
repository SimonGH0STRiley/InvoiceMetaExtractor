import { CommonModule } from "@angular/common";
import {
  CdkDragDrop,
  DragDropModule,
  moveItemInArray,
} from "@angular/cdk/drag-drop";
import {
  AfterViewInit,
  ChangeDetectorRef,
  Component,
  ElementRef,
  HostListener,
  OnDestroy,
  ViewChild,
} from "@angular/core";
import { FormsModule } from "@angular/forms";

import { NzButtonModule } from "ng-zorro-antd/button";
import { NzDropDownModule } from "ng-zorro-antd/dropdown";
import { NzDrawerModule } from "ng-zorro-antd/drawer";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzInputModule } from "ng-zorro-antd/input";
import { NzMessageService } from "ng-zorro-antd/message";
import { NzModalModule } from "ng-zorro-antd/modal";
import { NzPopconfirmModule } from "ng-zorro-antd/popconfirm";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";

import { AppToolbarComponent } from "./components/app-toolbar/app-toolbar.component";
import { FileDropOverlayComponent } from "./components/file-drop-overlay/file-drop-overlay.component";
import { ResultsTableComponent } from "./components/results-table/results-table.component";
import { PreviewPanelComponent } from "./components/preview-panel/preview-panel.component";
import { StatusBarComponent } from "./components/status-bar/status-bar.component";
import {
  InvoiceRecord,
  OaReimbursementProjectConfig,
  PreviewState,
} from "./models/invoice.models";
import { ClipboardService } from "./services/clipboard.service";
import { InvoiceApiService } from "./services/invoice-api.service";
import { NativeBridgeService } from "./services/native-bridge.service";
import {
  basename,
  formatNumber as formatDisplayNumber,
  recordKey,
  recordPageIndex,
  statsText,
} from "./shared/record-utils";

interface MiroSummaryRow {
  taxRate: string;
  amount: number;
  taxAmount: number;
  total: number;
}

type OaPaymentSortKey =
  | ""
  | "issue_date"
  | "amount"
  | "tax_amount"
  | "tax_rate";
type SortOrder = "ascend" | "descend" | null;
type OaPaymentNumericFilterKey = "amount" | "tax_amount" | "tax_rate";
type NumericRangeSide = "min" | "max";
type OaConfigField = "name" | "code" | "regexp";

interface OaReimbursementProjectConfigDraft
  extends OaReimbursementProjectConfig {
  nameError: string;
  codeError: string;
  regexpError: string;
}

@Component({
  selector: "app-root",
  standalone: true,
  imports: [
    CommonModule,
    AppToolbarComponent,
    DragDropModule,
    FileDropOverlayComponent,
    FormsModule,
    NzButtonModule,
    NzDropDownModule,
    NzDrawerModule,
    NzIconModule,
    NzInputModule,
    NzModalModule,
    NzPopconfirmModule,
    NzSelectModule,
    NzTableModule,
    PreviewPanelComponent,
    ResultsTableComponent,
    StatusBarComponent,
  ],
  templateUrl: "./app.component.html",
  styleUrl: "./app.component.css",
})
export class AppComponent implements AfterViewInit, OnDestroy {
  @ViewChild("workspace") private workspaceRef?: ElementRef<HTMLElement>;

  paths: string[] = [];
  records: InvoiceRecord[] = [];
  extracting = false;
  statusText = "就绪";
  progressPercent = 0;
  dragActive = false;
  dedupeStatusText = "";
  miroModalOpen = false;
  miroSummaryRows: MiroSummaryRow[] = [];
  miroSummaryTotal: Omit<MiroSummaryRow, "taxRate"> = {
    amount: 0,
    taxAmount: 0,
    total: 0,
  };
  miroTaxRateSortOrder: SortOrder = null;
  oaConfigModalOpen = false;
  oaConfigDraft: OaReimbursementProjectConfigDraft[] = [];
  oaPaymentDrawerOpen = false;
  oaPaymentConfigs: OaReimbursementProjectConfig[] = [];
  oaPaymentProjectByRowKey: Record<string, string> = {};
  readonly invoiceTypeFilters = [
    { text: "专用发票", value: "专用发票" },
    { text: "普通发票", value: "普通发票" },
  ];
  readonly sortDirections: SortOrder[] = ["ascend", "descend", null];
  readonly miroSortDirections: SortOrder[] = ["ascend", "descend"];
  oaPaymentInvoiceTypeFilter = "";
  oaPaymentInvoiceNumberQuery = "";
  oaPaymentSellerQuery = "";
  oaPaymentTaxItemsQuery = "";
  oaPaymentAmountRange = { min: "", max: "" };
  oaPaymentTaxAmountRange = { min: "", max: "" };
  oaPaymentTaxRateRange = { min: "", max: "" };
  oaPaymentSortKey: OaPaymentSortKey = "";
  oaPaymentSortOrder: SortOrder = null;

  selectedSource = "";
  selectedPage = 0;
  previewWidth = 560;
  preview: PreviewState = this.emptyPreview();

  private pollingTimer: number | undefined;
  private readonly minPreviewWidth = 280;
  private readonly minTableWidth = 360;
  private readonly previewRatioKey = "invoicePreviewRatio";
  private readonly oaConfigStorageKey = "oaReimbursementProjectConfigs";
  private readonly supportedFileAccept =
    ".pdf,.jpg,.jpeg,.png,.bmp,.webp,.tif,.tiff";
  private readonly supportedDropExtensions = new Set([
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
  ]);
  private dragDepth = 0;
  private resizeHandle?: HTMLElement;
  private resizeHandleOffset = 0;

  private readonly onPointerMove = (event: PointerEvent): void => {
    event.preventDefault();
    this.resizePreview(event.clientX);
  };

  private readonly onPointerUp = (event: PointerEvent): void => {
    this.resizeHandle?.releasePointerCapture?.(event.pointerId);
    this.resizeHandle = undefined;
    this.resizeHandleOffset = 0;
    document.body.classList.remove("resizing");
    window.removeEventListener("pointermove", this.onPointerMove);
    window.removeEventListener("pointerup", this.onPointerUp);
    window.removeEventListener("pointercancel", this.onPointerUp);
    this.persistPreviewRatio();
  };

  constructor(
    private readonly api: InvoiceApiService,
    private readonly bridge: NativeBridgeService,
    private readonly changeDetector: ChangeDetectorRef,
    private readonly clipboard: ClipboardService,
    private readonly message: NzMessageService
  ) {}

  ngAfterViewInit(): void {
    queueMicrotask(() => this.restorePreviewRatio());
  }

  ngOnDestroy(): void {
    if (this.pollingTimer) {
      window.clearTimeout(this.pollingTimer);
    }
    window.removeEventListener("pointermove", this.onPointerMove);
    window.removeEventListener("pointerup", this.onPointerUp);
    window.removeEventListener("pointercancel", this.onPointerUp);
  }

  get statsText(): string {
    return [statsText(this.records), this.dedupeStatusText]
      .filter(Boolean)
      .join(" · ");
  }

  get selectionStatus(): string {
    return this.paths.length ? `已选 ${this.paths.length} 个文件` : "";
  }

  get displayedMiroSummaryRows(): MiroSummaryRow[] {
    if (!this.miroTaxRateSortOrder) {
      return this.miroSummaryRows;
    }

    return this.miroSummaryRows
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const compare = this.compareMiroTaxRate(
          left.row,
          right.row,
          this.miroTaxRateSortOrder
        );
        return compare === 0 ? left.index - right.index : compare;
      })
      .map((item) => item.row);
  }

  get displayedOaPaymentRecords(): InvoiceRecord[] {
    const filtered = this.records.filter((record) =>
      this.oaPaymentRecordMatchesFilters(record)
    );
    if (!this.oaPaymentSortKey || !this.oaPaymentSortOrder) {
      return filtered;
    }

    return filtered
      .map((record, index) => ({ record, index }))
      .sort((left, right) => {
        const compare = this.compareOaPaymentRecords(
          left.record,
          right.record,
          this.oaPaymentSortKey
        );
        const direction = this.oaPaymentSortOrder === "ascend" ? 1 : -1;
        return compare === 0 ? left.index - right.index : compare * direction;
      })
      .map((item) => item.record);
  }

  get oaPaymentSummaryText(): string {
    const total = this.records.length;
    const displayed = this.displayedOaPaymentRecords.length;
    const filterText = this.hasActiveOaPaymentFilters
      ? `筛选显示 ${displayed}/${total} 条`
      : `当前共 ${total} 条记录`;
    return `已自动去重，${filterText}。`;
  }

  private get hasActiveOaPaymentFilters(): boolean {
    return Boolean(
      this.oaPaymentInvoiceTypeFilter ||
        this.oaPaymentInvoiceNumberQuery.trim() ||
        this.oaPaymentSellerQuery.trim() ||
        this.oaPaymentTaxItemsQuery.trim() ||
        this.oaPaymentAmountRange.min ||
        this.oaPaymentAmountRange.max ||
        this.oaPaymentTaxAmountRange.min ||
        this.oaPaymentTaxAmountRange.max ||
        this.oaPaymentTaxRateRange.min ||
        this.oaPaymentTaxRateRange.max
    );
  }

  @HostListener("window:dragenter", ["$event"])
  onWindowDragEnter(event: DragEvent): void {
    if (!this.hasDraggedFiles(event)) return;
    event.preventDefault();
    this.dragDepth += 1;
    this.dragActive = true;
  }

  @HostListener("window:dragover", ["$event"])
  onWindowDragOver(event: DragEvent): void {
    if (!this.hasDraggedFiles(event)) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = this.extracting ? "none" : "copy";
    }
    this.dragActive = true;
  }

  @HostListener("window:dragleave", ["$event"])
  onWindowDragLeave(event: DragEvent): void {
    if (!this.hasDraggedFiles(event)) return;
    event.preventDefault();
    this.dragDepth = Math.max(0, this.dragDepth - 1);
    this.dragActive = this.dragDepth > 0;
  }

  @HostListener("window:drop", ["$event"])
  onWindowDrop(event: DragEvent): void {
    if (!this.hasDraggedFiles(event)) return;
    event.preventDefault();
    this.dragDepth = 0;
    this.dragActive = false;
    void this.handleDroppedFiles(Array.from(event.dataTransfer?.files ?? []));
  }

  async selectFiles(): Promise<void> {
    if (!this.bridge.hasPywebview) {
      this.setProgress(0, 0, "就绪");
      const files = await this.openBrowserFilePicker();
      if (files.length) {
        await this.handleDroppedFiles(files);
      }
      return;
    }

    try {
      this.paths = await this.bridge.selectPaths();
      if (!this.paths.length) return;
      this.statusText = this.selectionStatus;
      await this.startExtract();
    } catch (error) {
      this.statusText = `选择失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  private openBrowserFilePicker(): Promise<File[]> {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = true;
      input.accept = this.supportedFileAccept;
      input.style.position = "fixed";
      input.style.left = "-9999px";

      input.addEventListener(
        "change",
        () => {
          const files = Array.from(input.files ?? []);
          input.remove();
          resolve(files);
        },
        { once: true }
      );

      document.body.appendChild(input);
      input.click();
    });
  }

  async handleDroppedFiles(files: File[]): Promise<void> {
    if (this.extracting) {
      this.message.warning("正在解析发票中，请稍后再拖入文件");
      return;
    }

    const supportedFiles = files.filter((file) =>
      this.isSupportedDropFile(file)
    );
    if (!supportedFiles.length) {
      this.message.warning("未找到支持的 PDF/图片文件");
      return;
    }

    this.paths = supportedFiles.map((file) => file.name);
    this.dedupeStatusText = "";
    this.setExtracting(true);
    this.setProgress(
      0,
      supportedFiles.length,
      `正在上传 ${supportedFiles.length} 个文件...`
    );

    try {
      const res = await this.api.uploadAndExtract(supportedFiles);
      if (!res.started) {
        this.setExtracting(false);
        this.statusText = res.message || "无法启动提取";
        return;
      }
      await this.pollProgress();
    } catch (error) {
      this.setExtracting(false);
      this.statusText = `拖拽解析发票失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async startExtract(): Promise<void> {
    if (!this.paths.length) {
      this.statusText = "请先选择文件";
      return;
    }
    if (this.extracting) return;

    this.dedupeStatusText = "";
    this.setExtracting(true);
    this.setProgress(0, this.paths.length, "正在启动...");
    try {
      const res = await this.api.startExtract(this.paths);
      if (!res.started) {
        this.setExtracting(false);
        this.statusText = res.message || "无法启动提取";
        return;
      }
      await this.pollProgress();
    } catch (error) {
      this.setExtracting(false);
      this.statusText = `提取失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async exportExcel(): Promise<void> {
    if (!this.records.length) {
      this.statusText = "没有可导出的数据";
      return;
    }

    try {
      const res = await this.api.exportExcel();
      this.statusText = `已导出: ${basename(res.path)}`;
      this.message.success(this.statusText);
      await this.bridge.openExportFolder(res.path);
    } catch (error) {
      this.statusText = `导出失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async exportMiroDrawerExcel(): Promise<void> {
    if (!this.miroSummaryRows.length) {
      this.message.warning("没有可导出的 MIRO 数据");
      return;
    }

    const rows = this.displayedMiroSummaryRows.map((row) => [
      row.taxRate,
      row.amount,
      row.taxAmount,
      row.total,
    ]);
    rows.push([
      "总计",
      this.miroSummaryTotal.amount,
      this.miroSummaryTotal.taxAmount,
      this.miroSummaryTotal.total,
    ]);

    await this.exportDrawerTable({
      prefix: "MIRO-",
      sheet_name: "MIRO税率汇总",
      headers: ["税率", "金额", "税额", "价税合计"],
      rows,
      successText: "MIRO 汇总已导出",
    });
  }

  async exportOaPaymentDrawerExcel(): Promise<void> {
    const records = this.displayedOaPaymentRecords;
    if (!records.length) {
      this.message.warning("没有可导出的 OA付款数据");
      return;
    }

    await this.exportDrawerTable({
      prefix: "OA付款-",
      sheet_name: "OA付款",
      headers: [
        "发票类型",
        "发票号码",
        "开票日期",
        "销售方",
        "税目",
        "数量",
        "金额",
        "税额",
        "税率",
        "OA报销项目",
      ],
      rows: records.map((record) => [
        record.invoice_type,
        record.invoice_number,
        record.issue_date,
        record.seller_name,
        record.tax_items,
        record.quantity,
        record.amount,
        record.tax_amount,
        record.tax_rate,
        this.oaPaymentProjectLabel(record),
      ]),
      successText: "OA付款表格已导出",
    });
  }

  async dedupeRecords(): Promise<void> {
    if (this.extracting || !this.records.length) return;

    try {
      await this.applyDedupe();
      this.refreshView();
    } catch (error) {
      this.statusText = `去重失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async openMiroSummary(): Promise<void> {
    if (this.extracting || !this.records.length) return;

    this.miroModalOpen = true;
    this.refreshView();

    try {
      await this.applyDedupe();
      this.buildMiroSummary();
      this.refreshView();
    } catch (error) {
      this.miroModalOpen = false;
      this.statusText = `MIRO 汇总失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  closeMiroSummary(): void {
    this.miroModalOpen = false;
  }

  async openOaPayment(): Promise<void> {
    if (this.extracting || !this.records.length) return;

    this.oaPaymentDrawerOpen = true;

    try {
      this.oaPaymentConfigs = await this.loadOaConfigs();
      this.refreshView();
      await this.applyDedupe();
      this.oaPaymentProjectByRowKey = this.pruneOaPaymentSelections(
        this.oaPaymentProjectByRowKey
      );
      this.applyOaPaymentRegexMatches();
      this.refreshView();
    } catch (error) {
      this.oaPaymentDrawerOpen = false;
      this.statusText = `OA付款打开失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  closeOaPayment(): void {
    this.oaPaymentDrawerOpen = false;
  }

  updateOaPaymentProject(record: InvoiceRecord, value: string | null): void {
    const rowKey = recordKey(record);
    this.oaPaymentProjectByRowKey = {
      ...this.oaPaymentProjectByRowKey,
      [rowKey]: value || "",
    };
  }

  oaPaymentProjectValue(record: InvoiceRecord): string {
    return this.oaPaymentProjectByRowKey[recordKey(record)] || "";
  }

  oaConfigOptionLabel(config: OaReimbursementProjectConfig): string {
    return [config.name, config.code].filter(Boolean).join(" - ");
  }

  oaPaymentProjectLabel(record: InvoiceRecord): string {
    const configId = this.oaPaymentProjectValue(record);
    const config = this.oaPaymentConfigs.find((item) => item.id === configId);
    return config ? this.oaConfigOptionLabel(config) : "";
  }

  trackOaPaymentRow(_: number, record: InvoiceRecord): string {
    return recordKey(record);
  }

  trackOaPaymentConfig(
    _: number,
    config: OaReimbursementProjectConfig
  ): string {
    return config.id;
  }

  formatNumber(value: number | null): string {
    return formatDisplayNumber(value);
  }

  eventValue(event: Event): string {
    const target = event.target;
    return target instanceof HTMLInputElement ||
      target instanceof HTMLSelectElement
      ? target.value
      : "";
  }

  setOaPaymentInvoiceTypeFilterFromNz(values: string[]): void {
    this.oaPaymentInvoiceTypeFilter = values[0] || "";
  }

  setOaPaymentTextFilter(
    field:
      | "oaPaymentInvoiceNumberQuery"
      | "oaPaymentSellerQuery"
      | "oaPaymentTaxItemsQuery",
    value: string
  ): void {
    this[field] = value;
  }

  setOaPaymentNumericRange(
    field: OaPaymentNumericFilterKey,
    side: NumericRangeSide,
    value: string
  ): void {
    this.oaPaymentRangeFor(field)[side] = value;
  }

  clearOaPaymentNumericRange(field: OaPaymentNumericFilterKey): void {
    const range = this.oaPaymentRangeFor(field);
    range.min = "";
    range.max = "";
  }

  setOaPaymentSortOrder(key: OaPaymentSortKey, order: string | null): void {
    if (!key) return;
    if (order === "ascend" || order === "descend") {
      this.oaPaymentSortKey = key;
      this.oaPaymentSortOrder = order;
      return;
    }

    if (this.oaPaymentSortKey === key) {
      this.oaPaymentSortKey = "";
      this.oaPaymentSortOrder = null;
    }
  }

  oaPaymentSortOrderFor(key: OaPaymentSortKey): SortOrder {
    return this.oaPaymentSortKey === key ? this.oaPaymentSortOrder : null;
  }

  async dropOaPaymentRecord(
    event: CdkDragDrop<InvoiceRecord[]>
  ): Promise<void> {
    if (this.extracting || event.previousIndex === event.currentIndex) return;

    const visible = [...this.displayedOaPaymentRecords];
    moveItemInArray(visible, event.previousIndex, event.currentIndex);
    const visibleKeys = new Set(visible.map((record) => recordKey(record)));
    const movedByVisiblePosition = [...visible];

    this.records = this.records.map((record) =>
      visibleKeys.has(recordKey(record))
        ? movedByVisiblePosition.shift() || record
        : record
    );
    this.oaPaymentSortKey = "";
    this.oaPaymentSortOrder = null;

    try {
      await this.api.reorderRecords(
        this.records.map((item) => recordKey(item)),
        this.records.map((item) => item.source_file)
      );
    } catch (error) {
      this.statusText = `OA付款排序同步失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async openOaConfig(): Promise<void> {
    this.oaConfigModalOpen = true;
    this.oaConfigDraft = [];
    try {
      this.oaConfigDraft = (await this.loadOaConfigs()).map((config) =>
        this.toOaConfigDraft(config)
      );
      if (!this.oaConfigDraft.length) {
        this.addOaConfigRow();
      }
      this.refreshView();
    } catch (error) {
      this.oaConfigModalOpen = false;
      this.message.error(`读取 OA 配置失败: ${this.api.errorMessage(error)}`);
    }
  }

  closeOaConfig(): void {
    this.oaConfigModalOpen = false;
    this.oaConfigDraft = [];
  }

  addOaConfigRow(): void {
    this.oaConfigDraft = [
      ...this.oaConfigDraft,
      {
        id: this.createOaConfigId(),
        name: "",
        code: "",
        regexp: "",
        nameError: "",
        codeError: "",
        regexpError: "",
      },
    ];
  }

  removeOaConfigRow(id: string): void {
    this.oaConfigDraft = this.oaConfigDraft.filter((row) => row.id !== id);
  }

  updateOaConfigField(id: string, field: OaConfigField, value: string): void {
    this.oaConfigDraft = this.oaConfigDraft.map((row) =>
      row.id === id
        ? this.validateOaConfigDraftRow({ ...row, [field]: value })
        : row
    );
  }

  async saveOaConfig(): Promise<void> {
    if (!this.validateOaConfigDraft()) {
      this.message.error(
        this.firstOaConfigDraftError() || "请先修正 OA 报销项目配置"
      );
      return;
    }

    const configs = this.oaConfigDraft.map((row) => ({
      id: row.id,
      name: row.name.trim(),
      code: row.code.trim(),
      regexp: row.regexp.trim(),
    }));

    try {
      const res = await this.api.saveOaConfig(configs);
      this.oaPaymentConfigs = res.configs;
      this.oaConfigModalOpen = false;
      this.oaConfigDraft = [];
      this.message.success(`已保存 ${configs.length} 个 OA 报销项目配置`);
    } catch (error) {
      this.message.error(`保存失败: ${this.api.errorMessage(error)}`);
    }
  }

  trackOaConfigRow(_: number, row: OaReimbursementProjectConfigDraft): string {
    return row.id;
  }

  formatMiroAmount(value: number): string {
    return value.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  setMiroTaxRateSortOrder(order: string | null): void {
    this.miroTaxRateSortOrder =
      order === "ascend" || order === "descend" ? order : null;
  }

  async clearAll(): Promise<void> {
    if (this.extracting) return;
    try {
      await this.api.clear();
    } catch {
      // Clearing local state is still useful when the backend has already reset.
    }
    this.paths = [];
    this.records = [];
    this.dedupeStatusText = "";
    this.miroModalOpen = false;
    this.miroSummaryRows = [];
    this.miroTaxRateSortOrder = null;
    this.oaPaymentDrawerOpen = false;
    this.oaPaymentProjectByRowKey = {};
    this.selectedSource = "";
    this.selectedPage = 0;
    this.clearPreview();
    this.setProgress(0, 0, "就绪");
  }

  async reorderRecords(records: InvoiceRecord[]): Promise<void> {
    if (this.extracting) return;

    this.records = records;
    try {
      await this.api.reorderRecords(
        this.records.map((item) => recordKey(item)),
        this.records.map((item) => item.source_file)
      );
    } catch (error) {
      this.statusText = `排序同步失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async updateRecord(record: InvoiceRecord): Promise<void> {
    if (this.extracting) return;
    const rowKey = recordKey(record);

    try {
      const updated = await this.api.updateRecord(
        rowKey,
        record.source_file,
        record
      );
      this.records = this.records.map((item) =>
        recordKey(item) === rowKey ? updated : item
      );
      this.statusText = "记录已更新";
      this.message.success(this.statusText);
      if (this.selectedSource === record.source_file) {
        this.selectedSource = updated.source_file;
      }
      this.refreshView();
    } catch (error) {
      this.statusText = `编辑失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async removeRecord(record: InvoiceRecord): Promise<void> {
    if (this.extracting) return;
    const rowKey = recordKey(record);
    try {
      await this.api.removeRecord(rowKey, record.source_file);
      const removedIndex = this.records.findIndex(
        (item) => recordKey(item) === rowKey
      );
      this.records = this.records.filter((item) => recordKey(item) !== rowKey);

      if (this.selectedSource === record.source_file) {
        const hasSameSource = this.records.some(
          (item) => item.source_file === record.source_file
        );
        if (!hasSameSource) {
          this.selectedSource = "";
          this.clearPreview();
          const next =
            this.records[Math.min(removedIndex, this.records.length - 1)];
          if (next) {
            await this.selectRow(next);
          }
        }
      }
    } catch (error) {
      this.statusText = `移除失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  async copyText(text: string): Promise<void> {
    if (!text) return;
    try {
      await this.clipboard.copy(text);
      this.message.success("成功复制到剪贴板");
    } catch {
      this.message.error("复制失败");
    }
  }

  async selectRow(record: InvoiceRecord): Promise<void> {
    const pageIndex = recordPageIndex(record);
    this.selectedSource = record.source_file;
    this.selectedPage = pageIndex;
    await this.loadPreview(record.source_file, pageIndex);
  }

  async prevPreviewPage(): Promise<void> {
    if (!this.selectedSource || this.preview.page <= 0) return;
    await this.loadPreview(this.selectedSource, this.preview.page - 1);
  }

  async nextPreviewPage(): Promise<void> {
    if (!this.selectedSource || this.preview.page + 1 >= this.preview.pageTotal)
      return;
    await this.loadPreview(this.selectedSource, this.preview.page + 1);
  }

  startResize(event: PointerEvent): void {
    event.preventDefault();
    const handle = this.resizeHandleElement(event);
    this.resizeHandle = handle;
    this.resizeHandleOffset = this.resizeOffsetWithinHandle(event, handle);
    handle?.setPointerCapture?.(event.pointerId);
    document.body.classList.add("resizing");
    window.addEventListener("pointermove", this.onPointerMove);
    window.addEventListener("pointerup", this.onPointerUp);
    window.addEventListener("pointercancel", this.onPointerUp);
    this.resizePreview(event.clientX);
  }

  private async pollProgress(): Promise<void> {
    try {
      const progress = await this.api.getProgress();
      this.setProgressFromDto(progress);
      this.records = progress.records || [];

      if (progress.running && !progress.done) {
        this.pollingTimer = window.setTimeout(
          () => void this.pollProgress(),
          400
        );
        return;
      }

      this.setExtracting(false);
      if (this.records.length && !this.selectedSource) {
        await this.selectRow(this.records[0]);
      }
    } catch (error) {
      this.setExtracting(false);
      this.statusText = `进度查询失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  private async loadPreview(sourceFile: string, page: number): Promise<void> {
    if (!sourceFile) {
      this.clearPreview();
      return;
    }

    this.preview = {
      ...this.preview,
      sourceFile,
      page,
      imageSrc: "",
      meta: basename(sourceFile),
      loading: true,
    };
    this.refreshView();

    try {
      const data = await this.api.preview(
        sourceFile,
        page,
        this.previewMaxEdge()
      );
      if (data.error || !data.data_base64) {
        this.preview = {
          ...this.preview,
          imageSrc: "",
          placeholder: data.error || "无法加载预览",
        };
        return;
      }

      this.selectedPage = data.page_index;
      this.preview = {
        sourceFile,
        page: data.page_index,
        pageTotal: data.page_total,
        imageSrc: `data:${data.mime};base64,${data.data_base64}`,
        meta: basename(sourceFile),
        placeholder: "选择发票后显示预览",
        loading: false,
      };
      this.refreshView();
    } catch (error) {
      this.preview = {
        ...this.preview,
        imageSrc: "",
        placeholder: this.api.errorMessage(error),
      };
      this.refreshView();
    } finally {
      this.preview = { ...this.preview, loading: false };
      this.refreshView();
    }
  }

  private clearPreview(): void {
    this.preview = this.emptyPreview();
    this.selectedPage = 0;
  }

  private setExtracting(running: boolean): void {
    this.extracting = running;
    this.refreshView();
  }

  private setProgress(current: number, total: number, message: string): void {
    this.progressPercent = total > 0 ? Math.round((current / total) * 100) : 0;
    this.statusText = message || "就绪";
    this.refreshView();
  }

  private setProgressFromDto(progress: {
    current: number;
    total: number;
    message: string;
    done?: boolean;
    page_current?: number;
    page_total?: number;
  }): void {
    if (
      progress.done ||
      (progress.total > 0 && progress.current >= progress.total)
    ) {
      this.progressPercent = progress.total > 0 ? 100 : 0;
      this.statusText = progress.message || "就绪";
      this.refreshView();
      return;
    }

    if (progress.total > 0 && progress.page_total && progress.page_total > 0) {
      const pageRatio =
        Math.min(progress.page_current || 0, progress.page_total) /
        progress.page_total;
      const completed = Math.max(0, progress.current);
      this.progressPercent = Math.min(
        99,
        Math.round(((completed + pageRatio) / progress.total) * 100)
      );
    } else {
      this.progressPercent =
        progress.total > 0
          ? Math.round((progress.current / progress.total) * 100)
          : 0;
    }
    this.statusText = progress.message || "就绪";
    this.refreshView();
  }

  private refreshView(): void {
    this.changeDetector.detectChanges();
  }

  private async applyDedupe(): Promise<void> {
    const res = await this.api.dedupeRecords();
    this.records = res.records || [];
    const removedCount = res.removed_count || 0;

    if (removedCount > 0) {
      this.dedupeStatusText = `已去重 ${removedCount} 条重复记录`;
      this.statusText = `成功去重：移除 ${removedCount} 条重复记录`;
      this.message.success(this.statusText);
    } else {
      this.dedupeStatusText = "未发现重复发票号码";
      this.statusText = "去重完成：未发现重复发票号码";
      this.message.info(this.statusText);
    }

    await this.ensureSelectedRecordVisible();
  }

  private buildMiroSummary(): void {
    const rowsByRate = new Map<string, MiroSummaryRow>();

    for (const record of this.records) {
      const taxRate = record.tax_rate?.trim() || "未识别";
      const amount = this.safeAmount(record.amount);
      const taxAmount = this.safeAmount(record.tax_amount);
      const row = rowsByRate.get(taxRate) || {
        taxRate,
        amount: 0,
        taxAmount: 0,
        total: 0,
      };

      row.amount += amount;
      row.taxAmount += taxAmount;
      row.total += amount + taxAmount;
      rowsByRate.set(taxRate, row);
    }

    this.miroSummaryRows = Array.from(rowsByRate.values());
    this.miroSummaryTotal = this.miroSummaryRows.reduce(
      (total, row) => ({
        amount: total.amount + row.amount,
        taxAmount: total.taxAmount + row.taxAmount,
        total: total.total + row.total,
      }),
      { amount: 0, taxAmount: 0, total: 0 }
    );
  }

  private safeAmount(value: number | null): number {
    return typeof value === "number" && Number.isFinite(value) ? value : 0;
  }

  private compareMiroTaxRate(
    left: MiroSummaryRow,
    right: MiroSummaryRow,
    order: SortOrder
  ): number {
    const leftValue = this.miroTaxRateSortValue(left.taxRate);
    const rightValue = this.miroTaxRateSortValue(right.taxRate);
    const direction = order === "descend" ? -1 : 1;

    if (leftValue === null && rightValue === null) {
      return left.taxRate.localeCompare(right.taxRate, "zh-CN");
    }
    if (leftValue === null) return 1;
    if (rightValue === null) return -1;
    if (leftValue !== rightValue) return (leftValue - rightValue) * direction;
    return left.taxRate.localeCompare(right.taxRate, "zh-CN");
  }

  private miroTaxRateSortValue(taxRate: string): number | null {
    const normalized = taxRate.trim();
    const match = normalized.match(/-?\d+(?:\.\d+)?/);
    if (!match) return null;
    const value = Number(match[0]);
    return Number.isFinite(value) ? value : null;
  }

  private async ensureSelectedRecordVisible(): Promise<void> {
    if (!this.selectedSource) return;

    const stillSelected = this.records.some(
      (record) =>
        record.source_file === this.selectedSource &&
        recordPageIndex(record) === this.selectedPage
    );
    if (stillSelected) return;

    const next = this.records[0];
    this.selectedSource = "";
    this.clearPreview();
    if (next) {
      await this.selectRow(next);
    }
  }

  private previewMaxEdge(): number {
    const workspace = this.workspaceRef?.nativeElement;
    const width = this.previewWidth || workspace?.clientWidth || 500;
    const height = workspace?.clientHeight || 600;
    const dpr = window.devicePixelRatio || 1;
    return Math.min(
      4096,
      Math.max(900, Math.round(Math.max(width, height) * dpr * 1.5))
    );
  }

  private resizePreview(clientX: number): void {
    const workspace = this.workspaceRef?.nativeElement;
    if (!workspace) return;

    const rect = workspace.getBoundingClientRect();
    const max = Math.max(this.minPreviewWidth, rect.width - this.minTableWidth);
    const requestedWidth = clientX - rect.left - this.resizeHandleOffset;
    const nextWidth = Math.max(
      this.minPreviewWidth,
      Math.min(requestedWidth, max)
    );
    this.previewWidth = nextWidth;
    this.changeDetector.detectChanges();
  }

  private resizeHandleElement(event: PointerEvent): HTMLElement | undefined {
    const element =
      event.currentTarget instanceof HTMLElement
        ? event.currentTarget
        : event.target;
    return element instanceof HTMLElement ? element : undefined;
  }

  private resizeOffsetWithinHandle(
    event: PointerEvent,
    handle?: HTMLElement
  ): number {
    if (!handle) return 0;

    const rect = handle.getBoundingClientRect();
    return Math.max(0, Math.min(event.clientX - rect.left, rect.width));
  }

  private restorePreviewRatio(): void {
    const workspace = this.workspaceRef?.nativeElement;
    if (!workspace) return;

    const saved = Number(localStorage.getItem(this.previewRatioKey));
    const ratio =
      Number.isFinite(saved) && saved > 0
        ? Math.min(Math.max(saved, 0.15), 0.85)
        : 0.5;
    const max = Math.max(
      this.minPreviewWidth,
      workspace.clientWidth - this.minTableWidth
    );
    this.previewWidth = Math.max(
      this.minPreviewWidth,
      Math.min(Math.floor(workspace.clientWidth * ratio), max)
    );
  }

  private persistPreviewRatio(): void {
    const workspace = this.workspaceRef?.nativeElement;
    if (!workspace?.clientWidth) return;
    localStorage.setItem(
      this.previewRatioKey,
      String(this.previewWidth / workspace.clientWidth)
    );
  }

  private async exportDrawerTable(request: {
    prefix: string;
    sheet_name: string;
    headers: string[];
    rows: Array<Array<string | number | null>>;
    successText: string;
  }): Promise<void> {
    try {
      const res = await this.api.exportTable({
        prefix: request.prefix,
        sheet_name: request.sheet_name,
        headers: request.headers,
        rows: request.rows,
      });
      this.statusText = `${request.successText}: ${basename(res.path)}`;
      this.message.success(this.statusText);
      await this.bridge.openExportFolder(res.path);
    } catch (error) {
      this.statusText = `导出失败: ${this.api.errorMessage(error)}`;
      this.message.error(this.statusText);
    }
  }

  private pruneOaPaymentSelections(
    selections: Record<string, string>
  ): Record<string, string> {
    const currentRows = new Set(
      this.records.map((record) => recordKey(record))
    );
    const currentConfigs = new Set(
      this.oaPaymentConfigs.map((config) => config.id)
    );
    const next: Record<string, string> = {};

    for (const [rowKey, configId] of Object.entries(selections)) {
      if (
        currentRows.has(rowKey) &&
        (!configId || currentConfigs.has(configId))
      ) {
        next[rowKey] = configId;
      }
    }

    return next;
  }

  private applyOaPaymentRegexMatches(): void {
    const matchers = this.oaPaymentConfigs
      .map((config) => {
        const pattern = config.regexp.trim();
        if (!pattern) return null;
        try {
          return { configId: config.id, regexp: new RegExp(pattern) };
        } catch {
          return null;
        }
      })
      .filter((item): item is { configId: string; regexp: RegExp } =>
        Boolean(item)
      );

    if (!matchers.length) return;

    const nextSelections = { ...this.oaPaymentProjectByRowKey };
    for (const record of this.records) {
      const rowKey = recordKey(record);
      if (nextSelections[rowKey]) continue;

      const taxItems = record.tax_items || "";
      const matched = matchers.find((matcher) => matcher.regexp.test(taxItems));
      if (matched) {
        nextSelections[rowKey] = matched.configId;
      }
    }

    this.oaPaymentProjectByRowKey = nextSelections;
  }

  private oaPaymentRecordMatchesFilters(record: InvoiceRecord): boolean {
    if (
      this.oaPaymentInvoiceTypeFilter &&
      record.invoice_type !== this.oaPaymentInvoiceTypeFilter
    ) {
      return false;
    }
    if (
      !this.includesQuery(
        record.invoice_number,
        this.oaPaymentInvoiceNumberQuery
      )
    ) {
      return false;
    }
    if (!this.includesQuery(record.seller_name, this.oaPaymentSellerQuery)) {
      return false;
    }
    if (!this.includesQuery(record.tax_items, this.oaPaymentTaxItemsQuery)) {
      return false;
    }
    if (!this.inRange(record.amount, this.oaPaymentAmountRange)) {
      return false;
    }
    if (!this.inRange(record.tax_amount, this.oaPaymentTaxAmountRange)) {
      return false;
    }
    return this.inRange(
      this.parseTaxRate(record.tax_rate),
      this.oaPaymentTaxRateRange
    );
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

  private compareOaPaymentRecords(
    left: InvoiceRecord,
    right: InvoiceRecord,
    key: OaPaymentSortKey
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

  private oaPaymentRangeFor(field: OaPaymentNumericFilterKey): {
    min: string;
    max: string;
  } {
    if (field === "amount") return this.oaPaymentAmountRange;
    if (field === "tax_amount") return this.oaPaymentTaxAmountRange;
    return this.oaPaymentTaxRateRange;
  }

  private async loadOaConfigs(): Promise<OaReimbursementProjectConfig[]> {
    const res = await this.api.getOaConfig();
    return res.configs
        .filter((item) => Boolean(item) && typeof item === "object")
        .map((item) => ({
          id:
            typeof item.id === "string" && item.id
              ? item.id
              : this.createOaConfigId(),
          name: typeof item.name === "string" ? item.name : "",
          code: typeof item.code === "string" ? item.code : "",
          regexp: typeof item.regexp === "string" ? item.regexp : "",
        }));
  }

  private toOaConfigDraft(
    config: OaReimbursementProjectConfig
  ): OaReimbursementProjectConfigDraft {
    return this.validateOaConfigDraftRow({
      ...config,
      nameError: "",
      codeError: "",
      regexpError: "",
    });
  }

  private validateOaConfigDraft(): boolean {
    let valid = true;
    const nameCounts = this.oaConfigDraft.reduce((counts, row) => {
      const name = row.name.trim();
      if (name) {
        counts.set(name, (counts.get(name) || 0) + 1);
      }
      return counts;
    }, new Map<string, number>());
    const codeCounts = this.oaConfigDraft.reduce((counts, row) => {
      const code = row.code.trim();
      if (code) {
        counts.set(code, (counts.get(code) || 0) + 1);
      }
      return counts;
    }, new Map<string, number>());

    this.oaConfigDraft = this.oaConfigDraft.map((row) => {
      const validated = this.validateOaConfigDraftRow(
        row,
        nameCounts,
        codeCounts
      );
      if (validated.nameError || validated.codeError || validated.regexpError) {
        valid = false;
      }
      return validated;
    });
    return valid;
  }

  private validateOaConfigDraftRow(
    row: OaReimbursementProjectConfigDraft,
    nameCounts = new Map<string, number>(),
    codeCounts = new Map<string, number>()
  ): OaReimbursementProjectConfigDraft {
    const name = row.name.trim();
    const code = row.code.trim();
    return {
      ...row,
      nameError: this.oaConfigNameError(name, nameCounts),
      codeError: this.oaConfigCodeError(code, codeCounts),
      regexpError: this.regexpError(row.regexp),
    };
  }

  private firstOaConfigDraftError(): string {
    for (const [index, row] of this.oaConfigDraft.entries()) {
      const error = row.nameError || row.codeError || row.regexpError;
      if (error) {
        return `第 ${index + 1} 行：${error}`;
      }
    }
    return "";
  }

  private oaConfigNameError(
    name: string,
    nameCounts: Map<string, number>
  ): string {
    if (!name) return "请输入报销项目名称";
    if ((nameCounts.get(name) || 0) > 1) return "报销项目名称不能重复";
    return "";
  }

  private oaConfigCodeError(
    code: string,
    codeCounts: Map<string, number>
  ): string {
    if (!code) return "";
    if ((codeCounts.get(code) || 0) > 1) return "报销项目代码不能重复";
    if (!/^[A-Za-z0-9_-]+$/.test(code)) {
      return "报销项目代码只能包含字母、数字、下划线或短横线";
    }
    return "";
  }

  private regexpError(value: string): string {
    const pattern = value.trim();
    if (!pattern) return "";

    try {
      new RegExp(pattern);
      return "";
    } catch (error) {
      return error instanceof Error
        ? `正则表达式格式不正确：${error.message}`
        : "正则表达式格式不正确";
    }
  }

  private createOaConfigId(): string {
    return (
      crypto.randomUUID?.() ??
      `oa-${Date.now()}-${Math.random().toString(16).slice(2)}`
    );
  }

  private hasDraggedFiles(event: DragEvent): boolean {
    return Array.from(event.dataTransfer?.types ?? []).includes("Files");
  }

  private isSupportedDropFile(file: File): boolean {
    const dotIndex = file.name.lastIndexOf(".");
    const suffix = dotIndex >= 0 ? file.name.slice(dotIndex).toLowerCase() : "";
    return this.supportedDropExtensions.has(suffix);
  }

  private emptyPreview(): PreviewState {
    return {
      sourceFile: "",
      page: 0,
      pageTotal: 0,
      imageSrc: "",
      meta: "点击表格行查看预览",
      placeholder: "选择发票后显示预览",
      loading: false,
    };
  }
}
