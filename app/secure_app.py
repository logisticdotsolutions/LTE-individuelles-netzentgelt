"""
Secure local entrypoint for the Netzentgelt Streamlit application.

The existing fachliche app remains unchanged and is executed only after a local
user has authenticated. Runtime bridges add audit attribution, role scope and
controlled export exceptions around the legacy UI without changing the fachliche
pipeline itself.
"""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
LEGACY_APP_PATH = BASE_DIR / "app" / "app.py"


def _require_streamlit_runtime() -> None:
    """Reject direct Python execution before Streamlit UI code is evaluated."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import (
            get_script_run_ctx,
        )
    except ImportError:
        return

    try:
        context = get_script_run_ctx(suppress_warning=True)
    except TypeError:
        context = get_script_run_ctx()

    if context is None:
        raise SystemExit(
            "FEHLER: Die Netzentgelt-Anwendung ist eine Streamlit-App und darf "
            "nicht direkt mit Python gestartet werden.\n"
            "Starte im Projektordner: .\\RUN_TOOL.bat\n"
            "Alternativ: .venv\\Scripts\\python.exe -m streamlit run "
            "app\\secure_app.py"
        )


_require_streamlit_runtime()

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title  # noqa: E402
from export_exception_runtime_bridge import export_exception_runtime  # noqa: E402
from export_exception_ui_module import (  # noqa: E402
    render_export_exception_area,
    render_export_exception_sidebar_toggle,
)
from local_auth_runtime_bridge import authenticated_runtime  # noqa: E402
from local_auth_ui_module import (  # noqa: E402
    render_admin_area,
    render_authenticated_sidebar,
    require_local_login,
)
from role_scope_runtime_bridge import role_scoped_runtime  # noqa: E402


PHASE9A_SECURE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_ENTRYPOINT_PHASE9A_V1_20260610"
PHASE9B_SCOPE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_ROLE_SCOPE_ENTRYPOINT_PHASE9B_V1_20260610"
PHASE9C_EXCEPTION_ENTRYPOINT_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_ENTRYPOINT_PHASE9C_V1_20260610"
PHASE9C_BARE_START_GUARD_MARKER = "NETZENTGELT_STREAMLIT_BARE_START_GUARD_PHASE9C_V1_20260610"
PHASE9D_BROWSER_TITLE_MARKER = "NETZENTGELT_BROWSER_TITLE_ENTRYPOINT_PHASE9D_V1_20260610"


st.set_page_config(
    page_title=DEFAULT_BROWSER_TITLE,
    page_icon="🚆",
    layout="wide",
)
enforce_browser_title(DEFAULT_BROWSER_TITLE)

current_user = require_local_login()
admin_mode = render_authenticated_sidebar(current_user)
exception_mode = render_export_exception_sidebar_toggle()

if exception_mode:
    render_export_exception_area(current_user)
    st.stop()

if admin_mode:
    render_admin_area(current_user)
    st.stop()

if not LEGACY_APP_PATH.exists():
    st.error(f"Fachanwendung nicht gefunden: {LEGACY_APP_PATH}")
    st.stop()

# app/app.py ruft aus historischen Gründen weiterhin st.set_page_config() auf.
# In diesem sicheren Einstiegspunkt wurde die Konfiguration bereits als erster
# Streamlit-Befehl gesetzt. Der zweite Aufruf wird daher ausschließlich während
# der Ausführung der Fachanwendung kontrolliert ignoriert.
_original_set_page_config = st.set_page_config
st.set_page_config = lambda *args, **kwargs: None
try:
    with authenticated_runtime(current_user):
        with role_scoped_runtime(current_user):
            with export_exception_runtime(current_user):
                runpy.run_path(str(LEGACY_APP_PATH), run_name="__main__")
finally:
    st.set_page_config = _original_set_page_config
