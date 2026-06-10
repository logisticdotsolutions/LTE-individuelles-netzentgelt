"""Runtime bridge between the portable login layer and the legacy fachliche UI.

The bridge is intentionally small and reversible. It binds the authenticated
session user to legacy write paths without changing the fachliche override
implementation. This keeps Phase 9A low-risk while making audit attribution
non-editable for operators.
"""

from __future__ import annotations

from contextlib import contextmanager
import getpass
from pathlib import Path
from typing import Any, Iterator

import streamlit as st

from local_auth_module import DEFAULT_DB_PATH, UserContext, append_audit_event
from manual_override_guided_runtime_bridge import guided_correction_widgets


PHASE9A_RUNTIME_BRIDGE_MARKER = "NETZENTGELT_PORTABLE_LOCAL_AUTH_RUNTIME_BRIDGE_PHASE9A_V1_20260610"
PHASE9D_GUIDED_CORRECTION_MARKER = "NETZENTGELT_GUIDED_CORRECTION_PHASE9D_V1_20260610"
_LOCKED_TEXT_INPUT_LABELS = {
    "Bearbeiter",
    "Bearbeiter für Sammelübernahme",
}


def _audit(
    *,
    user: UserContext,
    event_type: str,
    object_type: str | None = None,
    object_id: str | None = None,
    comment: str | None = None,
    details: dict[str, Any] | None = None,
    db_path: Path | str | None = None,
) -> None:
    append_audit_event(
        event_type=event_type,
        actor_username=user.username,
        actor_role=user.role_code,
        object_type=object_type,
        object_id=object_id,
        comment=comment,
        details=details,
        db_path=db_path or DEFAULT_DB_PATH,
    )


@contextmanager
def authenticated_runtime(
    user: UserContext,
    db_path: Path | str | None = None,
) -> Iterator[None]:
    """Bind the authenticated user to legacy UI actions for one Streamlit run."""
    import manual_override_ui_module as override_ui

    state_db_path = db_path or DEFAULT_DB_PATH
    original_getuser = getpass.getuser
    original_text_input = st.text_input
    original_append_change_log = override_ui._append_change_log
    original_run_pipeline = override_ui._run_pipeline
    original_dummy_upsert = override_ui.upsert_dummy_locomotive_mapping
    original_render_new_override = override_ui._render_new_override

    def authenticated_getuser() -> str:
        return user.username

    def locked_text_input(label: str, *args: Any, **kwargs: Any) -> Any:
        if str(label) in _LOCKED_TEXT_INPUT_LABELS:
            kwargs = dict(kwargs)
            kwargs["value"] = user.username
            kwargs["disabled"] = True
        return original_text_input(label, *args, **kwargs)

    def audited_append_change_log(
        *,
        action: str,
        override_id: str,
        override_type: str,
        changed_by: str,
        comment: str,
    ) -> None:
        original_append_change_log(
            action=action,
            override_id=override_id,
            override_type=override_type,
            changed_by=user.username,
            comment=comment,
        )
        _audit(
            user=user,
            event_type=(
                "DEACTIVATE_OVERRIDE"
                if str(action).strip().upper() == "DEACTIVATE"
                else "CREATE_OVERRIDE"
            ),
            object_type="MANUAL_OVERRIDE",
            object_id=override_id,
            comment=comment,
            details={
                "legacy_action": str(action),
                "override_type": str(override_type),
            },
            db_path=state_db_path,
        )

    def audited_run_pipeline(run_all_script: Path):
        _audit(
            user=user,
            event_type="RUN_PIPELINE",
            object_type="PIPELINE",
            object_id=str(run_all_script),
            comment="Pipeline-Neuberechnung aus der Fachoberfläche gestartet.",
            db_path=state_db_path,
        )
        result = original_run_pipeline(run_all_script)
        _audit(
            user=user,
            event_type=("RUN_PIPELINE_SUCCESS" if result.returncode == 0 else "RUN_PIPELINE_FAILED"),
            object_type="PIPELINE",
            object_id=str(run_all_script),
            details={"returncode": int(result.returncode)},
            db_path=state_db_path,
        )
        return result

    def audited_dummy_upsert(*args: Any, **kwargs: Any):
        kwargs = dict(kwargs)
        kwargs["changed_by"] = user.username
        action = original_dummy_upsert(*args, **kwargs)
        loco_no = str(kwargs.get("loco_no", "")).strip()
        reason = str(kwargs.get("reason", "")).strip()
        _audit(
            user=user,
            event_type="MARK_DUMMY_LOCOMOTIVE",
            object_type="LOCOMOTIVE",
            object_id=loco_no,
            comment=reason,
            details={"catalog_action": str(action)},
            db_path=state_db_path,
        )
        return action

    def guided_render_new_override(*args: Any, **kwargs: Any):
        with guided_correction_widgets():
            return original_render_new_override(*args, **kwargs)

    getpass.getuser = authenticated_getuser
    st.text_input = locked_text_input
    override_ui._append_change_log = audited_append_change_log
    override_ui._run_pipeline = audited_run_pipeline
    override_ui.upsert_dummy_locomotive_mapping = audited_dummy_upsert
    override_ui._render_new_override = guided_render_new_override
    try:
        yield
    finally:
        getpass.getuser = original_getuser
        st.text_input = original_text_input
        override_ui._append_change_log = original_append_change_log
        override_ui._run_pipeline = original_run_pipeline
        override_ui.upsert_dummy_locomotive_mapping = original_dummy_upsert
        override_ui._render_new_override = original_render_new_override
