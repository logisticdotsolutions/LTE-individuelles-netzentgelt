"""
Secure local entrypoint for the Netzentgelt Streamlit application.

The existing fachliche app remains unchanged and is executed only after a local
user has authenticated. The temporary set_page_config shim is intentionally
scoped to this wrapper because the legacy app still configures the Streamlit
page itself. During the later server migration the wrapper can be replaced by
an Entra-ID adapter without changing the fachliche UI.
"""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
LEGACY_APP_PATH = BASE_DIR / "app" / "app.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from local_auth_ui_module import (  # noqa: E402
    render_admin_area,
    render_authenticated_sidebar,
    require_local_login,
)


PHASE9A_SECURE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_ENTRYPOINT_PHASE9A_V1_20260610"


st.set_page_config(
    page_title="Bahnstrom Deutschland - Tagesprüfung",
    page_icon="🚆",
    layout="wide",
)

current_user = require_local_login()
admin_mode = render_authenticated_sidebar(current_user)

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
    runpy.run_path(str(LEGACY_APP_PATH), run_name="__main__")
finally:
    st.set_page_config = _original_set_page_config
