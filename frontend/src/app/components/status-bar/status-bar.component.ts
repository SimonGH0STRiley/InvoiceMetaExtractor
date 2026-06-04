import { CommonModule } from "@angular/common";
import { Component, Input } from "@angular/core";

import { NzIconModule } from "ng-zorro-antd/icon";
import { NzProgressModule } from "ng-zorro-antd/progress";
import { NzTooltipModule } from "ng-zorro-antd/tooltip";

@Component({
  selector: "app-status-bar",
  standalone: true,
  imports: [CommonModule, NzIconModule, NzProgressModule, NzTooltipModule],
  templateUrl: "./status-bar.component.html",
  styleUrl: "./status-bar.component.css",
})
export class StatusBarComponent {
  @Input({ required: true }) progressPercent = 0;
  @Input({ required: true }) statusText = "就绪";
  @Input({ required: true }) statsText = "";
  @Input({ required: true }) extracting = false;

  get statusIcon(): string {
    if (this.extracting) return "loading";
    if (this.progressPercent > 0 && this.progressPercent < 100)
      return "loading";
    if (this.statusText.includes("失败")) return "info-circle";
    if (this.statusText.includes("完成") || this.statusText.includes("已"))
      return "check-circle";
    return "info-circle";
  }

  get statusSpinning(): boolean {
    return this.statusIcon === "loading";
  }

  get statusColorClass(): string {
    if (this.statusText.includes("失败")) return "status-error";
    if (
      this.statusText.includes("完成") ||
      this.statusText.includes("已") ||
      this.progressPercent >= 100
    ) {
      return "status-success";
    }
    return "status-ready";
  }
}
