"""Portable SharePoint entrypoint for the Netzentgelt Streamlit app.

This wrapper runs only in the portable release. It loads encrypted runtime
configuration and seeds default local users before delegating to the existing
secure_app.py entrypoint. The existing application entrypoint remains unchanged
for normal development starts via RUN_TOOL.bat.
"""

from __future__ import annotations

from pathlib import Path
import runpy
import sys

import streamlit as st


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BASE_DIR / "scripts"
SECURE_APP_PATH = BASE_DIR / "app" / "secure_app.py"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from portable_runtime_config_v2 import (  # noqa: E402
    PortableRuntimeConfigError,
    apply_portable_azure_environment,
    seed_portable_users_if_required,
)

PORTABLE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_SHAREPOINT_ENTRYPOINT_PHASE12A_V1_20260621"

try:
    apply_portable_azure_environment(required=True)
    seed_portable_users_if_required()
except PortableRuntimeConfigError as error:
    st.error(f"Portable Konfiguration ungültig: {error}")
    st.stop()

runpy.run_path(str(SECURE_APP_PATH), run_name="__main__")
