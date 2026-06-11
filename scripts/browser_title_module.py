"""Robust browser title and login-shell helper for the Streamlit wrapper."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


BROWSER_TITLE_MARKER = "NETZENTGELT_BROWSER_TITLE_PHASE10B_V2_20260611"
DEFAULT_BROWSER_TITLE = "Bahnstrom Deutschland - Tagesprüfung"


def browser_title_script(title: str = DEFAULT_BROWSER_TITLE) -> str:
    """Return a client-side guard for title stability and a compact login shell."""
    encoded = json.dumps(str(title))
    return f"""
    <script>
    (() => {{
      const expected = {encoded};
      const doc = window.parent.document;
      const styleId = 'netzentgelt-login-shell-style';

      const hasLoginHeading = () => {{
        const text = Array.from(doc.querySelectorAll('h1, h2, h3'))
          .map(el => (el.innerText || '').trim())
          .join(' | ');
        return text.includes('Bahnstrom Deutschland - Anmeldung')
          || text.includes('Bahnstrom Deutschland - Ersteinrichtung')
          || text.includes('Passwort ändern');
      }};

      const applyLoginShell = () => {{
        const existing = doc.getElementById(styleId);
        if (!hasLoginHeading()) {{
          if (existing) existing.remove();
          return;
        }}
        if (existing) return;
        const style = doc.createElement('style');
        style.id = styleId;
        style.textContent = `
          [data-testid="stAppViewContainer"] .main .block-container {{
            max-width: 560px !important;
            margin-left: auto !important;
            margin-right: auto !important;
            padding-top: 4.5rem !important;
          }}
          [data-testid="stForm"] {{
            border: 1px solid rgba(120,120,120,.24);
            border-radius: 14px;
            padding: 1.1rem 1.2rem 1.2rem 1.2rem;
            box-shadow: 0 8px 24px rgba(0,0,0,.08);
          }}
        `;
        doc.head.appendChild(style);
      }};

      const apply = () => {{
        if (doc.title !== expected) doc.title = expected;
        applyLoginShell();
      }};

      apply();
      window.setTimeout(apply, 250);
      window.setTimeout(apply, 1000);
      window.setTimeout(apply, 2500);

      if (!window.parent.__netzentgeltShellObserver) {{
        const observer = new MutationObserver(apply);
        observer.observe(doc.documentElement, {{ childList: true, subtree: true, characterData: true }});
        window.parent.__netzentgeltShellObserver = observer;
      }}
    }})();
    </script>
    """


def enforce_browser_title(title: str = DEFAULT_BROWSER_TITLE) -> None:
    """Preserve the tab title and show a compact login card only while authentication is visible."""
    components.html(browser_title_script(title), height=0, width=0)
