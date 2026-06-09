import { Component, EventEmitter, Input, Output } from "@angular/core";

import { NzButtonModule } from "ng-zorro-antd/button";
import { NzIconModule } from "ng-zorro-antd/icon";

@Component({
  selector: "app-toolbar",
  standalone: true,
  imports: [NzButtonModule, NzIconModule],
  templateUrl: "./app-toolbar.component.html",
  styleUrl: "./app-toolbar.component.css",
})
export class AppToolbarComponent {
  @Input({ required: true }) extracting = false;
  @Input({ required: true }) hasRecords = false;

  @Output() miroSummary = new EventEmitter<void>();
  @Output() oaPayment = new EventEmitter<void>();
  @Output() settings = new EventEmitter<void>();
  @Output() selectFiles = new EventEmitter<void>();
  @Output() dedupeRecords = new EventEmitter<void>();
  @Output() exportExcel = new EventEmitter<void>();
  @Output() clearAll = new EventEmitter<void>();
}
