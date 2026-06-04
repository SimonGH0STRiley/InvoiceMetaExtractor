import { CommonModule } from "@angular/common";
import {
  Component,
  EventEmitter,
  HostListener,
  Input,
  Output,
} from "@angular/core";

import { NzButtonModule } from "ng-zorro-antd/button";
import { NzCardModule } from "ng-zorro-antd/card";
import { NzEmptyModule } from "ng-zorro-antd/empty";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzTooltipModule } from "ng-zorro-antd/tooltip";

import { PreviewState } from "../../models/invoice.models";

@Component({
  selector: "app-preview-panel",
  standalone: true,
  imports: [
    CommonModule,
    NzButtonModule,
    NzCardModule,
    NzEmptyModule,
    NzIconModule,
    NzTooltipModule,
  ],
  templateUrl: "./preview-panel.component.html",
  styleUrl: "./preview-panel.component.css",
})
export class PreviewPanelComponent {
  @Input({ required: true }) preview!: PreviewState;
  @Input({ required: true }) width = 560;
  @Input({ required: true }) extracting = false;

  @Output() previousPage = new EventEmitter<void>();
  @Output() nextPage = new EventEmitter<void>();
  @Output() startResize = new EventEmitter<PointerEvent>();

  get hasPreviewImage(): boolean {
    return Boolean(this.preview.imageSrc);
  }

  isPreviewModalOpen = false;

  openPreviewModal(): void {
    if (!this.hasPreviewImage) return;
    this.isPreviewModalOpen = true;
  }

  closePreviewModal(): void {
    this.isPreviewModalOpen = false;
  }

  @HostListener("document:keydown.escape")
  onEscape(): void {
    this.closePreviewModal();
  }
}
