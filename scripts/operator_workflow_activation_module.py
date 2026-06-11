"""Activate the operator workflow around one authenticated UI run."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator

from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title
from dummy_diagnostic_csv_runtime_bridge import dummy_diagnostic_csv_runtime
from local_auth_module import UserContext
from operator_tour_module import render_operator_tour_sidebar
from operator_workflow_runtime_bridge import operator_workflow_runtime

PHASE10B_WORKFLOW_ACTIVATION_MARKER = "NETZENTGELT_OPERATOR_WORKFLOW_ACTIVATION_PHASE10B_V1_20260611"


def _has_streamlit_runtime() -> bool:
    """Return true only while Streamlit evaluates an actual browser session."""
    try:
        from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx
    except ImportError:
        return False
    try:
        return get_script_run_ctx(suppress_warning=True) is not None
    except TypeError:
        return get_script_run_ctx() is not None


@contextmanager
def activated_operator_workflow(user: UserContext) -> Iterator[None]:
    """Render help controls and keep the fachliche title stable around the legacy app."""
    active_ui = _has_streamlit_runtime()
    if active_ui:
        enforce_browser_title(DEFAULT_BROWSER_TITLE)
        render_operator_tour_sidebar()
    try:
        with dummy_diagnostic_csv_runtime():
            with operator_workflow_runtime(user):
                yield
    finally:
        if active_ui:
            enforce_browser_title(DEFAULT_BROWSER_TITLE)
