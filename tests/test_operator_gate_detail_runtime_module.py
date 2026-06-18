from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operator_ui_module as operator_ui  # noqa: E402
from operator_gate_detail_runtime_module import install_operator_gate_detail_runtime  # noqa: E402


def test_gate_row_shows_missing_arrival_despite_full_coverage() -> None:
    install_operator_gate_detail_runtime()
    export_gate = pd.DataFrame([
        {
            "gate_status": "BLOCKED",
            "loco_no": "90802159256-7",
            "coverage_date": "2026-06-16",
            "performing_rus": "RTB CARGO GmbH | LTE AT - LTE Austria GmbH",
            "coverage_pct": 100.0,
            "unresolved_gap_minutes": 0,
            "overlap_minutes": 0,
            "gate_reason": "Manual Reviews=1 | Nicht exportfähige Movements=1",
        }
    ])
    findings = pd.DataFrame([
        {
            "severity": "MANUAL_REVIEW",
            "rule_id": "R003",
            "loco_no": "90802159256-7",
            "transport_number": "458707",
            "performing_ru": "RTB CARGO GmbH",
            "period_start_utc": "2026-06-16T00:30:00",
            "period_end_utc": "",
            "message": "ActualArrival fehlt.",
        }
    ])

    display = operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)

    assert "Ankunftszeit fehlt" in display.loc[0, "Warum?"]
    assert "Transport 458707" in display.loc[0, "Warum?"]
    assert "ActualArrival" in display.loc[0, "Naechster Schritt"]
    assert display.loc[0, "Zeitliche Abdeckung"] == "100 % Zeitkette, aber Pflichtdaten/Prueffall offen"
