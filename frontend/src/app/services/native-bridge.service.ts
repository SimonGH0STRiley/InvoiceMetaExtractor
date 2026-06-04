import { Injectable } from "@angular/core";

@Injectable({ providedIn: "root" })
export class NativeBridgeService {
  get hasPywebview(): boolean {
    return Boolean(window.pywebview);
  }

  async selectPaths(): Promise<string[]> {
    const api = window.pywebview?.api;
    const pickFn =
      api?.select_paths ??
      api?.selectPaths ??
      api?.select_files ??
      api?.selectFiles;

    if (!api || typeof pickFn !== "function") {
      throw new Error(
        this.hasPywebview
          ? "原生桥接未就绪，请稍后再试"
          : "请在桌面版中使用文件选择"
      );
    }

    const result = await pickFn.call(api);
    return Array.isArray(result) ? result : result?.paths ?? [];
  }

  async openExportFolder(path: string): Promise<void> {
    const api = window.pywebview?.api;
    const openFn = api?.open_export_folder ?? api?.openExportFolder;
    if (api && typeof openFn === "function") {
      await openFn.call(api, path);
    }
  }
}
