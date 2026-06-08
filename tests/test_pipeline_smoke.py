from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.support.smoke_support import run_isolated_pipeline


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.smoke
def test_full_pipeline_uses_temporary_paths_and_builds_product_db(monkeypatch, tmp_path: Path):
    productive_sentinel = tmp_path / "productive_netzentgelt.duckdb"
    productive_sentinel.write_bytes(b"DO-NOT-TOUCH")
    before = digest(productive_sentinel)
    paths, metrics = run_isolated_pipeline(monkeypatch, tmp_path)
    assert paths["DB_PATH"].exists()
    assert not paths["DB_BUILD_PATH"].exists()
    assert digest(productive_sentinel) == before
    assert metrics["raw_locomotivemovement_rows"] == 1
    assert metrics["staging_event_rows"] == 1
    assert metrics["timeline_movement_rows"] == 1
    assert metrics["timeline_gap_rows"] == 0


@pytest.mark.smoke
def test_smoke_pipeline_creates_audit_exports_only_inside_temp_folder(monkeypatch, tmp_path: Path):
    paths, _ = run_isolated_pipeline(monkeypatch, tmp_path)
    expected = {
        "dq_findings.csv",
        "dq_export_gate.csv",
        "dq_reconciliation.csv",
        "export_nutzungsmeldung.csv",
        "export_zuordnungen.csv",
        "audit_manual_override_application.csv",
        "audit_excluded_cancelled_transports.csv",
    }
    created = {path.name for path in paths["EXP_DIR"].glob("*.csv")}
    assert expected.issubset(created)
