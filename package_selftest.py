#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parent
INSTALLER = PKG / "apply_netzentgelt_manual_override_phase5a.py"

RUN_ALL = '''from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table

def main():
    con = object()
    run_id = "RUN_TEST"
    imported = []
    try:
        run_id, imported = import_csvs(con)
        build_cancelled_transport_exclusions(con)

        # 2. Fachliche Mappings und offizielle Marktpartner-Referenzdaten einlesen.
        import_mapping(con)
        import_market_partner_reference(con)
        import_market_partner_mapping(con)
        import_vens_tens_exception(con)

        # 3. Bewegungsdaten und Transport-Routen neu berechnen.
        # Die Reihenfolge ist relevant:
        # build_core() benötigt core_transport_route bereits für seinen Join.
        build_loco_events(con)
        build_transport_routes(con)
        build_core(con, run_id)
        build_unresolved_performing_ru_market_partner_alias(con)

        # 5. Sämtliche CSV-Ausgaben neu schreiben.
        for table, name in [
            ("raw_import_run", "raw_import_run.csv"),
            ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),
        ]:
            export_table(con, table, name)
    except Exception:
        raise
'''

APP = '''from pathlib import Path
from operator_ui_module import render_operator_dashboard, render_open_tasks

DB_PATH = Path("db")
SCRIPT_RUN_ALL = Path("scripts/run_all.py")
findings = None
timeline_raw = None

tab_overview, tab_tasks, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([
    "1. Tagesprüfung",
    "2. Offene Aufgaben",
    "3. Lok prüfen",
    "4. Exporte erstellen",
    "⚙️ Technik: Loknummern",
    "⚙️ Technik: Regelqueue",
    "⚙️ Technik: Pipeline"
])

with tab_tasks:
    render_open_tasks(
        export_gate=export_gate,
        global_export_blockers=global_export_blockers,
        findings=findings,
    )


with tab_no_loco:
    pass
'''

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(args: list[str], cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, str(INSTALLER), *args], cwd=str(cwd), capture_output=True, text=True)
    if result.returncode != expect:
        raise AssertionError(f"command failed {args}:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result

def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "app").mkdir()
        (root / "scripts" / "run_all.py").write_bytes(RUN_ALL.replace("\n", "\r\n").encode("utf-8"))
        (root / "app" / "app.py").write_bytes(APP.replace("\n", "\r\n").encode("utf-8"))
        before = {p: sha(root / p) for p in ["scripts/run_all.py", "app/app.py"]}

        run(["--project-root", str(root), "--dry-run"], root)
        assert before == {p: sha(root / p) for p in before}, "Dry-Run changed files"

        run(["--project-root", str(root), "--apply"], root)
        for relative in ["scripts/run_all.py", "app/app.py", "scripts/manual_override_module.py", "scripts/manual_override_ui_module.py"]:
            path = root / relative
            assert path.exists(), relative
            raw = path.read_bytes()
            assert b"\r\n" in raw, f"CRLF missing: {relative}"
        assert b"NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607" in (root / "scripts/run_all.py").read_bytes()
        assert b"render_manual_override_cockpit" in (root / "app/app.py").read_bytes()

        run(["--project-root", str(root), "--rollback"], root)
        assert before == {p: sha(root / p) for p in before}, "Rollback not byte exact"
        assert not (root / "scripts" / "manual_override_module.py").exists()
        assert not (root / "scripts" / "manual_override_ui_module.py").exists()

        # Mehrdeutiger Anker muss im Dry-Run sicher abbrechen.
        path = root / "app" / "app.py"
        text = path.read_text(encoding="utf-8")
        text += "\nfrom operator_ui_module import render_operator_dashboard, render_open_tasks\n"
        path.write_text(text, encoding="utf-8", newline="")
        result = run(["--project-root", str(root), "--dry-run"], root, expect=1)
        assert "nicht eindeutig" in result.stderr

    print("PACKAGE SELFTEST OK")

if __name__ == "__main__":
    main()
