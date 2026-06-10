"""Robust browser title helper for the Streamlit wrapper."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


BROWSER_TITLE_MARKER = "NETZENTGELT_BROWSER_TITLE_PHASE9D_V1_20260610"
DEFAULT_BROWSER_TITLE = "Bahnstrom Deutschland - Tagesprüfung"


def browser_title_script(title: str = DEFAULT_BROWSER_TITLE) -> str:
    """Return a tiny safe script that updates the parent Streamlit tab title."""
    encoded = json.dumps(str(title))
    return f"<script>window.parent.document.title = {encoded};</script>"


def enforce_browser_title(title: str = DEFAULT_BROWSER_TITLE) -> None:
    """Set the browser title even when Streamlit falls back to its default label."""
    components.html(browser_title_script(title), height=0, width=0)
