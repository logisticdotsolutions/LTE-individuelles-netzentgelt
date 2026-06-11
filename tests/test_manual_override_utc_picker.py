from __future__ import annotations

from datetime import date, time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_widget_value_module import combine_utc_picker_value, parse_utc_picker_default  # noqa: E402


def test_utc_picker_emits_strict_timestamp_format() -> None:
    assert combine_utc_picker_value(
        date(2026, 6, 8),
        time(3, 37, 5),
    ) == "2026-06-08 03:37:05"


def test_existing_timestamp_is_parsed_for_picker_default() -> None:
    parsed = parse_utc_picker_default("2026-06-08T03:37:00Z")

    assert parsed is not None
    assert parsed.strftime("%Y-%m-%d %H:%M:%S") == "2026-06-08 03:37:00"
