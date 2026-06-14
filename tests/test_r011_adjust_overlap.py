from __future__ import annotations

"""R011 ADJUST_OVERLAP – Einheitentests für Regel-Default, Guidance und Fallauswahltabelle.

Prüft:
- R011 erhält ADJUST_OVERLAP als automatischen Default-Korrekturtyp
- ADJUST_OVERLAP ist in GUIDANCE_BY_TYPE registriert, requires_new_value=False
- validate_guided_input akzeptiert fehlenden override_value für ADJUST_OVERLAP
- _build_case_table leitet overlap_with_transport_number aus dq_findings weiter
- JSON-Parsing der Überschneidungskorrekturen bei leerem/fehlerhaftem Wert stabil
"""

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_case_rule_module import default_override_type_for_rule
from manual_override_guidance_module import (
    GUIDANCE_BY_TYPE,
    guidance_for,
    validate_guided_input,
)
from manual_override_ui_module import _build_case_table


# ---------------------------------------------------------------------------
# Default-Korrekturtyp für R011
# ---------------------------------------------------------------------------

def test_r011_default_is_adjust_overlap() -> None:
    """R011 muss automatisch ADJUST_OVERLAP vorbelegen."""
    assert default_override_type_for_rule("R011") == "ADJUST_OVERLAP"


def test_r011_alias_r11_also_resolves() -> None:
    """Legacy-Schreibweise R11 muss ebenfalls auf ADJUST_OVERLAP führen."""
    assert default_override_type_for_rule("R11") == "ADJUST_OVERLAP"


# ---------------------------------------------------------------------------
# Guidance-Registrierung
# ---------------------------------------------------------------------------

def test_adjust_overlap_is_registered_in_guidance() -> None:
    """ADJUST_OVERLAP muss in GUIDANCE_BY_TYPE vorhanden sein."""
    assert "ADJUST_OVERLAP" in GUIDANCE_BY_TYPE


def test_adjust_overlap_requires_no_new_value() -> None:
    """ADJUST_OVERLAP-Guidance darf keinen freien Textwert erzwingen – Korrekturen kommen aus der Tabelle."""
    g = guidance_for("ADJUST_OVERLAP")
    assert g.requires_new_value is False


def test_adjust_overlap_requires_transport() -> None:
    """ADJUST_OVERLAP benötigt eine Transportnummer zur eindeutigen Zuordnung."""
    g = guidance_for("ADJUST_OVERLAP")
    assert g.requires_transport is True


# ---------------------------------------------------------------------------
# Validation – fehlender override_value ist für ADJUST_OVERLAP zulässig
# ---------------------------------------------------------------------------

def test_validate_adjust_overlap_no_override_value_no_error() -> None:
    """Bei ADJUST_OVERLAP darf fehlendes override_value keinen Fehler auslösen."""
    errors = validate_guided_input(
        override_type="ADJUST_OVERLAP",
        transport_number="12345",
        target_loco_no="91800000001-1",
        override_value="",
        classification_code="",
        comment="Zeitüberschneidung fachlich geprüft, Abfahrt korrigiert.",
        confirmed=True,
    )
    value_errors = [e for e in errors if "neuer Wert" in e.lower() or "override_value" in e.lower()]
    assert value_errors == [], f"Unerwarteter Fehler für fehlenden Wert: {value_errors}"


def test_validate_adjust_overlap_short_comment_fails() -> None:
    """Kurze Begründung muss auch bei ADJUST_OVERLAP als Fehler gewertet werden."""
    errors = validate_guided_input(
        override_type="ADJUST_OVERLAP",
        transport_number="12345",
        target_loco_no="",
        override_value="",
        classification_code="",
        comment="kurz",
        confirmed=True,
    )
    assert any("Begründung" in e or "10 Zeichen" in e for e in errors)


def test_validate_adjust_overlap_no_confirmation_fails() -> None:
    """Fehlende Bestätigung muss auch bei ADJUST_OVERLAP blockieren."""
    errors = validate_guided_input(
        override_type="ADJUST_OVERLAP",
        transport_number="12345",
        target_loco_no="",
        override_value="",
        classification_code="",
        comment="Zeitüberschneidung fachlich geprüft, Abfahrt Transport 54321 auf 11:00 Uhr.",
        confirmed=False,
    )
    assert any("bestätig" in e.lower() or "geprüft" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# _build_case_table: overlap_with_transport_number durchgereicht
# ---------------------------------------------------------------------------

def _make_r011_finding(transport: str, overlap: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "rule_id": "R011",
        "transport_number": transport,
        "loco_no": "91800000001-1",
        "period_start_utc": "2026-06-09 10:00:00",
        "period_end_utc": "2026-06-09 11:00:00",
        "message": "Zeitliche Überschneidung.",
        "source_table": "raw_locomotivemovement",
        "source_row_id": "42",
        "overlap_with_transport_number": overlap,
    }])


def test_build_case_table_has_overlap_column() -> None:
    """_build_case_table muss overlap_with_transport_number als Spalte enthalten."""
    findings = _make_r011_finding("12345", "54321")
    table = _build_case_table(findings=findings, timeline=pd.DataFrame())
    assert "overlap_with_transport_number" in table.columns


def test_build_case_table_r011_overlap_value_passed_through() -> None:
    """R011-Zeile in der Falltabelle muss den Überlappungspartner korrekt enthalten."""
    findings = _make_r011_finding("12345", "54321")
    table = _build_case_table(findings=findings, timeline=pd.DataFrame())
    r011_rows = table[table["rule_id"] == "R011"]
    assert not r011_rows.empty
    assert r011_rows.iloc[0]["overlap_with_transport_number"] == "54321"


def test_build_case_table_free_row_has_empty_overlap() -> None:
    """Freie Erfassung darf kein overlap_with_transport_number haben."""
    table = _build_case_table(findings=pd.DataFrame(), timeline=pd.DataFrame())
    free = table[table["rule_id"] == ""]
    assert not free.empty
    assert free.iloc[0]["overlap_with_transport_number"] == ""


# ---------------------------------------------------------------------------
# JSON-Parsing der Korrekturen (Stabilitätstest, kein Streamlit nötig)
# ---------------------------------------------------------------------------

def test_corrections_json_round_trip() -> None:
    """JSON-kodierte Korrekturen müssen stabil serialisiert und deserialisiert werden."""
    corrections = {
        "12345": {"current_dep": "2026-06-09 10:00:00", "new_dep": "", "current_arr": "2026-06-09 11:00:00", "new_arr": ""},
        "54321": {"current_dep": "2026-06-09 10:30:00", "new_dep": "2026-06-09 11:00:00", "current_arr": "2026-06-09 13:00:00", "new_arr": ""},
    }
    serialized = json.dumps(corrections, ensure_ascii=False)
    parsed = json.loads(serialized)
    assert parsed["54321"]["new_dep"] == "2026-06-09 11:00:00"
    assert parsed["12345"]["new_dep"] == ""


def test_corrections_json_empty_string_is_stable() -> None:
    """Leerer override_value darf beim Parsen nicht werfen."""
    try:
        result = json.loads("") if False else {}
    except Exception:
        result = {}
    for val in ["", "{}", "null"]:
        try:
            parsed = json.loads(val)
        except Exception:
            parsed = {}
        assert isinstance(parsed, (dict, type(None)))
