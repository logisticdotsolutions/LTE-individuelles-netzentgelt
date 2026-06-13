from __future__ import annotations

"""Grenzwerttests für GAP-Schwellwerte im Netzentgelt-MVP.

Abgedeckte Grenzen:
- GAP_THRESHOLD_MINUTES = 15  (run_all.py): GAPs ≤ 15 min werden nicht als GAP-Zeile erzeugt.
- COLD_STAND_PROPOSAL_MIN_MINUTES = 120 (fallpruefung_review_runtime_bridge.py):
  Kaltabstellungsvorschlag nur bei GAP > 120 min (strikt größer als).
- R010 ERROR: gap_duration_minutes > 480.
- R010.5 INFO: gap_duration_minutes <= 480.
"""

from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fallpruefung_review_runtime_bridge as bridge_module
import run_all
from tests.support.builders import build_base_findings, gap


# ---------------------------------------------------------------------------
# GAP_THRESHOLD_MINUTES-Vertrag (Konstantenprüfung)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_gap_creation_threshold_constant_is_15_minutes() -> None:
    """GAP_THRESHOLD_MINUTES muss exakt 15 betragen.

    GAPs mit gap_minutes <= 15 werden in der Pipeline nicht als GAP-Zeile
    in core_loco_timeline eingetragen (Bedingung: gap_minutes > GAP_THRESHOLD_MINUTES).
    """
    assert run_all.GAP_THRESHOLD_MINUTES == 15


# ---------------------------------------------------------------------------
# Kaltabstellungsvorschlag – 119 / 120 / 121 Minuten
# ---------------------------------------------------------------------------

def _de_gap_df(minutes: int) -> pd.DataFrame:
    """Minimale Timeline mit einer DE-relevanten GAP-Zeile."""
    start = pd.Timestamp("2026-06-09 10:00:00")
    return pd.DataFrame([
        {
            "row_type": "GAP",
            "loco_no": "91801234567-8",
            "period_start_utc": start,
            "period_end_utc": start + pd.Timedelta(minutes=minutes),
            "gap_duration_minutes": minutes,
            "gap_relevant_de": True,
            "transport_number": "T-001",
            "source_table": "core_loco_timeline",
            "source_row_id": "gap-1",
        }
    ])


@pytest.mark.unit
def test_cold_stand_proposal_not_created_at_119_minutes() -> None:
    """119 Minuten: unter dem Schwellwert – kein Vorschlag erwartet."""
    result = bridge_module._build_gap_cold_stand_suggestions(_de_gap_df(119))
    assert result == []


@pytest.mark.unit
def test_cold_stand_proposal_not_created_at_exactly_120_minutes() -> None:
    """120 Minuten: exakt am Schwellwert – kein Vorschlag (Bedingung ist strikt >)."""
    result = bridge_module._build_gap_cold_stand_suggestions(_de_gap_df(120))
    assert result == []


@pytest.mark.unit
def test_cold_stand_proposal_created_at_121_minutes() -> None:
    """121 Minuten: strikt über dem Schwellwert – genau ein Vorschlag erwartet."""
    result = bridge_module._build_gap_cold_stand_suggestions(_de_gap_df(121))
    assert len(result) == 1
    assert result[0].classification_code == "COLD_STAND"
    assert result[0].override_type == "CLASSIFY_GAP"


@pytest.mark.unit
def test_cold_stand_proposal_not_created_for_non_de_gap_at_121_minutes() -> None:
    """DE-Relevanz-Flag: GAP mit gap_relevant_de=False erzeugt keinen Vorschlag."""
    df = _de_gap_df(121)
    df["gap_relevant_de"] = False
    result = bridge_module._build_gap_cold_stand_suggestions(df)
    assert result == []


# ---------------------------------------------------------------------------
# R010 / R010.5 Severity-Grenze – 479 / 480 / 481 Minuten
# ---------------------------------------------------------------------------

@pytest.mark.rules
def test_r010_5_info_at_479_minutes(con) -> None:
    """479 Minuten: unter der 8-Stunden-Grenze → R010.5 INFO (nicht blockierend)."""
    build_base_findings(con, [gap(1, minutes=479, transport_number="TR-479")])
    rows = con.execute(
        "select severity, rule_id from dq_findings where transport_number='TR-479'"
    ).fetchall()
    rule_ids = {r[1] for r in rows}
    assert "R010.5" in rule_ids, "479 Minuten muss R010.5 erzeugen"
    assert "R010" not in rule_ids, "479 Minuten darf kein R010 erzeugen"
    severity = next(r[0] for r in rows if r[1] == "R010.5")
    assert severity == "INFO"


@pytest.mark.rules
def test_r010_5_info_at_exactly_480_minutes(con) -> None:
    """480 Minuten: exakt an der 8-Stunden-Grenze → R010.5 INFO (Grenze ist <=)."""
    build_base_findings(con, [gap(1, minutes=480, transport_number="TR-480")])
    rows = con.execute(
        "select severity, rule_id from dq_findings where transport_number='TR-480'"
    ).fetchall()
    rule_ids = {r[1] for r in rows}
    assert "R010.5" in rule_ids, "480 Minuten muss R010.5 erzeugen"
    assert "R010" not in rule_ids, "480 Minuten darf kein R010 ERROR erzeugen"


@pytest.mark.rules
def test_r010_error_at_481_minutes(con) -> None:
    """481 Minuten: strikt über der 8-Stunden-Grenze → R010 ERROR (blockiert Export)."""
    build_base_findings(con, [gap(1, minutes=481, transport_number="TR-481")])
    rows = con.execute(
        "select severity, rule_id from dq_findings where transport_number='TR-481'"
    ).fetchall()
    rule_ids = {r[1] for r in rows}
    assert "R010" in rule_ids, "481 Minuten muss R010 erzeugen"
    severity = next(r[0] for r in rows if r[1] == "R010")
    assert severity == "ERROR"
