from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import friendly_ui_density_module as module


def test_density_cleanup_renders_compact_css(monkeypatch):
    rendered = []
    monkeypatch.setattr(module.st, "markdown", lambda body, **kwargs: rendered.append((body, kwargs)))

    module.apply_density_cleanup()

    assert len(rendered) == 1
    css, kwargs = rendered[0]
    assert ".block-container" in css
    assert "[data-testid=\"stAlert\"]" in css
    assert "border-left: 0" in css
    assert "[data-testid=\"stSidebar\"] .stButton > button" in css
    assert "[data-testid=\"stExpander\"] summary" in css
    assert "[data-testid=\"stStatusWidget\"]" in css
    assert "[data-testid=\"stSpinner\"]" in css
    assert "color: var(--lte-text) !important;" in css
    assert "fill: var(--lte-accent) !important;" in css
    assert kwargs["unsafe_allow_html"] is True
