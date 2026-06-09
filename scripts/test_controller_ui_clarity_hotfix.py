from __future__ import annotations
import sys, types
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.modules.setdefault("streamlit", types.SimpleNamespace())
import operator_ui_module as operator_ui
import manual_override_ui_module as manual_ui

def main() -> int:
    problem, action = operator_ui._friendly_rule("R012", "Planungs-/Dummy-Lok erkannt und aus fachlicher Verarbeitung ausgeschlossen.")
    assert problem == "Dummy-Lok", problem
    assert "Echte Loknummer" in action, action
    missing_problem, _ = operator_ui._friendly_rule("R012", "Loknummer fehlt.")
    assert missing_problem == "Loknummer fehlt", missing_problem
    gate = pd.DataFrame([{"gate_status":"BLOCKED","loco_no":"DUMMY-1","coverage_date":"2026-06-06","performing_rus":"","coverage_pct":0,"unresolved_gap_minutes":0,"overlap_minutes":0,"gate_reason":"ERROR-Findings=1"}])
    findings = pd.DataFrame([{"rule_id":"R012","row_type":"RAW_DUMMY_LOCOMOTIVE","loco_no":"DUMMY-1","message":"Planungs-/Dummy-Lok erkannt und aus fachlicher Verarbeitung ausgeschlossen."}])
    gate_display = operator_ui._friendly_gate_table(gate, only_status="BLOCKED", findings=findings)
    assert gate_display.loc[0, "Warum?"] == "Dummy-Lok", gate_display
    suggestions = pd.DataFrame([
      {"suggestion_type":"GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS","confidence":"HIGH","suggested_value":"LTE DE","transport_number":"T1","loco_no":"L1","period_start_utc":"2026-06-06T10:00:00","period_end_utc":"2026-06-06T10:33:00","reason":"Gap"},
      {"suggestion_type":"LOCO_NO_REVIEW","confidence":"LOW","suggested_value":"","transport_number":"T2","loco_no":"","period_start_utc":"2026-06-06T10:00:00","period_end_utc":"2026-06-06T11:00:00","reason":"Kein Gap"},
    ])
    display = manual_ui._suggestion_display_table(suggestions)
    assert "GAP-Minuten" in display.columns, display.columns
    assert int(display.loc[0, "GAP-Minuten"]) == 33, display
    assert pd.isna(display.loc[1, "GAP-Minuten"]), display
    print("OK: Dummy-Lok-Klartext und GAP-Minuten erfolgreich getestet.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
