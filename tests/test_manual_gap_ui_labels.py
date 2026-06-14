from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_gap_case_ui_module import decorate_case_table, decorate_context_table  # noqa: E402


def test_gap_duration_is_visible_in_dropdown_and_context() -> None:
    case = {
        "rule_id": "GAP",
        "transport_number": "454569",
        "loco_no": "91806189201-7",
        "period_start_utc": "2026-06-10 11:25:00",
        "period_end_utc": "2026-06-10 14:58:00",
        "case_label": "old",
    }
    decorated = decorate_case_table(pd.DataFrame([case]))
    assert decorated.loc[0, "gap_duration_minutes"] == 213
    assert "Dauer: 213 Minuten" in decorated.loc[0, "case_label"]

    context = pd.DataFrame([{"Angabe": "Lok", "Aktueller Kontext": "91806189201-7"}])
    decorated_context = decorate_context_table(context, case)
    assert decorated_context.iloc[-1]["Aktueller Kontext"] == "213 Minuten"


def test_r012_dropdown_is_descriptive() -> None:
    case = {
        "rule_id": "R012",
        "transport_number": "T-012",
        "loco_no": "00000000000-0",
        "period_start_utc": "2026-06-10 08:00:00",
        "case_label": "old",
    }
    decorated = decorate_case_table(pd.DataFrame([case]))
    assert decorated.loc[0, "case_label"].startswith("R012 – Loknummer fehlt oder ist technisch")
