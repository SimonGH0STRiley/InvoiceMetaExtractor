# InvoiceMetaExtractor

离线发票 PDF/图片字段提取工具（OCR + 版面语义抽取）。

## 开发环境

建议使用 64 位 Python 3.10+ 创建打包环境；OCR 依赖中的 onnxruntime 通常不适合 32 位 Python 环境。

```bash
pip install -r requirements.txt
```

可选：将 RapidOCR ONNX 模型放入 `assets/models/` 以实现完全离线（否则 RapidOCR 首次运行可能使用本地缓存）。

打包开发机还需要安装 PyInstaller：

```bash
pip install -r requirements-dev.txt
```

## 前端开发

Web UI 已接入 Angular 与 ng-zorro，源码位于 `frontend/src/`，构建产物输出到现有 `web/` 目录，FastAPI/pywebview 启动方式保持不变。
页面支持整页拖拽 PDF/图片文件，松开后会上传到本地服务并自动开始 OCR。

```bash
npm install
npm run build
```

本地前端调试运行：

```bash
npm start
```

该命令会同时启动 FastAPI（`127.0.0.1:8000`）和 Angular dev server（`127.0.0.1:4200`）。

仅刷新内嵌 WebView 使用的静态资源：

```bash
npm run build
```

构建产物会写入 `web/`，PyInstaller 打包时会把该目录作为静态 UI 资源带入 exe。

## 命令行测试

```bash
python -m core.pipeline "path/to/invoice.pdf"
python -m core.pipeline "folder/" --recursive
```

## 项目结构

- `core/` — 载入、OCR、版面分析、字段抽取
- `api/` — 本地 FastAPI
- `frontend/` — Angular + ng-zorro Web UI 源码
- `web/` — 内嵌 Web UI 静态资源/Angular 构建产物
- `app/` — pywebview 启动器与原生桥接
- `invoice_meta_extractor.spec` — PyInstaller 单文件打包配置
- `build_exe.bat` — Windows 打包脚本

## 打包

在 Windows 开发机执行：

```bat
build_exe.bat
```

如果项目根目录存在 `.venv-build\Scripts\python.exe`，脚本会优先使用该虚拟环境执行 PyInstaller；否则回退到系统 `python`。

脚本会依次执行：

1. `npm run build`：生成 Angular 静态产物到 `web/`
2. `python -m PyInstaller invoice_meta_extractor.spec --noconfirm --clean`
3. 输出单文件 `dist\InvoiceMetaExtractor.exe`

`invoice_meta_extractor.spec` 会打入 `main.py`、`core/`、`api/`、`app/`、`web/`、`assets/`（含 `assets/models/` OCR 模型，如存在）以及 onnxruntime/RapidOCR 相关资源，并使用 `frontend/public/icons/app-icon.ico` 作为 exe 图标。

## 无 Python 环境运行

打包完成后，将 `dist\InvoiceMetaExtractor.exe` 复制到目标 Windows 机器，双击即可启动。目标机器不需要安装 Python 或 Node.js。

运行时会启动仅绑定 `127.0.0.1` 的本地 FastAPI 服务，并打开 pywebview 内嵌窗口。若系统缺少 Microsoft WebView2 Runtime，启动器会给出安装提示。

## 验收记录

打包和样例验收记录见 `PACKAGING_ACCEPTANCE.md`。样例覆盖范围包括文本层 PDF、纯图片 PDF、JPEG/PNG 图片输入，三类输入均应走统一的“渲染/载入图像 → OCR → 版面语义抽取 → Excel 导出”流程。
