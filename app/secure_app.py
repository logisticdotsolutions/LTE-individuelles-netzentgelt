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

from ae01_hardened_runtime_bridge import install_ae01_hardened_runtime, restore_ae01_hardened_runtime  # noqa: E402
from async_rebuild_runtime_module import install_async_rebuild_runtime  # noqa: E402
from async_rebuild_status_ui_module import render_async_rebuild_status  # noqa: E402
from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title  # noqa: E402
from compact_login_ui_runtime_module import install_compact_login_views  # noqa: E402
from dual_role_runtime_module import install_dual_operator_role_runtime  # noqa: E402
from export_exception_runtime_bridge import export_exception_runtime  # noqa: E402
from export_exception_ui_module import render_export_exception_area, render_export_exception_sidebar_toggle  # noqa: E402
from friendly_ui_copy_runtime_module import install_compact_copy_runtime  # noqa: E402
from friendly_ui_density_module import apply_density_cleanup  # noqa: E402
from friendly_ui_theme_module import apply_theme, render_theme_toggle  # noqa: E402
from holder_grouped_export_runtime_module import install_holder_grouped_export_runtime  # noqa: E402
from local_auth_runtime_bridge import authenticated_runtime  # noqa: E402
from manual_override_gap_policy_runtime_module import install_gap_policy_labels  # noqa: E402
from manual_override_overlap_runtime_module import install_overlap_correction_workflow  # noqa: E402
from manual_override_suggestion_cache_runtime_module import install_suggestion_cache_runtime  # noqa: E402
from n01_hardened_runtime_bridge import install_n01_hardened_runtime, restore_n01_hardened_runtime  # noqa: E402
from operational_day_filter_ui_runtime_bridge import install_operational_day_filter_runtime, render_early_sidebar_operational_day_filter, restore_operational_day_filter_runtime  # noqa: E402
from operator_gate_detail_runtime_module import install_operator_gate_detail_runtime  # noqa: E402
from overlap_tolerance_runtime_module import install_overlap_tolerance_runtime  # noqa: E402
from packaged_subprocess_runtime_bridge import install_packaged_subprocess_runtime, restore_packaged_subprocess_runtime  # noqa: E402
from remove_review_tab_runtime_module import install_remove_review_tab_runtime, restore_remove_review_tab_runtime  # noqa: E402
from remove_vens_runtime_module import install_remove_vens_runtime  # noqa: E402
from loco_timeline_review_queue_runtime_module import install_loco_timeline_review_queue_runtime, restore_loco_timeline_review_queue_runtime  # noqa: E402
from loco_timeline_calendar_runtime_module import install_loco_timeline_calendar_runtime, restore_loco_timeline_calendar_runtime  # noqa: E402
from waterfall_overview_runtime_module import install_waterfall_overview_runtime, restore_waterfall_overview_runtime  # noqa: E402

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

from local_auth_ui_module import render_admin_area, render_authenticated_sidebar, require_local_login  # noqa: E402
from role_scope_runtime_bridge import role_scoped_runtime  # noqa: E402
from zuordnungen_hardened_runtime_bridge import install_zuordnungen_hardened_runtime, restore_zuordnungen_hardened_runtime  # noqa: E402
from zuordnungen_ui_runtime_bridge import install_zuordnungen_export_tab_extension, restore_zuordnungen_export_tab_extension  # noqa: E402

PHASE14F_LOCO_TIMELINE_REVIEW_QUEUE_MARKER = "NETZENTGELT_LOCO_TIMELINE_REVIEW_QUEUE_ENTRYPOINT_PHASE14F_V1_20260630"

st.set_page_config(page_title=DEFAULT_BROWSER_TITLE, page_icon="🚆", layout="wide")
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
_original_operational_day_filter = install_operational_day_filter_runtime(_operational_day_range)
_original_set_page_config = st.set_page_config
_packaged_subprocess_runtime = install_packaged_subprocess_runtime()
_n01_runtime = install_n01_hardened_runtime()
_ae01_runtime = install_ae01_hardened_runtime()
_zuordnungen_hardened_runtime = install_zuordnungen_hardened_runtime()
_loco_timeline_review_queue_runtime = install_loco_timeline_review_queue_runtime()
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
    restore_loco_timeline_review_queue_runtime(_loco_timeline_review_queue_runtime)
    restore_zuordnungen_hardened_runtime(_zuordnungen_hardened_runtime)
    restore_ae01_hardened_runtime(_ae01_runtime)
    restore_n01_hardened_runtime(_n01_runtime)
    restore_operational_day_filter_runtime(_original_operational_day_filter)
    st.set_page_config = _original_set_page_config
