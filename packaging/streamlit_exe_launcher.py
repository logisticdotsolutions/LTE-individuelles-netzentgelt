from __future__ import annotations

"""Launcher fuer den Windows-EXE-Build der Streamlit-Anwendung.

Die EXE startet die gebuendelte Streamlit-App lokal und oeffnet danach den Browser.
Das eigentliche Fachtool bleibt eine lokale Web-App; die EXE ist nur der stabile Starter.
"""

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _read_configured_entrypoint(root: Path) -> str | None:
    env_value = os.environ.get("NETZENTGELT_STREAMLIT_ENTRY", "").strip()
    if env_value:
        return env_value

    config_path = root / "packaging" / "netzentgelt_entrypoint.txt"
    if config_path.exists():
        value = config_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def _score_streamlit_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return -1

    if "streamlit" not in text and "st." not in text:
        return -1

    score = 0
    indicators = {
        "st.set_page_config": 100,
        "st.navigation": 80,
        "st.Page": 80,
        "st.sidebar": 40,
        "st.tabs": 30,
        "st.title": 25,
        "st.header": 15,
        "def main": 10,
    }
    for needle, weight in indicators.items():
        if needle in text:
            score += weight
    return score


def _detect_entrypoint(root: Path) -> Path:
    configured = _read_configured_entrypoint(root)
    if configured:
        candidate = (root / configured).resolve()
        if candidate.exists():
            return candidate
        raise FileNotFoundError(
            f"Konfigurierter Streamlit-Einstieg wurde nicht gefunden: {configured}"
        )

    preferred = [
        "app.py",
        "streamlit_app.py",
        "Home.py",
        "main.py",
        "scripts/app.py",
        "scripts/streamlit_app.py",
        "scripts/main.py",
    ]
    for relative in preferred:
        candidate = root / relative
        if candidate.exists() and _score_streamlit_file(candidate) >= 0:
            return candidate

    ignored_parts = {".git", ".venv", "build", "dist", "tests", "_test_reports", "__pycache__"}
    scored: list[tuple[int, Path]] = []
    for candidate in root.rglob("*.py"):
        if any(part in ignored_parts for part in candidate.relative_to(root).parts):
            continue
        score = _score_streamlit_file(candidate)
        if score > 0:
            scored.append((score, candidate))

    if scored:
        scored.sort(key=lambda item: (item[0], str(item[1])), reverse=True)
        return scored[0][1]

    raise FileNotFoundError(
        "Kein Streamlit-Einstieg gefunden. Build mit explizitem Pfad starten, z. B. "
        "BUILD_WINDOWS_EXE.bat scripts\\dein_streamlit_app.py"
    )


def _find_free_port(start_port: int = 8501) -> int:
    for port in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Kein freier lokaler Port fuer Streamlit gefunden.")


def _open_browser_later(port: int) -> None:
    time.sleep(2.5)
    webbrowser.open(f"http://127.0.0.1:{port}")


def main() -> int:
    root = _project_root()
    entrypoint = _detect_entrypoint(root)
    port = _find_free_port()

    os.chdir(root)
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

    print("Netzentgelt MVP wird gestartet ...")
    print(f"Projektordner: {root}")
    print(f"Streamlit-App: {entrypoint.relative_to(root)}")
    print(f"Browser: http://127.0.0.1:{port}")

    threading.Thread(target=_open_browser_later, args=(port,), daemon=True).start()

    sys.argv = [
        "streamlit",
        "run",
        str(entrypoint),
        "--server.headless=true",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--browser.gatherUsageStats=false",
    ]

    from streamlit.web.cli import main as streamlit_main

    return int(streamlit_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
