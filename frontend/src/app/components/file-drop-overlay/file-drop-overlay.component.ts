import { Component, Input } from "@angular/core";

@Component({
  selector: "app-file-drop-overlay",
  standalone: true,
  templateUrl: "./file-drop-overlay.component.html",
  styleUrl: "./file-drop-overlay.component.css",
})
export class FileDropOverlayComponent {
  @Input({ required: true }) active = false;
  @Input({ required: true }) extracting = false;
}
