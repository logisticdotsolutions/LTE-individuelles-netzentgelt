from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "scripts" / "manual_gap_release_module.py"
PHASE6D = ROOT / "scripts" / "rule_engine_hardening_phase6d.py"


def test_no_lte_gap_release_is_auditable_and_gate_effective() -> None:
    release = RELEASE.read_text(encoding="utf-8")
    phase6d = PHASE6D.read_text(encoding="utf-8")

    assert 'CLASSIFICATION_CODE = "NO_LTE_ASSIGNMENT"' in release
    assert "audit_manual_gap_export_release" in release
    assert "gap_export_released" in release
    assert "set gap_relevant_de = false" in release
    assert "restore_released_gap_visibility" in release

    assert "apply_no_lte_gap_release(con, run_id)" in phase6d
    assert "suspend_released_gaps_for_quality_gate(con)" in phase6d
    assert "restore_released_gap_visibility(con)" in phase6d
    assert "build_quality_gate_tables(con, run_id" in phase6d
    assert "loco_filter=loco_filter" in phase6d
    assert "manual_no_lte_gap_releases" in phase6d
