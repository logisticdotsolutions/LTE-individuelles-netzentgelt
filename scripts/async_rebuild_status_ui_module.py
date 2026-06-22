"""Small UI wrapper for rebuild status messages.

This module avoids stale ERROR banners after a successful manual pipeline run.
"""

from __future__ import annotations

import getpass
from pathlib import Path

import streamlit as st

from async_rebuild_runtime_module import (
    DEFAULT_REBUILD_MODE,
    PIPELINE_ENTRYPOINT,
    read_rebuild_status,
    request_background_rebuild,
)
from pipeline.status import reset_status


ROOT = Path(__file__).resolve().parents[1]
STATUS_UI_MARKER = "NETZENTGELT_ASYNC_REBUILD_STATUS_UI_PHASE13E_V1_20260622"


def render_async_rebuild_status() -> None:
    """Render rebuild status and allow clearing stale error states."""
    status = read_rebuild_status()
    state = str(status.get("state") or "CURRENT").upper()
    mode = str(status.get("mode") or DEFAULT_REBUILD_MODE)

    if state in {"QUEUED", "RUNNING"}:
        st.warning(
            "Neuberechnung laeuft im Hintergrund. Du kannst weiter Korrekturen speichern. "
            "Exporte gelten bis zum Abschluss als nicht final."
        )
        st.caption(
            f"Modus: {mode} · "
            f"Lauf: {status.get('current_run_id') or '-'} · "
            f"Start: {status.get('started_at_utc') or 'wartet'}"
        )
        return

    if state == "PENDING":
        st.warning(
            "Neuberechnung laeuft bereits; weitere Korrekturen wurden vorgemerkt. "
            "Nach dem aktuellen Lauf startet automatisch ein weiterer Prueflauf."
        )
        st.caption(
            f"Modus: {mode} · "
            f"Aktueller Lauf: {status.get('current_run_id') or '-'} · "
            f"Vorgemerkt seit: {status.get('pending_since_utc') or '-'}"
        )
        return

    if state == "ERROR":
        st.error(
            "Die letzte Hintergrund-Neuberechnung ist fehlgeschlagen. "
            "Der letzte gueltige Stand bleibt bestehen."
        )
        col_retry, col_reset = st.columns(2)
        with col_retry:
            if st.button("Neuberechnung erneut starten", key="async_rebuild_retry_button"):
                request_background_rebuild(
                    run_all_script=PIPELINE_ENTRYPOINT,
                    requested_by=getpass.getuser(),
                    reason="manual_retry_after_error",
                    mode=str(mode or DEFAULT_REBUILD_MODE),
                )
                st.rerun()
        with col_reset:
            if st.button("Fehlerhinweis ausblenden", key="async_rebuild_reset_error_button"):
                reset_status(ROOT, reason="ui_error_status_reset")
                st.rerun()

        with st.expander("Technische Details zur Neuberechnung", expanded=False):
            st.caption(f"Modus: {mode}")
            st.caption(f"Lauf: {status.get('current_run_id') or '-'}")
            st.text(status.get("last_error") or "Kein Fehlertext vorhanden.")
            if status.get("last_stdout_path"):
                st.caption(f"stdout: {status.get('last_stdout_path')}")
            if status.get("last_stderr_path"):
                st.caption(f"stderr: {status.get('last_stderr_path')}")
        return

    if status.get("last_success_at_utc"):
        st.success(
            f"Letzte Hintergrund-Neuberechnung erfolgreich: {status.get('last_success_at_utc')} "
            f"({mode})"
        )
