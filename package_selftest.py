#!/usr/bin/env python3
"""Selbsttest für Dry-Run, Apply, CRLF, Syntax, Sicherheitsabbruch und Rollback."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "apply_netzentgelt_manual_override_phase5b.py"
FIXTURES = ROOT / "tests" / "fixtures"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str, expect_ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        capture_output=True,
        text=True,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(f"Befehl fehlgeschlagen: {args}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    if not expect_ok and result.returncode == 0:
        raise AssertionError(f"Befehl hätte fehlschlagen müssen: {args}\nSTDOUT:\n{result.stdout}")
    return result


def write_crlf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8"))


def create_fixture_project(project: Path) -> None:
    write_crlf(
        project / "scripts" / "manual_override_ui_module.py",
        (FIXTURES / "manual_override_ui_module_phase5a.py").read_text(encoding="utf-8"),
    )
    write_crlf(
        project / "scripts" / "manual_override_module.py",
        (FIXTURES / "manual_override_module_phase5a.py").read_text(encoding="utf-8"),
    )
    write_crlf(
        project / "app" / "app.py",
        "from manual_override_ui_module import render_manual_override_cockpit\n",
    )
    write_crlf(
        project / "scripts" / "run_all.py",
        "from manual_override_module import import_manual_overrides, apply_raw_manual_overrides, apply_staging_manual_overrides\n",
    )


def assert_crlf_only(path: Path) -> None:
    raw = path.read_bytes()
    assert b"\r\n" in raw, f"CRLF fehlt: {path}"
    assert b"\n" not in raw.replace(b"\r\n", b""), f"isoliertes LF gefunden: {path}"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="phase5b_selftest_") as tmp:
        project = Path(tmp) / "project"
        create_fixture_project(project)
        ui = project / "scripts" / "manual_override_ui_module.py"
        engine = project / "scripts" / "manual_override_suggestion_module.py"
        original_ui_hash = sha256(ui)

        # Dry-Run verändert nichts.
        run("--project-root", str(project), "--dry-run")
        assert sha256(ui) == original_ui_hash
        assert not engine.exists()

        # Apply legt Backup an, erzeugt Engine und erhält CRLF.
        run("--project-root", str(project), "--apply")
        assert engine.exists()
        assert "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607" in ui.read_text(encoding="utf-8")
        assert "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_SUGGESTIONS_V1_20260607" in engine.read_text(encoding="utf-8")
        assert_crlf_only(ui)
        assert_crlf_only(engine)
        subprocess.run([sys.executable, "-m", "py_compile", str(ui), str(engine)], check=True)

        # Idempotenter Dry-Run nach Apply.
        run("--project-root", str(project), "--dry-run")

        # Rollback stellt UI bytegenau her und entfernt neue Engine.
        run("--project-root", str(project), "--rollback")
        assert sha256(ui) == original_ui_hash
        assert not engine.exists()

        # Abweichender lokaler UI-Stand wird sicher abgewiesen.
        with ui.open("ab") as handle:
            handle.write(b"\r\n# LOCAL_UNCOMMITTED_CHANGE\r\n")
        result = run("--project-root", str(project), "--dry-run", expect_ok=False)
        assert "weicht vom geprüften Phase-5A-GitHub-Stand ab" in result.stderr

    print("PACKAGE SELFTEST OK: Dry-Run, Apply, CRLF, Syntax, idempotenter Dry-Run, Rollback und Sicherheitsabbruch geprüft.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
