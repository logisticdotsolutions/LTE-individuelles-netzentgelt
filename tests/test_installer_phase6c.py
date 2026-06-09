from __future__ import annotations

import importlib.util
import py_compile
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# NETZENTGELT_HISTORICAL_INSTALLER_TEST_SKIP_V1_20260609
INSTALLER_PATH = ROOT / "apply_rule_engine_hardening_phase6c.py"
installer = None
if INSTALLER_PATH.exists():
    spec = importlib.util.spec_from_file_location("installer", INSTALLER_PATH)
    installer = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(installer)

def test_historical_phase6c_installer_artifact():
    if installer is None:
        import pytest
        pytest.skip("Historischer Phase-6C-Installer wurde beim Repository-Cleanup entfernt.")

RUN_ALL = """from rule_engine_hardening_phase6b import (
    apply_core_assignment_fallbacks,
    harden_findings_and_export_policy,
)

def main():
    if True:
        build_core(con, run_id)
        apply_core_assignment_fallbacks(con, run_id)
        build_unresolved_performing_ru_market_partner_alias(con)
        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)
        harden_findings_and_export_policy(con, run_id)
        build_quality_gate_tables(con, run_id)
        for table, name in [
            ("dq_rule_engine_hardening_blockers", "dq_rule_engine_hardening_blockers.csv"),
            ("stg_loco_events", "stg_loco_events.csv"),
        ]:
            pass
"""

QUALITY_GATE = """def table_exists(con,x): return True
def _require_tables(con,x): pass
def build_quality_gate_tables(con,run_id):
    # ------------------------------------------------------------------
    # 1. Nutzungssegmente aus der bereits vorhandenen Timeline ableiten.
    # ------------------------------------------------------------------
    con.execute(
        \"\"\"
        create or replace temp table tmp_qg_usage_segments as
        select 1
        \"\"\"
    )

    # ------------------------------------------------------------------
    # 2. 15-Minuten-Slots für Nutzungssegmente, Movements und GAPs.
    # ------------------------------------------------------------------
    con.execute(\"\"\"
        where c.row_type = 'GAP'
          and coalesce(c.gap_relevant_de, false) = true
          and nullif(trim(c.loco_no), '') is not null
    \"\"\")
    con.execute(\"\"\"
        with movement_intervals as (
            select
                row_number() over () as overlap_row_no,
                loco_no,
                period_start_utc,
                period_end_utc
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and nullif(trim(loco_no), '') is not null
              and period_start_utc is not null
              and period_end_utc is not null
              and period_end_utc > period_start_utc
        ),
        x as(select 1) select 1
    \"\"\")
"""

EXPORT = """from typing import Sequence
from datetime import date
def table_exists(con,x): return True
def _as_ru_tuple(x): return tuple(x)
def _placeholders(x): return ','.join('?'*len(x))
def _to_day_bounds(a,b): return a,b
def _assert_export_gate_ready(*a): pass
AUDIT_CSV_EXPORTS = [
    ("core_loco_timeline", "core_loco_timeline.csv"),
    ("dq_findings", "dq_findings.csv"),
]
def build_export_tables(con) -> None:
    \"\"\"old\"\"\"
    pass

def export_table_to_csv(
    con,
):
    pass

def _fetch_usage_segments(
    con,
    performing_ru_values: Sequence[str],
    date_from: date,
    date_to: date,
) -> list[dict[str, object]]:
    return []

def _resolve_export_header(
    con,
):
    pass
"""


def crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def main() -> int:
    if installer is None:
        print("SKIP: historischer Phase-6C-Installer wurde beim Repository-Cleanup entfernt.")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "scripts").mkdir(parents=True)
        (project / "payload").mkdir(parents=True)
        shutil.copytree(ROOT / "payload", project / "payload", dirs_exist_ok=True)
        fixture_diag = (ROOT / "tests" / "fixture_rule_engine_diagnostic_phase6a.py").read_text(encoding="utf-8")
        fixtures = {
            Path("scripts/run_all.py"): RUN_ALL,
            Path("scripts/quality_gate_module.py"): QUALITY_GATE,
            Path("scripts/export_module.py"): EXPORT,
            Path("scripts/rule_engine_diagnostic_phase6a.py"): fixture_diag,
        }
        original = {}
        for rel, text in fixtures.items():
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(crlf(text))
            original[rel] = path.read_bytes()
        installer.EXPECTED_LF_BLOBS = {
            rel: installer.git_blob_sha(installer.lf_bytes((project / rel).read_bytes()))
            for rel in fixtures
        }
        installer.MODIFIED_FILES = list(installer.EXPECTED_LF_BLOBS)
        installer.ALL_FILES = installer.MODIFIED_FILES + installer.NEW_FILES
        installer.cmd_dry(project)
        installer.cmd_apply(project)
        installer.cmd_verify(project)
        for rel in fixtures:
            raw = (project / rel).read_bytes()
            assert b"\r\n" in raw, f"CRLF ging verloren: {rel}"
            assert installer.MARKER.encode() in raw, f"Marker fehlt: {rel}"
        installer.cmd_apply(project)  # idempotent
        installer.cmd_rollback(project)
        for rel, expected in original.items():
            assert (project / rel).read_bytes() == expected, f"Rollback nicht bytegenau: {rel}"
        for rel in installer.NEW_FILES:
            assert not (project / rel).exists(), f"Neue Datei blieb nach Rollback bestehen: {rel}"
    print("OK: Installer Dry-Run, Apply, CRLF, Verify, Idempotenz und Rollback erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
