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
from async_rebuild_runtime_module import install_async_rebuild_runtime  # noqa: E402
from async_rebuild_status_ui_module import render_async_rebuild_status  # noqa: E402
from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title  # noqa: E402
from compact_login_ui_runtime_module import install_compact_login_views  # noqa: E402
from dual_role_runtime_module import install_dual_operator_role_runtime  # noqa: E402
from export_exception_runtime_bridge import export_exception_runtime  # noqa: E402
from export_exception_ui_module import (  # noqa: E402
    render_export_exception_area,
    render_export_exception_sidebar_toggle,
)
from friendly_ui_copy_runtime_module import install_compact_copy_runtime  # noqa: E402
from friendly_ui_density_module import apply_density_cleanup  # noqa: E402
from friendly_ui_theme_module import apply_theme, render_theme_toggle  # noqa: E402
from holder_grouped_export_runtime_module import install_holder_grouped_export_runtime  # noqa: E402
from local_auth_runtime_bridge import authenticated_runtime  # noqa: E402
from manual_override_gap_policy_runtime_module import install_gap_policy_labels  # noqa: E402
from manual_override_overlap_runtime_module import install_overlap_correction_workflow  # noqa: E402
from manual_override_suggestion_cache_runtime_module import (  # noqa: E402
    install_suggestion_cache_runtime,
)
from n01_hardened_runtime_bridge import (  # noqa: E402
    install_n01_hardened_runtime,
    restore_n01_hardened_runtime,
)
from operational_day_filter_ui_runtime_bridge import (  # noqa: E402
    install_operational_day_filter_runtime,
    render_early_sidebar_operational_day_filter,
    restore_operational_day_filter_runtime,
)
from operator_gate_detail_runtime_module import install_operator_gate_detail_runtime  # noqa: E402
from overlap_tolerance_runtime_module import install_overlap_tolerance_runtime  # noqa: E402
from packaged_subprocess_runtime_bridge import (  # noqa: E402
    install_packaged_subprocess_runtime,
    restore_packaged_subprocess_runtime,
)
from remove_review_tab_runtime_module import (  # noqa: E402
    install_remove_review_tab_runtime,
    restore_remove_review_tab_runtime,
)
from remove_vens_runtime_module import install_remove_vens_runtime  # noqa: E402
from loco_timeline_calendar_runtime_module import (  # noqa: E402
    install_loco_timeline_calendar_runtime,
    restore_loco_timeline_calendar_runtime,
)
from waterfall_overview_runtime_module import (  # noqa: E402
    install_waterfall_overview_runtime,
    restore_waterfall_overview_runtime,
)

install_compact_copy_runtime()
install_compact_login_views()
install_dual_operator_role_runtime()
install_gap_policy_labels()
install_suggestion_cache_runtime()
install_remove_vens_runtime()
install_operator_gate_detail_runtime()
install_overlap_correction_workflow()
install_overlap_tolerance_runtime()
install_holder_grouped_export_runtime()

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
PHASE11M_REVIEW_BLOCK_REMOVED_MARKER = "NETZENTGELT_REVIEW_BLOCK_REMOVED_PHASE11M_V1_20260618"
PHASE11O_GATE_DETAIL_MARKER = "NETZENTGELT_OPERATOR_GATE_DETAIL_PHASE11O_V1_20260618"
PHASE11P_OVERLAP_WORKFLOW_MARKER = "NETZENTGELT_OVERLAP_CORRECTION_WORKFLOW_PHASE11P_V1_20260618"
PHASE11R_REMOVE_REVIEW_TAB_MARKER = "NETZENTGELT_REMOVE_REVIEW_TAB_PHASE11R_V1_20260618"
PHASE11S_DUAL_ROLE_MARKER = "NETZENTGELT_DUAL_OPERATOR_ROLE_PHASE11S_V1_20260618"
PHASE13A_ASYNC_REBUILD_MARKER = "NETZENTGELT_ASYNC_REBUILD_ENTRYPOINT_PHASE13A_V1_20260621"
PHASE13B_OVERLAP_TOLERANCE_MARKER = "NETZENTGELT_OVERLAP_TOLERANCE_ENTRYPOINT_PHASE13B_V1_20260621"
PHASE13E_ASYNC_STATUS_UI_MARKER = "NETZENTGELT_ASYNC_REBUILD_STATUS_UI_PHASE13E_V1_20260622"
PHASE13F_SUGGESTION_CACHE_MARKER = "NETZENTGELT_SUGGESTION_CACHE_PHASE13F_V1_20260622"
PHASE13G_PACKAGED_SUBPROCESS_MARKER = "NETZENTGELT_PACKAGED_SUBPROCESS_ENTRYPOINT_PHASE13G_V1_20260623"
PHASE14C_WATERFALL_OVERVIEW_MARKER = "NETZENTGELT_WATERFALL_OVERVIEW_ENTRYPOINT_PHASE14C_V1_20260629"
PHASE14D_HOLDER_GROUPED_EXPORT_MARKER = "NETZENTGELT_HOLDER_GROUPED_EXPORT_ENTRYPOINT_PHASE14D_V1_20260630"
PHASE14E_LOCO_TIMELINE_CALENDAR_MARKER = "NETZENTGELT_LOCO_TIMELINE_CALENDAR_ENTRYPOINT_PHASE14E_V1_20260630"


st.set_page_config(
    page_title=DEFAULT_BROWSER_TITLE,
    page_icon="🚆",
    layout="wide",
)
enforce_browser_title(DEFAULT_BROWSER_TITLE)
apply_theme()
apply_density_cleanup()
install_async_rebuild_runtime()

current_user = require_local_login()
admin_mode = render_authenticated_sidebar(current_user)
render_theme_toggle()
render_async_rebuild_status()
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
_packaged_subprocess_runtime = install_packaged_subprocess_runtime()
_n01_runtime = install_n01_hardened_runtime()
_ae01_runtime = install_ae01_hardened_runtime()
_zuordnungen_hardened_runtime = install_zuordnungen_hardened_runtime()
_loco_timeline_calendar_runtime = install_loco_timeline_calendar_runtime()
_waterfall_overview_runtime = install_waterfall_overview_runtime()
_original_tabs = install_zuordnungen_export_tab_extension()
_original_review_tabs = install_remove_review_tab_runtime()
st.set_page_config = lambda *args, **kwargs: None
try:
    with authenticated_runtime(current_user):
        with role_scoped_runtime(current_user):
            with export_exception_runtime(current_user):
                runpy.run_path(str(LEGACY_APP_PATH), run_name="__main__")
finally:
    restore_packaged_subprocess_runtime(_packaged_subprocess_runtime)
    restore_remove_review_tab_runtime(_original_review_tabs)
    restore_zuordnungen_export_tab_extension(_original_tabs)
    restore_waterfall_overview_runtime(_waterfall_overview_runtime)
    restore_loco_timeline_calendar_runtime(_loco_timeline_calendar_runtime)
    restore_zuordnungen_hardened_runtime(_zuordnungen_hardened_runtime)
    restore_ae01_hardened_runtime(_ae01_runtime)
    restore_n01_hardened_runtime(_n01_runtime)
    restore_operational_day_filter_runtime(_original_operational_day_filter)
    st.set_page_config = _original_set_page_config
