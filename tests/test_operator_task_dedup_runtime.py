from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operator_workflow_runtime_bridge import _deduplicate_task_table  # noqa: E402


def test_missing_loco_gate_and_r012_finding_are_shown_once() -> None:
    table = pd.DataFrame(
        [
            {
                "Status": "⛔ Gesperrt",
                "Datum": "16.06.2026",
                "Problem": "Loknummer fehlt",
                "Transportnummer": "458727",
                "Nutzendes EVU": "LTE DE - LTE Germany GmbH",
                "Naechster Schritt": "Fall prüfen und jede betroffene Minute fachlich schließen.",
                "Prioritaet": "",
                "Loknummer": "None",
                "Von": "None",
                "Bis": "None",
                "Auswirkung": "None",
                "Regel": "None",
            },
            {
                "Status": "None",
                "Datum": "None",
                "Problem": "Loknummer fehlt",
                "Transportnummer": "458727.0",
                "Nutzendes EVU": "LTE DE - LTE Germany GmbH",
                "Naechster Schritt": "Fall prüfen und jede betroffene Minute fachlich schließen.",
                "Prioritaet": "⛔ Blockierend",
                "Loknummer": "",
                "Von": "16.06.2026 02:00",
                "Bis": "17.06.2026 01:57",
                "Auswirkung": "Export gesperrt",
                "Regel": "R012",
            },
        ]
    )

    result = _deduplicate_task_table(table)

    assert len(result) == 1
    assert result.iloc[0]["Transportnummer"] == "458727.0"
    assert result.iloc[0]["Regel"] == "R012"
    assert result.iloc[0]["Status"] == ""
