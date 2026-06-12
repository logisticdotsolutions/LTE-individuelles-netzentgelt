from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import zuordnungen_ui_runtime_bridge as module  # noqa: E402


class DummyTab:
    def __init__(self, label: str) -> None:
        self.label = label
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1
        return False


def test_install_extension_wraps_only_export_tab_and_restores_original_tabs(monkeypatch) -> None:
    rendered_extensions: list[str] = []

    def original_tabs(labels):
        return [DummyTab(str(label)) for label in labels]

    monkeypatch.setattr(module.st, "tabs", original_tabs)
    monkeypatch.setattr(
        module,
        "render_zuordnungen_export_extension",
        lambda: rendered_extensions.append("rendered"),
    )

    restored_tabs = module.install_zuordnungen_export_tab_extension()
    tabs = module.st.tabs([
        "1. Tagesprüfung",
        module.EXPORT_TAB_LABEL,
        "6. Weitere Prüfungen",
    ])

    assert restored_tabs is original_tabs
    assert tabs[0].label == "1. Tagesprüfung"
    assert tabs[2].label == "6. Weitere Prüfungen"
    assert isinstance(tabs[1], module._InjectedExportTab)

    with tabs[0]:
        pass

    assert rendered_extensions == []

    with tabs[1]:
        pass

    assert rendered_extensions == ["rendered"]

    module.restore_zuordnungen_export_tab_extension(restored_tabs)
    assert module.st.tabs is original_tabs


def test_install_extension_leaves_unrelated_tab_sets_unchanged(monkeypatch) -> None:
    def original_tabs(labels):
        return [DummyTab(str(label)) for label in labels]

    monkeypatch.setattr(module.st, "tabs", original_tabs)

    restored_tabs = module.install_zuordnungen_export_tab_extension()
    tabs = module.st.tabs(["A", "B"])

    assert restored_tabs is original_tabs
    assert all(isinstance(tab, DummyTab) for tab in tabs)

    module.restore_zuordnungen_export_tab_extension(restored_tabs)
    assert module.st.tabs is original_tabs


def test_render_extension_calls_both_holding_downloads(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    rendered_ids: list[str] = []

    monkeypatch.setattr(module, "DB_PATH", db_path)
    monkeypatch.setattr(module.st, "divider", lambda: None)
    monkeypatch.setattr(module.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.st, "session_state", {})
    monkeypatch.setattr(
        module,
        "_render_holding_download",
        lambda **kwargs: rendered_ids.append(kwargs["holding_market_partner_id"]),
    )

    module.render_zuordnungen_export_extension()

    assert rendered_ids == list(module.LTE_HOLDING_MARKET_PARTNER_IDS)
