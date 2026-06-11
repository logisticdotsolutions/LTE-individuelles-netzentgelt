"""Robust browser title helper for the Streamlit wrapper."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


BROWSER_TITLE_MARKER = "NETZENTGELT_BROWSER_TITLE_PHASE11A_V1_20260611"
DEFAULT_BROWSER_TITLE = "Bahnstrom Deutschland - Tagesprüfung"


def browser_title_script(title: str = DEFAULT_BROWSER_TITLE) -> str:
    """Return a lightweight client-side guard for browser-title stability."""
    encoded = json.dumps(str(title))
    return f"""
    <script>
    (() => {{
      const expected = {encoded};
      const doc = window.parent.document;
      const apply = () => {{
        if (doc.title !== expected) doc.title = expected;
      }};

      apply();
      window.setTimeout(apply, 250);
      window.setTimeout(apply, 1000);

      const titleNode = doc.querySelector('title');
      if (titleNode && !window.parent.__netzentgeltTitleObserver) {{
        const observer = new MutationObserver(apply);
        observer.observe(titleNode, {{ childList: true, subtree: true, characterData: true }});
        window.parent.__netzentgeltTitleObserver = observer;
      }}
    }})();
    </script>
    """


def enforce_browser_title(title: str = DEFAULT_BROWSER_TITLE) -> None:
    """Preserve the fachliche tab title when Streamlit falls back to its default label."""
    components.html(browser_title_script(title), height=0, width=0)
