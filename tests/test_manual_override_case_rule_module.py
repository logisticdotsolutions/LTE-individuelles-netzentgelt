from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_case_rule_module import (  # noqa: E402
    default_override_type_for_rule,
    format_case_option,
    normalize_rule_id,
    rule_description,
    rule_id_from_case_option,
)


def test_normalize_rule_id_accepts_legacy_r12_spelling() -> None:
    assert normalize_rule_id("R12") == "R012"
    assert normalize_rule_id("r012") == "R012"


def test_format_case_option_adds_readable_rule_description() -> None:
    raw = "R12 | Transport T1 | Lok 91850000002-4 | 2026-06-10T08:15:00"

    result = format_case_option(raw)

    assert result.startswith("R012 – Loknummer fehlt oder ist eine technische Dummy-/Planungslok")
    assert "Transport T1" in result
    assert "Lok 91850000002-4" in result


def test_rule_id_from_case_option_keeps_internal_code_stable() -> None:
    raw = "R012 | Transport T1 | Lok - | 2026-06-10T08:15:00"

    assert rule_id_from_case_option(raw) == "R012"
    assert rule_id_from_case_option("Freie manuelle Erfassung") == ""


def test_default_override_type_is_only_set_for_unambiguous_rules() -> None:
    assert default_override_type_for_rule("R012") == "SET_LOCO_NO"
    assert default_override_type_for_rule("R007") == "SET_PERFORMING_RU"
    assert default_override_type_for_rule("GAP") == "CLASSIFY_GAP"
    assert default_override_type_for_rule("R011") == ""


def test_unknown_rule_remains_readable_without_false_claim() -> None:
    assert rule_description("R999") == "Prüffall aus dem fachlichen Regelwerk"
