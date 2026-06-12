from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import friendly_ui_theme_module as module


class DummySidebar:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def toggle(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.value


def test_light_mode_is_default(monkeypatch):
    rendered = []
    monkeypatch.setattr(module.st, "session_state", {})
    monkeypatch.setattr(module.st, "markdown", lambda body, **kwargs: rendered.append(body))

    assert module.apply_theme() is False
    assert "#f7f9fc" in rendered[0]
    assert "#eef3f8" in rendered[0]


def test_dark_mode_palette(monkeypatch):
    rendered = []
    monkeypatch.setattr(module.st, "markdown", lambda body, **kwargs: rendered.append(body))

    assert module.apply_theme(dark_mode=True) is True
    assert "#111827" in rendered[0]
    assert "#182235" in rendered[0]


def test_sidebar_toggle_reapplies_selected_theme(monkeypatch):
    sidebar = DummySidebar(True)
    calls = []
    monkeypatch.setattr(module.st, "sidebar", sidebar)
    monkeypatch.setattr(module.st, "session_state", {})
    monkeypatch.setattr(module, "apply_theme", lambda *, dark_mode=None: calls.append(dark_mode) or bool(dark_mode))

    assert module.render_theme_toggle() is True
    assert calls == [True]
    assert sidebar.calls[0][0] == ("Dunkelmodus",)


def test_form_fields_enforce_readable_text_placeholder_and_autofill(monkeypatch):
    rendered = []
    monkeypatch.setattr(module.st, "markdown", lambda body, **kwargs: rendered.append(body))

    module.apply_theme(dark_mode=False)

    css = rendered[0]
    assert '[data-baseweb="input"] input' in css
    assert 'input::placeholder' in css
    assert 'input:-webkit-autofill' in css
    assert '-webkit-text-fill-color: var(--lte-text)' in css
    assert '-webkit-text-fill-color: var(--lte-muted)' in css
    assert 'box-shadow: 0 0 0 1000px var(--lte-surface) inset' in css
