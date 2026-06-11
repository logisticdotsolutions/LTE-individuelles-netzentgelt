from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from active_override_id_runtime_module import (  # noqa: E402
    build_active_override_display,
    deactivate_selected_overrides,
)


def _overrides() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "override_id": "OVR_ABC123",
                "active_flag": "Y",
                "override_type": "SET_LOCO_NO",
                "target_loco_no": "00000000000-0",
                "transport_number": "T1",
                "target_actual_departure_utc": "2026-06-10T08:15:00",
                "target_actual_arrival_utc": "",
                "override_value": "91806189201-7",
                "comment": "fachlich geprüft",
                "created_by": "tester",
                "created_at_utc": "2026-06-11T09:00:00Z",
                "updated_at_utc": "2026-06-11T09:00:00Z",
            },
            {
                "override_id": "OVR_DEF456",
                "active_flag": "Y",
                "override_type": "SET_PERFORMING_RU",
                "target_loco_no": "91806189201-7",
                "transport_number": "T2",
                "target_actual_departure_utc": "2026-06-10T10:00:00",
                "target_actual_arrival_utc": "",
                "override_value": "LTE DE",
                "comment": "fachlich geprüft",
                "created_by": "tester",
                "created_at_utc": "2026-06-11T09:05:00Z",
                "updated_at_utc": "2026-06-11T09:05:00Z",
            },
            {
                "override_id": "OVR_OLD999",
                "active_flag": "N",
                "override_type": "CASE_NOTE",
                "target_loco_no": "91806189201-7",
                "transport_number": "T3",
                "target_actual_departure_utc": "",
                "target_actual_arrival_utc": "",
                "override_value": "",
                "comment": "bereits deaktiviert",
                "created_by": "tester",
                "created_at_utc": "2026-06-11T09:10:00Z",
                "updated_at_utc": "2026-06-11T09:15:00Z",
            },
        ]
    )


def test_build_active_override_display_exposes_correction_id_first() -> None:
    result = build_active_override_display(
        _overrides().iloc[[0]],
        {"SET_LOCO_NO": "Loknummer ergänzen oder korrigieren"},
    )

    assert result.columns.tolist()[0] == "Korrektur-ID"
    assert result.loc[0, "Korrektur-ID"] == "OVR_ABC123"
    assert result.loc[0, "Korrektur"] == "Loknummer ergänzen oder korrigieren"


def test_deactivate_selected_overrides_updates_all_selected_and_returns_one_audit_row_each() -> None:
    updated, audit_rows = deactivate_selected_overrides(
        _overrides(),
        ["OVR_ABC123", "OVR_DEF456"],
        comment="Korrekturen sind in RailCube umgesetzt",
        changed_by="controller",
        updated_at_utc="2026-06-11T10:00:00Z",
    )

    result = updated.set_index("override_id")
    assert result.loc["OVR_ABC123", "active_flag"] == "N"
    assert result.loc["OVR_DEF456", "active_flag"] == "N"
    assert result.loc["OVR_OLD999", "active_flag"] == "N"
    assert result.loc["OVR_ABC123", "updated_at_utc"] == "2026-06-11T10:00:00Z"
    assert [row["override_id"] for row in audit_rows] == ["OVR_ABC123", "OVR_DEF456"]
    assert all(row["action"] == "DEACTIVATE" for row in audit_rows)
    assert all(row["comment"] == "Korrekturen sind in RailCube umgesetzt" for row in audit_rows)


def test_deactivate_selected_overrides_requires_selection_and_comment() -> None:
    with pytest.raises(ValueError, match="mindestens eine"):
        deactivate_selected_overrides(
            _overrides(),
            [],
            comment="Kommentar",
            changed_by="controller",
            updated_at_utc="2026-06-11T10:00:00Z",
        )

    with pytest.raises(ValueError, match="gemeinsame Begründung"):
        deactivate_selected_overrides(
            _overrides(),
            ["OVR_ABC123"],
            comment="",
            changed_by="controller",
            updated_at_utc="2026-06-11T10:00:00Z",
        )


def test_deactivate_selected_overrides_rejects_stale_or_inactive_selection() -> None:
    with pytest.raises(ValueError, match="nicht mehr aktiv"):
        deactivate_selected_overrides(
            _overrides(),
            ["OVR_ABC123", "OVR_OLD999"],
            comment="fachlich geprüft",
            changed_by="controller",
            updated_at_utc="2026-06-11T10:00:00Z",
        )
