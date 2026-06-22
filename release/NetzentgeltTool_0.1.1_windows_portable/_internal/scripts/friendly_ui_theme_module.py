from __future__ import annotations


SESSION_KEY = "ui_dark_mode"


def apply_theme(*, dark_mode: bool | None = None) -> bool:
    """Keep the compatibility hook but rely on Streamlit's native theme selector."""
    return bool(dark_mode)


def render_theme_toggle() -> bool:
    """Do not render a second theme toggle; Streamlit provides the native selector."""
    return False
