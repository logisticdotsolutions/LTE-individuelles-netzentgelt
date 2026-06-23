from __future__ import annotations

from pathlib import Path
import sys
import types

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import operator_workflow_runtime_bridge as module  # noqa: E402
from operator_workflow_runtime_bridge import load_case_timeline_once  # noqa: E402
from local_auth_module import UserContext  # noqa: E402


def _admin_user() -> UserContext:
    return UserContext("admin", "Admin", "ADMIN", "test-install")


def _inject_context_mocks(monkeypatch):
    """Injiziert Dummy-Module fuer operator_workflow_runtime; gibt fake_override_ui zurueck."""
    fake_override_ui = types.SimpleNamespace(render_manual_override_cockpit=lambda *a, **kw: None)
    fake_operator_ui = types.SimpleNamespace(
        render_operator_dashboard=lambda **kw: None,
        render_open_tasks=lambda **kw: None,
    )
    fake_pipeline_ui = types.SimpleNamespace(render_pipeline_test_controller=lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, "manual_override_ui_module", fake_override_ui)
    monkeypatch.setitem(sys.modules, "operator_ui_module", fake_operator_ui)
    monkeypatch.setitem(sys.modules, "pipeline_test_ui_module", fake_pipeline_ui)
    monkeypatch.setattr(module, "render_case_workspace", lambda **kw: None)
    return fake_override_ui


def test_load_case_timeline_once_calls_loader_only_once() -> None:
    cache: dict[str, pd.DataFrame] = {}
    calls = {"count": 0}

    def loader() -> pd.DataFrame:
        calls["count"] += 1
        return pd.DataFrame([{"loco_no": "9180"}])

    first = load_case_timeline_once(cache, loader=loader)
    second = load_case_timeline_once(cache, loader=loader)

    assert calls["count"] == 1
    assert first is second
    assert first["loco_no"].tolist() == ["9180"]


def test_without_legacy_override_info_suppresses_legacy_message() -> None:
    passed: list[str] = []

    def original_info(body, *args, **kwargs):
        passed.append(str(body))

    filtered = module._without_legacy_override_info(original_info)
    filtered("Lokale Korrekturen ändern weder RailCube noch die importierten Original-CSVs: wichtig")
    filtered("Eine andere Info-Meldung")

    assert passed == ["Eine andere Info-Meldung"]


def test_cockpit_calls_dialog_when_success_message_set(monkeypatch) -> None:
    fake_override_ui = _inject_context_mocks(monkeypatch)
    session: dict = {"override_save_success_message": "Korrektur ABC gespeichert."}
    monkeypatch.setattr(module.st, "session_state", session)
    dialog_calls: list[str] = []
    monkeypatch.setattr(module, "_save_success_dialog", lambda msg: dialog_calls.append(msg))
    monkeypatch.setattr(module, "_navigate_to_fall_bearbeiten_tab", lambda: None)

    with module.operator_workflow_runtime(_admin_user()):
        fake_override_ui.render_manual_override_cockpit()

    assert dialog_calls == ["Korrektur ABC gespeichert."]
    assert "override_save_success_message" not in session


def test_cockpit_no_dialog_when_no_success_message(monkeypatch) -> None:
    fake_override_ui = _inject_context_mocks(monkeypatch)
    session: dict = {}
    monkeypatch.setattr(module.st, "session_state", session)
    dialog_calls: list[str] = []
    monkeypatch.setattr(module, "_save_success_dialog", lambda msg: dialog_calls.append(msg))
    monkeypatch.setattr(module, "_navigate_to_fall_bearbeiten_tab", lambda: None)

    with module.operator_workflow_runtime(_admin_user()):
        fake_override_ui.render_manual_override_cockpit()

    assert dialog_calls == []


def test_cockpit_calls_navigate_when_flag_set(monkeypatch) -> None:
    fake_override_ui = _inject_context_mocks(monkeypatch)
    session: dict = {"navigate_to_fall_bearbeiten": True}
    monkeypatch.setattr(module.st, "session_state", session)
    navigate_calls: list[bool] = []
    monkeypatch.setattr(module, "_navigate_to_fall_bearbeiten_tab", lambda: navigate_calls.append(True))
    monkeypatch.setattr(module, "_save_success_dialog", lambda msg: None)

    with module.operator_workflow_runtime(_admin_user()):
        fake_override_ui.render_manual_override_cockpit()

    assert navigate_calls == [True]
    assert "navigate_to_fall_bearbeiten" not in session


def test_cockpit_no_navigate_when_flag_absent(monkeypatch) -> None:
    fake_override_ui = _inject_context_mocks(monkeypatch)
    session: dict = {}
    monkeypatch.setattr(module.st, "session_state", session)
    navigate_calls: list[bool] = []
    monkeypatch.setattr(module, "_navigate_to_fall_bearbeiten_tab", lambda: navigate_calls.append(True))
    monkeypatch.setattr(module, "_save_success_dialog", lambda msg: None)

    with module.operator_workflow_runtime(_admin_user()):
        fake_override_ui.render_manual_override_cockpit()

    assert navigate_calls == []
