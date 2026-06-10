from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_guidance_module import (  # noqa: E402
    current_value_for,
    guidance_for,
    validate_guided_input,
)


def test_guidance_explains_target_field_and_example() -> None:
    guidance = guidance_for("SET_ACTUAL_DEPARTURE")

    assert guidance.target_field == "ActualDeparture / tatsächliche Abfahrtszeit"
    assert "Neue Abfahrtszeit" in guidance.input_label
    assert guidance.example == "2026-06-07 08:15:00"
    assert guidance.requires_transport


def test_current_value_is_resolved_from_timeline() -> None:
    timeline = pd.DataFrame(
        {
            "transport_number": ["TR-1", "TR-2"],
            "loco_no": ["91806189201-7", "91806189202-5"],
            "actual_departure_ts": ["2026-06-07 08:15:00", "2026-06-07 09:30:00"],
            "actual_arrival_ts": ["2026-06-07 11:45:00", "2026-06-07 12:45:00"],
            "performing_ru": ["LTE DE - LTE Germany GmbH", "LTE NL - LTE Netherlands B.V."],
        }
    )

    assert current_value_for(
        "SET_ACTUAL_DEPARTURE",
        timeline,
        transport_number="TR-1",
    ) == "2026-06-07 08:15:00"
    assert current_value_for(
        "SET_PERFORMING_RU",
        timeline,
        transport_number="TR-2",
    ) == "LTE NL - LTE Netherlands B.V."


def test_guided_validation_requires_valid_time_comment_and_confirmation() -> None:
    errors = validate_guided_input(
        override_type="SET_ACTUAL_ARRIVAL",
        transport_number="TR-1",
        target_loco_no="91806189201-7",
        override_value="not-a-time",
        classification_code="",
        comment="kurz",
        confirmed=False,
    )

    assert any("gültige Zeit" in error for error in errors)
    assert any("mindestens 10 Zeichen" in error for error in errors)
    assert any("bestätige" in error for error in errors)


def test_gap_classification_needs_reason_but_no_new_value() -> None:
    errors = validate_guided_input(
        override_type="CLASSIFY_GAP",
        transport_number="",
        target_loco_no="91806189201-7",
        override_value="",
        classification_code="COLD_STAND",
        comment="Fachlich geprüft und als kalte Abstellung eingeordnet.",
        confirmed=True,
    )

    assert errors == []
