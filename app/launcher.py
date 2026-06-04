"""EXE entry: start local API + pywebview window."""

from __future__ import annotations

import socket
import sys
import threading
import time

WEBVIEW2_DOCS = (
    "https://developer.microsoft.com/microsoft-edge/webview2/"
)


def _find_free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _wait_for_server(port: int, timeout: float = 30.0) -> bool:
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    return False


def _start_uvicorn(port: int) -> None:
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host="127.0.0.1",
        port=port,
        log_level="warning",
        log_config=None,
        access_log=False,
    )


def _webview2_registry_locations():
    if sys.platform != "win32":
        return []
    import winreg

    client_key = (
        r"Microsoft\EdgeUpdate\Clients"
        r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    )
    return [
        (winreg.HKEY_CURRENT_USER, rf"Software\{client_key}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"Software\{client_key}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"Software\WOW6432Node\{client_key}"),
    ]


def _check_webview2_hint():
    if sys.platform != "win32":
        return None
    try:
        import winreg

        for hive, path in _webview2_registry_locations():
            try:
                key = winreg.OpenKey(hive, path)
                winreg.CloseKey(key)
                return None
            except OSError:
                continue
    except OSError:
        pass

    return (
        "未检测到 Microsoft WebView2 运行时。\n"
        f"请安装后重试：{WEBVIEW2_DOCS}"
    )


def main() -> None:
    hint = _check_webview2_hint()
    if hint:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("InvoiceMetaExtractor", hint)
            root.destroy()
        except ImportError:
            print(hint, file=sys.stderr)
        sys.exit(1)

    port = _find_free_port()
    server_thread = threading.Thread(
        target=_start_uvicorn,
        args=(port,),
        daemon=True,
        name="uvicorn",
    )
    server_thread.start()

    if not _wait_for_server(port):
        print("本地服务启动失败，请检查端口与依赖。", file=sys.stderr)
        sys.exit(1)

    import webview

    from app.native_bridge import NativeBridge

    bridge = NativeBridge()
    url = f"http://127.0.0.1:{port}/"
    webview.create_window(
        "小宝的发票工作台",
        url,
        width=1600,
        height=800,
        min_size=(900, 600),
        js_api=bridge,
    )
    webview.start(gui="edgechromium")
    sys.exit(0)


if __name__ == "__main__":
    main()
