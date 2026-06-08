from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

import quality_gate_module
from tests.support.builders import create_core_timeline, create_findings_shell
from tests.support.smoke_support import run_isolated_pipeline
from tests.support.warning_checks import check_project


@pytest.mark.integration
def test_quality_gate_reports_missing_prerequisites_readably(con):
    create_core_timeline(con)
    create_findings_shell(con)
    with pytest.raises(RuntimeError, match="Fehlende Tabellen: dq_run_metadata"):
        quality_gate_module.build_quality_gate_tables(con, "RUN_TEST")


@pytest.mark.smoke
def test_pipeline_schema_contains_expected_phase6d_tables_and_columns(monkeypatch, tmp_path: Path):
    paths, _ = run_isolated_pipeline(monkeypatch, tmp_path)
    con = duckdb.connect(str(paths["DB_PATH"]), read_only=True)
    try:
        tables = {row[0] for row in con.execute("select table_name from information_schema.tables").fetchall()}
        required_tables = {
            "core_loco_timeline", "dq_findings", "dq_run_metadata", "core_usage_assignment_segments",
            "core_usage_assignment_segment_movements", "core_loco_stand_candidates", "dq_export_gate",
            "dq_export_gate_ru", "dq_phase6d_exact_overlap_days", "dq_rule_engine_hardening_phase6d_audit",
            "export_zuordnungen", "export_nutzungsmeldung", "audit_manual_override_application",
            "audit_excluded_cancelled_transports",
        }
        assert required_tables.issubset(tables)
        gate_columns = {row[0] for row in con.execute("describe dq_export_gate").fetchall()}
        assert {"exact_overlap_seconds", "exact_overlap_minutes", "gate_status", "gate_reason"}.issubset(gate_columns)
        timeline_columns = {row[0] for row in con.execute("describe core_loco_timeline").fetchall()}
        assert {"gap_time_basis_safe", "gap_context_class", "de_period_start_utc", "de_period_end_utc", "export_blocking"}.issubset(timeline_columns)
    finally:
        con.close()


@pytest.mark.unit
def test_source_row_hash_missing_pipeline_integration_is_explicit_warning(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run_all.py").write_text("source_hash = 'file-level-only'\n", encoding="utf-8")
    (scripts / "download_blob_data.py").write_text("# manifest\n", encoding="utf-8")
    result = check_project(tmp_path)
    codes = {item["code"] for item in result["warnings"]}
    assert "W001_SOURCE_ROW_HASH_NOT_INTEGRATED" in codes


@pytest.mark.unit
def test_source_row_hash_warning_disappears_after_future_integration(tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "run_all.py").write_text("source_row_hash = 'integrated'\n", encoding="utf-8")
    (scripts / "download_blob_data.py").write_text("# manifest\n", encoding="utf-8")
    result = check_project(tmp_path)
    codes = {item["code"] for item in result["warnings"]}
    assert "W001_SOURCE_ROW_HASH_NOT_INTEGRATED" not in codes
