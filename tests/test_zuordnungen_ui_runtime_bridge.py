from __future__ import annotations

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


def test_install_extension_uses_compact_export_grid_without_patching_tabs(monkeypatch) -> None:
    install_calls: list[Path] = []
    restore_calls: list[object] = []
    sentinel = object()

    def original_tabs(labels):
        return [DummyTab(str(label)) for label in labels]

    monkeypatch.setattr(module.st, "tabs", original_tabs)
    monkeypatch.setattr(module, "_COMPACT_EXPORT_GRID_RUN_PATH", None)
    monkeypatch.setattr(
        module,
        "install_compact_export_grid_runtime",
        lambda path: install_calls.append(path) or sentinel,
    )
    monkeypatch.setattr(
        module,
        "restore_compact_export_grid_runtime",
        lambda original_run_path: restore_calls.append(original_run_path),
    )

    restored_tabs = module.install_zuordnungen_export_tab_extension()
    tabs = module.st.tabs([
        "1. Tagesprüfung",
        module.EXPORT_TAB_LABEL,
        "6. Weitere Prüfungen",
    ])

    assert restored_tabs is None
    assert module.st.tabs is original_tabs
    assert install_calls == [module.ROOT / "app" / "app.py"]
    assert tabs[0].label == "1. Tagesprüfung"
    assert tabs[1].label == module.EXPORT_TAB_LABEL
    assert tabs[2].label == "6. Weitere Prüfungen"

    module.restore_zuordnungen_export_tab_extension(restored_tabs)
    assert restore_calls == [sentinel]
    assert module._COMPACT_EXPORT_GRID_RUN_PATH is None
    assert module.st.tabs is original_tabs


def test_install_extension_leaves_unrelated_tab_sets_unchanged(monkeypatch) -> None:
    def original_tabs(labels):
        return [DummyTab(str(label)) for label in labels]

    monkeypatch.setattr(module.st, "tabs", original_tabs)
    monkeypatch.setattr(module, "_COMPACT_EXPORT_GRID_RUN_PATH", None)
    monkeypatch.setattr(module, "install_compact_export_grid_runtime", lambda _path: object())
    monkeypatch.setattr(module, "restore_compact_export_grid_runtime", lambda _original_run_path: None)

    restored_tabs = module.install_zuordnungen_export_tab_extension()
    tabs = module.st.tabs(["A", "B"])

    assert restored_tabs is None
    assert module.st.tabs is original_tabs
    assert all(isinstance(tab, DummyTab) for tab in tabs)

    module.restore_zuordnungen_export_tab_extension(restored_tabs)
    assert module.st.tabs is original_tabs


def test_install_extension_is_idempotent_for_compact_export_grid(monkeypatch) -> None:
    install_calls: list[Path] = []
    restore_calls: list[object] = []
    sentinel = object()

    monkeypatch.setattr(module, "_COMPACT_EXPORT_GRID_RUN_PATH", None)
    monkeypatch.setattr(
        module,
        "install_compact_export_grid_runtime",
        lambda path: install_calls.append(path) or sentinel,
    )
    monkeypatch.setattr(
        module,
        "restore_compact_export_grid_runtime",
        lambda original_run_path: restore_calls.append(original_run_path),
    )

    first = module.install_zuordnungen_export_tab_extension()
    second = module.install_zuordnungen_export_tab_extension()

    assert first is None
    assert second is None
    assert install_calls == [module.ROOT / "app" / "app.py"]

    module.restore_zuordnungen_export_tab_extension(first)

    assert restore_calls == [sentinel]
    assert module._COMPACT_EXPORT_GRID_RUN_PATH is None


def test_render_extension_calls_preview_and_both_holding_downloads(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    rendered_ids: list[str] = []
    preview_calls: list[str] = []

    monkeypatch.setattr(module, "DB_PATH", db_path)
    monkeypatch.setattr(module.st, "divider", lambda: None)
    monkeypatch.setattr(module.st, "subheader", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module.st, "session_state", {})
    monkeypatch.setattr(
        module,
        "_render_preview",
        lambda **_kwargs: preview_calls.append("preview"),
    )
    monkeypatch.setattr(
        module,
        "_render_holding_download",
        lambda **kwargs: rendered_ids.append(kwargs["holding_market_partner_id"]),
    )

    module.render_zuordnungen_export_extension()

    assert preview_calls == ["preview"]
    assert rendered_ids == list(module.LTE_HOLDING_MARKET_PARTNER_IDS)
