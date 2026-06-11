from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from active_override_id_runtime_module import build_active_override_display  # noqa: E402


def test_build_active_override_display_exposes_correction_id_first() -> None:
    active = pd.DataFrame(
        [
            {
                "override_id": "OVR_ABC123",
                "override_type": "SET_LOCO_NO",
                "target_loco_no": "00000000000-0",
                "transport_number": "T1",
                "target_actual_departure_utc": "2026-06-10T08:15:00",
                "target_actual_arrival_utc": "",
                "override_value": "91806189201-7",
                "comment": "fachlich geprüft",
                "created_by": "tester",
                "created_at_utc": "2026-06-11T09:00:00Z",
            }
        ]
    )

    result = build_active_override_display(
        active,
        {"SET_LOCO_NO": "Loknummer ergänzen oder korrigieren"},
    )

    assert result.columns.tolist()[0] == "Korrektur-ID"
    assert result.loc[0, "Korrektur-ID"] == "OVR_ABC123"
    assert result.loc[0, "Korrektur"] == "Loknummer ergänzen oder korrigieren"
