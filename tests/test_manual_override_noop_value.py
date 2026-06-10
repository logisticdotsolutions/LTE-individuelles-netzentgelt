from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_guidance_module import is_noop_value, validate_guided_input  # noqa: E402


def test_identical_performing_ru_is_noop_and_rejected() -> None:
    current = "LTE NL - LTE Netherlands B.V."

    assert is_noop_value("SET_PERFORMING_RU", current, current)
    assert not is_noop_value("SET_PERFORMING_RU", current, "LTE DE - LTE Germany GmbH")

    errors = validate_guided_input(
        override_type="SET_PERFORMING_RU",
        transport_number="454496",
        target_loco_no="91515370164-3",
        override_value=current,
        classification_code="",
        comment="Fachlich geprüft, aber der Wert ist bereits identisch.",
        confirmed=True,
        current_value=current,
    )

    assert any("keine tatsächliche Änderung" in error for error in errors)


def test_identical_timestamp_with_different_format_is_noop() -> None:
    assert is_noop_value(
        "SET_ACTUAL_DEPARTURE",
        "2026-06-08 03:37:00",
        "2026-06-08T03:37:00Z",
    )
