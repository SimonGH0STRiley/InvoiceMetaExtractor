@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_EXE=python"
if exist ".venv-build\Scripts\python.exe" (
    set "PYTHON_EXE=.venv-build\Scripts\python.exe"
)

echo [1/3] Building Angular frontend...
call npm run build
if errorlevel 1 goto fail

echo [2/3] Checking PyInstaller...
"%PYTHON_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller is not installed.
    echo Run: pip install -r requirements-dev.txt
    exit /b 1
)

echo [3/3] Packaging Windows app...
if exist "dist\InvoiceMetaExtractor" rmdir /s /q "dist\InvoiceMetaExtractor"
if exist "dist\InvoiceMetaExtractor.exe" del /q "dist\InvoiceMetaExtractor.exe"
"%PYTHON_EXE%" -m PyInstaller invoice_meta_extractor.spec --noconfirm --clean
if errorlevel 1 goto fail

echo.
echo Build complete: dist\InvoiceMetaExtractor.exe
exit /b 0

:fail
echo.
echo Build failed with exit code %errorlevel%.
exit /b %errorlevel%
