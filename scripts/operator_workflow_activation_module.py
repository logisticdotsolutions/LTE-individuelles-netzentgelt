"""Activate the operator workflow around one authenticated UI run."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Iterator

from browser_title_module import DEFAULT_BROWSER_TITLE, enforce_browser_title
from local_auth_module import UserContext
from operator_tour_module import render_operator_tour_sidebar
from operator_workflow_runtime_bridge import operator_workflow_runtime

PHASE10A_WORKFLOW_ACTIVATION_MARKER = "NETZENTGELT_OPERATOR_WORKFLOW_ACTIVATION_PHASE10A_V1_20260611"

@contextmanager
def activated_operator_workflow(user: UserContext) -> Iterator[None]:
    """Render help controls and keep the fachliche title stable around the legacy app."""
    enforce_browser_title(DEFAULT_BROWSER_TITLE)
    render_operator_tour_sidebar()
    try:
        with operator_workflow_runtime(user):
            yield
    finally:
        enforce_browser_title(DEFAULT_BROWSER_TITLE)
