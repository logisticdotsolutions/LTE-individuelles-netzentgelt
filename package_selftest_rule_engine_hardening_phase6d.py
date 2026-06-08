from __future__ import annotations

"""Paket-Selbsttest: Dry-Run, Apply, CRLF, Verify, Idempotenz und Rollback."""

import importlib.util
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_installer(path: Path):
    spec = importlib.util.spec_from_file_location("phase6d_installer_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_crlf(path: Path, text: str, bom: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n").encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + payload)


def make_fixture(root: Path) -> None:
    shutil.copy2(HERE / "apply_rule_engine_hardening_phase6d.py", root / "apply_rule_engine_hardening_phase6d.py")
    shutil.copytree(HERE / "payload", root / "payload")
    write_crlf(root / "scripts" / "run_all.py", '''# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_V1_20260608
from rule_engine_hardening_phase6c import (
    harden_findings_and_segments_phase6c,
    prepare_timeline_context_phase6c,
)

def outer():
    def pipeline(con, run_id):
        build_quality_gate_tables(con, run_id)
        build_exports(con)
        values = [
            ("dq_rule_engine_hardening_phase6c_audit", "dq_rule_engine_hardening_phase6c_audit.csv"),
            ("dq_phase6c_uncertain_gaps", "dq_phase6c_uncertain_gaps.csv"),
        ]
''')
    write_crlf(root / "app" / "app.py", '''# test fixture
# NETZENTGELT_OPERATIONAL_DAY_FILTER_PHASE5C_V1_20260608
# ------------------------------------------------------
excluded_export_rows_path = EXPORT_DIR / "export_excluded_rows.csv"
excluded_export_rows = read_csv_safe(excluded_export_rows_path)
no_loco_summary = summarize_no_loco_cases(no_loco_cases, no_loco_summary)

tab_overview, tab_tasks, tab_override, tab_timeline, tab_exports, tab_no_loco, tab_findings, tab_run = st.tabs([
    "1. Tagesprüfung",
    "2. Offene Aufgaben",
    "3. Fall bearbeiten",
    "4. Lok prüfen",
    "5. Exporte erstellen",
    "⚙️ Technik: Loknummern",
    "⚙️ Technik: Regelqueue",
    "⚙️ Technik: Pipeline"
])

with tab_no_loco:
    pass
''', bom=True)
    write_crlf(root / "scripts" / "rule_engine_diagnostic_phase6a.py", '''"""
Netzentgelt MVP - Rule Engine Diagnostic Phase 6A
=================================================
"""

def run_sql_check(*args, **kwargs):
    pass

def require(*args, **kwargs):
    return True

def columns(*args, **kwargs):
    return []

def check_uncertain_gap_duration(ctx):
    pass

def check_non_de_gap_findings(ctx):
    pass

def check_invisible_same_place_stands(ctx):
    pass

def check_unsupported_gap_transitions(ctx):
    pass

def check_cutoff_bypass(ctx):
    pass

def check_exact_overlap_rounding(ctx):
    pass

def check_info_blocking_movements(ctx):
    pass
''')


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="netzentgelt_phase6d_selftest_") as temp:
        root = Path(temp)
        make_fixture(root)
        installer = load_installer(root / "apply_rule_engine_hardening_phase6d.py")
        installer.EXPECTED_BLOBS = {
            relative: installer.git_blob_sha((root / relative).read_bytes())
            for relative in installer.PATCHERS
        }
        before = {relative: (root / relative).read_bytes() for relative in installer.PATCHERS}
        installer.dry_run()
        for relative, raw in before.items():
            assert (root / relative).read_bytes() == raw, f"Dry-Run hat {relative} veraendert"
        installer.apply()
        installer.verify()
        for relative in installer.PATCHERS:
            data = (root / relative).read_bytes()
            assert b"\r\n" in data, f"CRLF ging verloren: {relative}"
        installer.dry_run()
        installer.apply()
        installer.rollback()
        for relative, raw in before.items():
            assert (root / relative).read_bytes() == raw, f"Rollback unvollstaendig: {relative}"
        for relative in installer.NEW_FILES:
            assert not (root / relative).exists(), f"Neue Datei nach Rollback vorhanden: {relative}"
    print("OK: Paket-Selbsttest Phase 6D erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
