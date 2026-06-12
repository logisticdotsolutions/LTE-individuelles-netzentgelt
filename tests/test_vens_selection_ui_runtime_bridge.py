from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import vens_selection_ui_runtime_bridge as module


def test_runtime_bridge_calls_original_and_extension_with_keyword_timeline(monkeypatch) -> None:
    calls = []

    def original(*args, **kwargs):
        calls.append(("original", args, kwargs))

    monkeypatch.setattr(module.cockpit, "render_manual_override_cockpit", original)
    monkeypatch.setattr(module, "render_vens_selection_area", lambda *, timeline: calls.append(("extension", timeline)))

    runtime = module.install_vens_selection_ui_runtime()
    try:
        module.cockpit.render_manual_override_cockpit(timeline="KW")
    finally:
        module.restore_vens_selection_ui_runtime(runtime)

    assert calls[0][0] == "original"
    assert calls[1] == ("extension", "KW")
    assert module.cockpit.render_manual_override_cockpit is original


def test_runtime_bridge_supports_positional_timeline(monkeypatch) -> None:
    calls = []

    def original(*args, **kwargs):
        pass

    monkeypatch.setattr(module.cockpit, "render_manual_override_cockpit", original)
    monkeypatch.setattr(module, "render_vens_selection_area", lambda *, timeline: calls.append(timeline))

    runtime = module.install_vens_selection_ui_runtime()
    try:
        module.cockpit.render_manual_override_cockpit("db", "script", "findings", "POSITIONAL")
    finally:
        module.restore_vens_selection_ui_runtime(runtime)

    assert calls == ["POSITIONAL"]
