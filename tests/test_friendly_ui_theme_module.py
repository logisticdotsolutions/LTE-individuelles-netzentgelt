from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import friendly_ui_theme_module as module


def test_apply_theme_is_compatibility_noop():
    assert module.apply_theme() is False
    assert module.apply_theme(dark_mode=True) is True


def test_render_theme_toggle_does_not_render_sidebar_control():
    assert module.render_theme_toggle() is False
