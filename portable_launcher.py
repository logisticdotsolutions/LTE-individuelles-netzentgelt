"""Portable Windows launcher for the Netzentgelt Streamlit tool.

This launcher runs Streamlit in-process. That is important for PyInstaller,
because the packaged exe is not a normal Python interpreter that can reliably be
called with `-m streamlit`.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
import webbrowser


PORTABLE_LAUNCHER_MARKER = "NETZENTGELT_PORTABLE_LAUNCHER_PHASE12A_V6_20260621"


def _runtime_dir() -> Path:
    """Writable directory next to the exe; used for logs and runtime state."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_dirs(runtime_dir: Path) -> list[Path]:
    """Possible read-only resource roots for PyInstaller onedir/dev runs."""
    candidates = [runtime_dir]
    internal_dir = runtime_dir / "_internal"
    if internal_dir.exists():
        candidates.append(internal_dir)
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass).resolve())

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _find_app_path(runtime_dir: Path) -> Path | None:
    for resource_dir in _resource_dirs(runtime_dir):
        app_path = resource_dir / "app" / "portable_secure_app.py"
        if app_path.exists():
            return app_path
    return None


def _log_dir(runtime_dir: Path) -> Path:
    path = runtime_dir / "_portable_logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_log(runtime_dir: Path, message: str) -> Path:
    log_path = _log_dir(runtime_dir) / "launcher_error.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n" + "=" * 80 + "\n")
        handle.write(datetime.now().isoformat(timespec="seconds") + "\n")
        handle.write(message.rstrip() + "\n")
    return log_path


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
    runtime_dir = _runtime_dir()
    try:
        app_path = _find_app_path(runtime_dir)
        if app_path is None:
            searched = "\n".join(str(path / "app" / "portable_secure_app.py") for path in _resource_dirs(runtime_dir))
            message = "FEHLER: Portable App wurde nicht gefunden. Geprüfte Pfade:\n" + searched
            print(message)
            _write_log(runtime_dir, message)
            return 2

        port = _free_port()
        url = f"http://127.0.0.1:{port}"
        os.environ["NETZENTGELT_PORTABLE"] = "1"
        os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
        sys.argv = [
            "streamlit",
            "run",
            str(app_path),
            "--global.developmentMode=false",
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]

        print("Starte Netzentgelt Tool...")
        print(f"Lokale URL: {url}")
        print(f"Arbeitsordner: {runtime_dir}")
        print(f"App-Datei: {app_path}")
        from streamlit.web import cli as stcli

        try:
            stcli.main()
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else 0
            if exit_code == 0:
                return 0
            message = f"Streamlit wurde mit Exitcode {exit_code} beendet."
            _write_log(runtime_dir, message)
            print(message)
            return exit_code
        return 0
    except BaseException:
        details = traceback.format_exc()
        log_path = _write_log(runtime_dir, details)
        print("FEHLER: Netzentgelt Tool konnte nicht gestartet werden.")
        print(f"Details wurden protokolliert unter: {log_path}")
        print(details)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
