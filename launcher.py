"""Portable Windows launcher for the Netzentgelt Streamlit tool.

The launcher is packaged by PyInstaller. It starts the portable Streamlit
entrypoint and opens the local browser. No Python installation is required on the
operator workstation when the onedir package is used.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import webbrowser


LAUNCHER_MARKER = "NETZENTGELT_PORTABLE_LAUNCHER_PHASE12A_V1_20260621"


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


def main() -> int:
    base_dir = _base_dir()
    app_path = base_dir / "app" / "portable_secure_app.py"
    if not app_path.exists():
        print(f"FEHLER: Portable App wurde nicht gefunden: {app_path}")
        return 2

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env["NETZENTGELT_PORTABLE"] = "1"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    cmd = [
        sys.executable,
        "-m",
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
    process = subprocess.Popen(cmd, cwd=str(base_dir), env=env)
    time.sleep(3)
    webbrowser.open(url)
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
