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

from ae01_hardened_runtime_bridge import (  # noqa: E402
    install_ae01_hardened_runtime,
    restore_ae01_hardened_runtime,
)
from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title  # noqa: E402
from compact_login_ui_runtime_module import install_compact_login_views  # noqa: E402
from export_exception_runtime_bridge import export_exception_runtime  # noqa: E402
from export_exception_ui_module import (  # noqa: E402
    render_export_exception_area,
    render_export_exception_sidebar_toggle,
)
from fallpruefung_review_runtime_bridge import (  # noqa: E402
    install_fallpruefung_review_integration,
    restore_fallpruefung_review_integration,
)
from friendly_ui_copy_runtime_module import install_compact_copy_runtime  # noqa: E402
from friendly_ui_density_module import apply_density_cleanup  # noqa: E402
from friendly_ui_theme_module import apply_theme, render_theme_toggle  # noqa: E402
from local_auth_runtime_bridge import authenticated_runtime  # noqa: E402
from manual_override_gap_policy_runtime_module import install_gap_policy_labels  # noqa: E402
from n01_hardened_runtime_bridge import (  # noqa: E402
    install_n01_hardened_runtime,
    restore_n01_hardened_runtime,
)
from operational_day_filter_ui_runtime_bridge import (  # noqa: E402
    install_operational_day_filter_runtime,
    render_early_sidebar_operational_day_filter,
    restore_operational_day_filter_runtime,
)
from remove_vens_runtime_module import install_remove_vens_runtime  # noqa: E402

install_compact_copy_runtime()
install_compact_login_views()
install_gap_policy_labels()
install_remove_vens_runtime()

from local_auth_ui_module import (  # noqa: E402
    render_admin_area,
    render_authenticated_sidebar,
    require_local_login,
)
from role_scope_runtime_bridge import role_scoped_runtime  # noqa: E402
from zuordnungen_hardened_runtime_bridge import (  # noqa: E402
    install_zuordnungen_hardened_runtime,
    restore_zuordnungen_hardened_runtime,
)
from zuordnungen_ui_runtime_bridge import (  # noqa: E402
    install_zuordnungen_export_tab_extension,
    restore_zuordnungen_export_tab_extension,
)


PHASE9A_SECURE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_ENTRYPOINT_PHASE9A_V1_20260610"
PHASE9B_SCOPE_ENTRYPOINT_MARKER = "NETZENTGELT_PORTABLE_ROLE_SCOPE_ENTRYPOINT_PHASE9B_V1_20260610"
PHASE9C_EXCEPTION_ENTRYPOINT_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_ENTRYPOINT_PHASE9C_V1_20260610"
PHASE9C_BARE_START_GUARD_MARKER = "NETZENTGELT_STREAMLIT_BARE_START_GUARD_PHASE9C_V1_20260610"
PHASE9D_BROWSER_TITLE_MARKER = "NETZENTGELT_BROWSER_TITLE_ENTRYPOINT_PHASE9D_V1_20260610"
PHASE10C_COMPACT_LOGIN_ENTRYPOINT_MARKER = "NETZENTGELT_COMPACT_LOGIN_ENTRYPOINT_PHASE10C_V1_20260611"
PHASE11A_ZUORDNUNGEN_EXPORT_UI_MARKER = "NETZENTGELT_UKL_ZUORDNUNGEN_EXPORT_UI_PHASE11A_V1_20260611"
PHASE11B_CASE_REVIEW_UI_MARKER = "NETZENTGELT_CASE_REVIEW_INTEGRATION_PHASE11B_V1_20260612"
PHASE11C_UKL_PREFLIGHT_MARKER = "NETZENTGELT_UKL_PREFLIGHT_PHASE11C_V1_20260612"
PHASE11F_FRIENDLY_THEME_MARKER = "NETZENTGELT_FRIENDLY_THEME_PHASE11F_V1_20260612"
PHASE11G_EARLY_DAY_FILTER_MARKER = "NETZENTGELT_EARLY_OPERATIONAL_DAY_FILTER_PHASE11G_V1_20260612"
PHASE11H_GAP_POLICY_LABEL_MARKER = "NETZENTGELT_GAP_POLICY_LABELS_PHASE11H_V1_20260618"
PHASE11L_VENS_REMOVED_MARKER = "NETZENTGELT_VENS_SELECTION_REMOVED_PHASE11L_V1_20260618"


st.set_page_config(
    page_title=DEFAULT_BROWSER_TITLE,
    page_icon="🚆",
    layout="wide",
)
enforce_browser_title(DEFAULT_BROWSER_TITLE)
apply_theme()
apply_density_cleanup()

current_user = require_local_login()
admin_mode = render_authenticated_sidebar(current_user)
render_theme_toggle()
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

_operational_day_range = render_early_sidebar_operational_day_filter()
_original_operational_day_filter = install_operational_day_filter_runtime(
    _operational_day_range
)
_original_set_page_config = st.set_page_config
_n01_runtime = install_n01_hardened_runtime()
_ae01_runtime = install_ae01_hardened_runtime()
_zuordnungen_hardened_runtime = install_zuordnungen_hardened_runtime()
_fallpruefung_runtime = install_fallpruefung_review_integration()
_original_tabs = install_zuordnungen_export_tab_extension()
st.set_page_config = lambda *args, **kwargs: None
try:
    with authenticated_runtime(current_user):
        with role_scoped_runtime(current_user):
            with export_exception_runtime(current_user):
                runpy.run_path(str(LEGACY_APP_PATH), run_name="__main__")
finally:
    restore_zuordnungen_export_tab_extension(_original_tabs)
    restore_fallpruefung_review_integration(_fallpruefung_runtime)
    restore_zuordnungen_hardened_runtime(_zuordnungen_hardened_runtime)
    restore_ae01_hardened_runtime(_ae01_runtime)
    restore_n01_hardened_runtime(_n01_runtime)
    restore_operational_day_filter_runtime(_original_operational_day_filter)
    st.set_page_config = _original_set_page_config
