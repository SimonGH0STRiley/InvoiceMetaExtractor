# 打包与样例验收记录

日期：2026-06-04

## 打包链路

| 项目 | 命令/动作 | 期望结果 | 本次结果 |
|---|---|---|---|
| 安装 Python 依赖 | `pip install -r requirements-dev.txt` | 可导入 FastAPI、pywebview、RapidOCR、onnxruntime、PyInstaller | 通过；已安装用户级 64 位 Python 3.10，并在 `.venv-build` 中安装依赖 |
| 依赖导入检查 | `.venv-build\Scripts\python.exe -c "import fastapi, webview, onnxruntime, rapidocr_onnxruntime, fitz, PIL, openpyxl, uvicorn"` | 打包关键依赖均可导入 | 通过 |
| Angular 构建 | `npm run build` | `web/` 下生成 `index.html` 与哈希静态资源 | 通过；已刷新 `web/index.html`、`main-VWDXQ6MB.js`、`styles-HABWMDKD.css`、`polyfills-RV3JTMEC.js` |
| Python 编译检查 | `.venv-build\Scripts\python.exe -m compileall main.py app api core` | 入口、API、启动器、核心模块语法通过 | 通过 |
| PyInstaller 打包 | `build_exe.bat` | 生成单文件 `dist\InvoiceMetaExtractor.exe` | 通过；最终单文件 exe 路径已确认存在 |
| EXE 图标 | `frontend/public/icons/app-icon.ico` | 打包后的 exe 使用 public icons 目录中的图标 | 通过；PyInstaller 日志显示 `Copying icon to EXE` |
| WebView2 检测 | 在未安装 WebView2 Runtime 的机器双击 exe | 弹出明确提示并退出 | 待执行 |
| 无 Python 环境运行 | 在无 Python、无 Node 的 Windows 机器运行 `dist\InvoiceMetaExtractor.exe` | 内嵌 WebView 窗口启动，本地 API 仅绑定 `127.0.0.1` | 待执行 |

## 样例输入验收

| 样例类型 | 样例文件 | 处理路径 | 期望结果 | 本次结果 |
|---|---|---|---|---|
| 文本层 PDF | `samples/text-layer-invoice.pdf` | PDF 渲染为图像后 OCR | 成功提取发票类型、号码、开票日期、销售方、金额、税额、税率；可导出 Excel | 待执行：仓库当前未包含样例文件 |
| 纯图片 PDF | `samples/image-only-invoice.pdf` | PyMuPDF 按页渲染后 OCR | 与文本层 PDF 共用 OCR 流水线，失败时显示可读警告 | 待执行：仓库当前未包含样例文件 |
| JPEG/PNG | `samples/photo-invoice.jpg` 或 `samples/photo-invoice.png` | Pillow 读取并校正方向后 OCR | 表格展示结果，预览面板可打开图片，Excel 导出成功 | 待执行：仓库当前未包含样例文件 |

## 验收步骤

1. 执行 `build_exe.bat`。
2. 双击 `dist\InvoiceMetaExtractor.exe`。
3. 分别选择文本层 PDF、纯图片 PDF、JPEG/PNG 样例。
4. 确认进度条更新、结果表格有记录、异常样例显示警告而不是崩溃。
5. 点击导出 Excel，确认文件生成在用户文档目录。
6. 将 `dist\InvoiceMetaExtractor.exe` 复制到无 Python、无 Node 的 Windows 环境复测。

## 备注

- OCR 模型应放在 `assets/models/` 后再打包，确保目标机器完全离线可用。
- `app/launcher.py` 会检测 WebView2 Runtime，注册表范围覆盖当前用户、64 位机器级与 WOW6432Node 机器级安装。
- 本地服务使用启动时分配的随机端口，仅监听 `127.0.0.1`。
