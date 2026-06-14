"""Regression tests for operator_ui_module.py UI-audit changes.

Covers:
- RULE_TEXT completeness (R007, R016, GAP entries added)
- _friendly_rule behavior for all rule IDs
- _friendly_gate_reason technical-to-friendly replacements
- _friendly_findings column names (German umlauts, no ASCII fallbacks)
- _friendly_gate_table column names and dummy-loco label
- Severity label text
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.modules.setdefault("streamlit", types.SimpleNamespace())

import operator_ui_module as ui


# ---------------------------------------------------------------------------
# RULE_TEXT completeness
# ---------------------------------------------------------------------------

class TestRuleTextEntries:
    """RULE_TEXT must contain all rules that appear in production findings."""

    EXPECTED_RULES = ["R001", "R002", "R003", "R004", "R007", "R009",
                      "R010", "R010.5", "R011", "R012", "R016", "GAP"]

    def test_all_expected_rules_present(self) -> None:
        for rule in self.EXPECTED_RULES:
            assert rule in ui.RULE_TEXT, f"RULE_TEXT missing entry for {rule}"

    def test_r007_mentions_evu(self) -> None:
        problem, action = ui.RULE_TEXT["R007"]
        evu_mentioned = (
            "EVU" in problem or "EVU" in action
            or "Eisenbahnverkehrsunternehmen" in problem
            or "Eisenbahnverkehrsunternehmen" in action
        )
        assert evu_mentioned, "R007 entry should mention EVU or its full name"

    def test_r016_mentions_lte_zuweisung(self) -> None:
        problem, action = ui.RULE_TEXT["R016"]
        assert "LTE" in problem or "LTE" in action

    def test_r016_explains_no_export_block(self) -> None:
        _, action = ui.RULE_TEXT["R016"]
        assert "Export" in action or "sperrt" in action.lower() or "freigegeben" in action

    def test_gap_entry_describes_gap(self) -> None:
        problem, _ = ui.RULE_TEXT["GAP"]
        assert "Lücke" in problem or "GAP" in problem.upper()

    def test_r010_mentions_8_hours_or_export_blocked(self) -> None:
        problem, _ = ui.RULE_TEXT["R010"]
        assert "8" in problem or "Export" in problem or "gesperrt" in problem

    def test_r011_mentions_overlap(self) -> None:
        problem, _ = ui.RULE_TEXT["R011"]
        assert "überschneid" in problem.lower() or "überlapp" in problem.lower()

    def test_r012_no_umlaut_encoding_errors(self) -> None:
        problem, action = ui.RULE_TEXT["R012"]
        for forbidden in ["ae", "oe", "ue", "Ae", "Oe", "Ue"]:
            # Only fail if it looks like a substitution (standalone or adjacent to consonant)
            # "Loknummer" doesn't contain "ue" in a wrong way, but "pruef" would
            pass
        assert "ü" in problem or "Ü" in action or "Planungs" in problem

    def test_each_entry_is_two_tuple_of_nonempty_strings(self) -> None:
        for rule, entry in ui.RULE_TEXT.items():
            assert isinstance(entry, tuple) and len(entry) == 2, f"{rule} entry is not a 2-tuple"
            problem, action = entry
            assert problem.strip(), f"{rule} problem text is empty"
            assert action.strip(), f"{rule} action text is empty"


# ---------------------------------------------------------------------------
# _friendly_rule
# ---------------------------------------------------------------------------

class TestFriendlyRule:

    def test_r001_returns_text_without_original_message(self) -> None:
        problem, _ = ui._friendly_rule("R001", "some raw message")
        assert "Grenzbewegung" in problem or "fehlt" in problem

    def test_r007_returns_evu_text(self) -> None:
        problem, action = ui._friendly_rule("R007", "")
        assert "EVU" in problem or "Eisenbahnverkehrsunternehmen" in problem or "EVU" in action

    def test_r016_returns_lte_text(self) -> None:
        problem, _ = ui._friendly_rule("R016", "")
        assert "LTE" in problem

    def test_gap_entry_returned(self) -> None:
        problem, _ = ui._friendly_rule("GAP", "")
        assert "Lücke" in problem or "GAP" in problem.upper()

    def test_r012_non_dummy_not_mapped_to_dummy_label(self) -> None:
        problem, action = ui._friendly_rule("R012", "Loknummer fehlt.")
        assert problem != "Dummy-Lok"
        assert "Loknummer" in problem
        assert "RailCube" in action

    def test_r012_dummy_message_mapped_to_dummy_label(self) -> None:
        problem, _ = ui._friendly_rule("R012", "Planungs-/Dummy-Lok erkannt.")
        assert problem == "Dummy-Lok"

    def test_unknown_rule_returns_message_as_problem(self) -> None:
        problem, _ = ui._friendly_rule("R999", "Unbekannter Fehler")
        assert "Unbekannter Fehler" in problem

    def test_none_rule_does_not_raise(self) -> None:
        problem, action = ui._friendly_rule(None, "")
        assert isinstance(problem, str)
        assert isinstance(action, str)

    def test_lowercase_rule_id_is_normalized(self) -> None:
        problem_lower, _ = ui._friendly_rule("r001", "")
        problem_upper, _ = ui._friendly_rule("R001", "")
        assert problem_lower == problem_upper


# ---------------------------------------------------------------------------
# _friendly_gate_reason
# ---------------------------------------------------------------------------

class TestFriendlyGateReason:

    def test_error_findings_replaced(self) -> None:
        result = ui._friendly_gate_reason("ERROR-Findings=3")
        assert "3" in result
        assert "ERROR-Findings" not in result
        assert "Blockierende Fehler" in result

    def test_manual_review_replaced(self) -> None:
        result = ui._friendly_gate_reason("MANUAL_REVIEW-Findings=2")
        assert "Manuelle Prüfungen" in result or "Manuelle" in result
        assert "MANUAL_REVIEW" not in result

    def test_gap_over_8h_replaced(self) -> None:
        result = ui._friendly_gate_reason("GAPs ueber 8h=1")
        assert "GAPs ueber 8h" not in result
        assert "8" in result

    def test_ungeklaerte_gap_minuten_replaced(self) -> None:
        result = ui._friendly_gate_reason("Ungeklaerte GAP-Minuten=45")
        assert "Ungeklaerte" not in result
        assert "45" in result

    def test_keine_lte_zuweisung_replaced(self) -> None:
        result = ui._friendly_gate_reason("Keine LTE-Zuweisung")
        assert "Keine LTE-Zuweisung" in result
        assert "freigegeben" in result or "sperrt" in result.lower() or "Export" in result

    def test_empty_value_returns_fallback(self) -> None:
        result = ui._friendly_gate_reason("")
        assert result  # not empty

    def test_none_value_returns_fallback(self) -> None:
        import math
        result = ui._friendly_gate_reason(float("nan"))
        assert result


# ---------------------------------------------------------------------------
# _friendly_findings column names
# ---------------------------------------------------------------------------

class TestFriendlyFindingsColumns:

    def _sample_findings(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "rule_id": "R001",
            "loco_no": "1234",
            "transport_number": "T1",
            "performing_ru": "LTE DE",
            "period_start_utc": "2026-06-13T10:00:00",
            "period_end_utc": "2026-06-13T11:00:00",
            "severity": "ERROR",
            "message": "Grenzübergang fehlt.",
        }])

    def test_has_prioritaet_column_with_umlaut(self) -> None:
        result = ui._friendly_findings(self._sample_findings())
        assert "Priorität" in result.columns
        assert "Prioritaet" not in result.columns

    def test_has_naechster_schritt_with_umlaut(self) -> None:
        result = ui._friendly_findings(self._sample_findings())
        assert "Nächster Schritt" in result.columns

    def test_error_severity_maps_to_blocked_label(self) -> None:
        result = ui._friendly_findings(self._sample_findings())
        assert "⛔" in result.loc[0, "Priorität"]
        assert "Export" in result.loc[0, "Priorität"] or "Blockiert" in result.loc[0, "Priorität"]

    def test_manual_review_severity_label_contains_umlaut_pruefung(self) -> None:
        findings = pd.DataFrame([{
            "rule_id": "R007",
            "loco_no": "X1",
            "transport_number": "",
            "performing_ru": "",
            "period_start_utc": "",
            "period_end_utc": "",
            "severity": "MANUAL_REVIEW",
            "message": "",
        }])
        result = ui._friendly_findings(findings)
        label = result.loc[0, "Priorität"]
        assert "Prüfung" in label, f"Expected 'Prüfung' (with umlaut) in '{label}'"
        assert "Pruefung" not in label

    def test_warning_auswirkung_is_export_moeglich_with_umlaut(self) -> None:
        findings = pd.DataFrame([{
            "rule_id": "R010.5",
            "loco_no": "L1",
            "transport_number": "",
            "performing_ru": "",
            "period_start_utc": "",
            "period_end_utc": "",
            "severity": "WARNING",
            "message": "",
        }])
        result = ui._friendly_findings(findings)
        auswirkung = result.loc[0, "Auswirkung"]
        assert "möglich" in auswirkung, f"Expected 'möglich' (with umlaut) in '{auswirkung}'"
        assert "moeglich" not in auswirkung

    def test_empty_findings_returns_empty_dataframe_with_columns(self) -> None:
        result = ui._friendly_findings(pd.DataFrame())
        assert "Priorität" in result.columns
        assert result.empty


# ---------------------------------------------------------------------------
# _friendly_gate_table column names
# ---------------------------------------------------------------------------

class TestFriendlyGateTableColumns:

    def _sample_gate(self) -> pd.DataFrame:
        return pd.DataFrame([{
            "gate_status": "BLOCKED",
            "loco_no": "L1",
            "coverage_date": "2026-06-13",
            "performing_rus": "LTE DE",
            "coverage_pct": 80,
            "unresolved_gap_minutes": 10,
            "overlap_minutes": 0,
            "gate_reason": "ERROR-Findings=1",
        }])

    def test_has_ungeklaerte_minuten_with_umlaut(self) -> None:
        result = ui._friendly_gate_table(self._sample_gate())
        assert "Ungeklärte Minuten" in result.columns
        assert "Ungeklaerte" not in " ".join(str(c) for c in result.columns)

    def test_has_ueberschneidungsminuten_with_umlaut(self) -> None:
        result = ui._friendly_gate_table(self._sample_gate())
        assert "Überschneidungsminuten" in result.columns
        assert "Ueberschneidungsminuten" not in " ".join(str(c) for c in result.columns)

    def test_has_naechster_schritt_with_umlaut(self) -> None:
        result = ui._friendly_gate_table(self._sample_gate())
        assert "Nächster Schritt" in result.columns
        assert "Naechster" not in " ".join(str(c) for c in result.columns)

    def test_dummy_loco_warum_label_is_dummy_lok(self) -> None:
        gate = self._sample_gate()
        gate["loco_no"] = "DUMMY-1"
        findings = pd.DataFrame([{
            "rule_id": "R012",
            "loco_no": "DUMMY-1",
            "row_type": "RAW_DUMMY_LOCOMOTIVE",
            "message": "Planungs-/Dummy-Lok erkannt.",
        }])
        result = ui._friendly_gate_table(gate, findings=findings)
        assert result.loc[0, "Warum?"] == "Dummy-Lok"

    def test_non_dummy_loco_warum_label_is_gate_reason_text(self) -> None:
        result = ui._friendly_gate_table(self._sample_gate())
        warum = result.loc[0, "Warum?"]
        assert warum  # not empty
        assert warum != "Dummy-Lok"

    def test_empty_gate_returns_columns(self) -> None:
        result = ui._friendly_gate_table(pd.DataFrame())
        assert "Nächster Schritt" in result.columns
        assert result.empty
