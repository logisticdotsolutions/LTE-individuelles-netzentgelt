"""Portable Windows launcher for the Netzentgelt Streamlit tool.

This launcher runs Streamlit in-process. That is important for PyInstaller,
because the packaged exe is not a normal Python interpreter that can reliably be
called with `-m streamlit`.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
import threading
import time
import webbrowser


PORTABLE_LAUNCHER_MARKER = "NETZENTGELT_PORTABLE_LAUNCHER_PHASE12A_V2_20260621"


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _free_port(preferred: int = 8501) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def _open_browser(url: str) -> None:
    time.sleep(3)
    webbrowser.open(url)


def main() -> int:
    base_dir = _base_dir()
    app_path = base_dir / "app" / "portable_secure_app.py"
    if not app_path.exists():
        print(f"FEHLER: Portable App wurde nicht gefunden: {app_path}")
        return 2

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    os.environ["NETZENTGELT_PORTABLE"] = "1"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]

    print("Starte Netzentgelt Tool...")
    print(f"Lokale URL: {url}")
    from streamlit.web import cli as stcli

    stcli.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
