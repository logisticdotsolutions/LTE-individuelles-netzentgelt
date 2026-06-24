from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from zuordnungen_ui_runtime_bridge import _build_export_overview_counts  # noqa: E402


def test_export_overview_counts_are_grouped_by_business_area() -> None:
    export_gate_ru_df = pd.DataFrame(
        [
            {"performing_ru": "LTE DE - LTE Germany GmbH", "gate_status": "BLOCKED"},
            {"performing_ru": "LTE NL - LTE Netherlands B.V.", "gate_status": "BLOCKED"},
            {"performing_ru": "Other RU", "gate_status": "BLOCKED"},
            {"performing_ru": "Other RU", "gate_status": "OK"},
        ]
    )
    findings_df = pd.DataFrame(
        [
            {"performing_ru": "LTE DE - LTE Germany GmbH", "severity": "ERROR"},
            {"performing_ru": "LTE NL - LTE Netherlands B.V.", "severity": "MANUAL_REVIEW"},
            {"performing_ru": "Other RU", "severity": "ERROR"},
            {"performing_ru": "", "severity": "ERROR"},
            {"performing_ru": "Other RU", "severity": "INFO"},
        ]
    )
    global_blockers_df = pd.DataFrame(
        [
            {"gate_status": "BLOCKED"},
            {"gate_status": "OK"},
        ]
    )

    result = _build_export_overview_counts(
        export_gate_ru_df=export_gate_ru_df,
        global_blockers_df=global_blockers_df,
        findings_df=findings_df,
    )

    assert result["lte_de_open"] == 2
    assert result["lte_nl_open"] == 2
    assert result["rest_open"] == 2
    assert result["holding_open"] == 2
    assert result["technical_blocked"] == 4
    assert result["technical_findings"] == 4
