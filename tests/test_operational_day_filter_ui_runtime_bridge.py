from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operational_day_filter_ui_runtime_bridge as module


class DummySidebar:
    def __init__(self, date_values):
        self.date_values = iter(date_values)
        self.calls = []

    def divider(self):
        self.calls.append(("divider", None))

    def header(self, text):
        self.calls.append(("header", text))

    def caption(self, text):
        self.calls.append(("caption", text))

    def warning(self, text):
        self.calls.append(("warning", text))

    def date_input(self, label, **kwargs):
        self.calls.append(("date_input", label, kwargs))
        return next(self.date_values)


def test_early_sidebar_filter_is_compact_and_normalizes_range(monkeypatch):
    sidebar = DummySidebar([date(2026, 6, 10), date(2026, 6, 8)])
    monkeypatch.setattr(module.st, "sidebar", sidebar)
    monkeypatch.setattr(
        module.operational_day_filter,
        "default_operational_day",
        lambda: date(2026, 6, 9),
    )

    result = module.render_early_sidebar_operational_day_filter()

    assert result == (date(2026, 6, 8), date(2026, 6, 10))
    assert ("header", "Arbeitszeitraum") in sidebar.calls
    assert any(call[0] == "warning" for call in sidebar.calls)
    assert any("Vollständige Kalendertage" in call[1] for call in sidebar.calls if call[0] == "caption")
    assert any("Aktiv: 08.06.2026 00:00 bis 11.06.2026 00:00" in call[1] for call in sidebar.calls if call[0] == "caption")


def test_runtime_returns_pre_rendered_range_and_restores_renderer(monkeypatch):
    def original_renderer():
        return date(2026, 6, 1), date(2026, 6, 1)

    monkeypatch.setattr(
        module.operational_day_filter,
        "render_sidebar_operational_day_filter",
        original_renderer,
    )

    saved_renderer = module.install_operational_day_filter_runtime(
        (date(2026, 6, 10), date(2026, 6, 8))
    )

    assert saved_renderer is original_renderer
    assert module.operational_day_filter.render_sidebar_operational_day_filter() == (
        date(2026, 6, 8),
        date(2026, 6, 10),
    )

    module.restore_operational_day_filter_runtime(saved_renderer)
    assert module.operational_day_filter.render_sidebar_operational_day_filter is original_renderer
