from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operational_day_filter_module as operational_day_filter  # noqa: E402
import operational_day_filter_ui_runtime_bridge as bridge  # noqa: E402
from operational_day_filter_ui_runtime_bridge import (  # noqa: E402
    CANONICAL_FROM_KEY,
    CANONICAL_TO_KEY,
    EARLY_FROM_KEY,
    EARLY_TO_KEY,
)


class _FakeSidebar:
    def __init__(self) -> None:
        self.date_input_keys: list[str] = []
        self.messages: list[str] = []

    def divider(self) -> None:
        return None

    def header(self, *_args, **_kwargs) -> None:
        return None

    def caption(self, message: str, *_args, **_kwargs) -> None:
        self.messages.append(str(message))

    def warning(self, message: str, *_args, **_kwargs) -> None:
        self.messages.append(str(message))

    def info(self, message: str, *_args, **_kwargs) -> None:
        self.messages.append(str(message))

    def date_input(self, _label: str, *, value, key: str, **_kwargs):
        self.date_input_keys.append(key)
        return value


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, object] = {}
        self.sidebar = _FakeSidebar()


def test_early_operational_day_filter_uses_private_widget_keys():
    assert CANONICAL_FROM_KEY == "operational_day_filter_from"
    assert CANONICAL_TO_KEY == "operational_day_filter_to"
    assert EARLY_FROM_KEY != CANONICAL_FROM_KEY
    assert EARLY_TO_KEY != CANONICAL_TO_KEY
    assert EARLY_FROM_KEY.startswith("_early_")
    assert EARLY_TO_KEY.startswith("_early_")


def test_early_filter_publishes_canonical_keys_without_legacy_duplicate_inputs(monkeypatch):
    fake_st = _FakeStreamlit()
    monkeypatch.setattr(bridge, "st", fake_st)
    monkeypatch.setattr(
        operational_day_filter,
        "default_operational_day",
        lambda reference_date=None: date(2026, 6, 28),
    )

    selected_range = bridge.render_early_sidebar_operational_day_filter()

    assert selected_range == (date(2026, 6, 28), date(2026, 6, 28))
    assert fake_st.sidebar.date_input_keys == [EARLY_FROM_KEY, EARLY_TO_KEY]
    assert CANONICAL_FROM_KEY not in fake_st.sidebar.date_input_keys
    assert CANONICAL_TO_KEY not in fake_st.sidebar.date_input_keys
    assert fake_st.session_state[CANONICAL_FROM_KEY] == date(2026, 6, 28)
    assert fake_st.session_state[CANONICAL_TO_KEY] == date(2026, 6, 28)

    original_renderer = bridge.install_operational_day_filter_runtime(selected_range)
    try:
        legacy_result = operational_day_filter.render_sidebar_operational_day_filter()
    finally:
        bridge.restore_operational_day_filter_runtime(original_renderer)

    assert legacy_result == selected_range
    assert fake_st.sidebar.date_input_keys == [EARLY_FROM_KEY, EARLY_TO_KEY]
