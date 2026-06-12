from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "fallpruefung_review_runtime_bridge.py"


def test_gap_duration_policy_contract() -> None:
    source = MODULE.read_text(encoding="utf-8")

    assert "SHORT_GAP_CONTINUITY_MIN_MINUTES = 15" in source
    assert "SHORT_GAP_CONTINUITY_MAX_MINUTES = 120" in source
    assert "COLD_STAND_PROPOSAL_MIN_MINUTES = 120" in source
    assert "COLD_STAND_PROPOSAL_MAX_MINUTES = 480" in source
    assert "NO_LTE_ASSIGNMENT_MIN_MINUTES = 480" in source
    assert 'NO_LTE_ASSIGNMENT_CLASSIFICATION_CODE = "NO_LTE_ASSIGNMENT"' in source
    assert "Keine LTE-Zuweisung" in source
