"""Small UI wrapper for rebuild status messages.

This module avoids stale ERROR banners after a successful manual pipeline run and
shows a clearly visible calculation banner while a background rebuild is active.
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
PROMINENT_LOADING_MARKER = "NETZENTGELT_PROMINENT_REBUILD_LOADING_UI_PHASE14L_V1_20260630"


def _render_loading_card(*, title: str, body: str, detail: str, pending: bool = False) -> None:
    accent = "#ffb020" if pending else "#1f77b4"
    background = "#fff7e6" if pending else "#eaf4ff"
    border = "#f2a100" if pending else "#1f77b4"
    icon = "⏳" if pending else "🔄"
    st.markdown(
        f"""
        <style>
        @keyframes netzentgeltPulse {{
            0% {{ opacity: .45; transform: scaleX(.12); }}
            50% {{ opacity: 1; transform: scaleX(.88); }}
            100% {{ opacity: .45; transform: scaleX(.12); }}
        }}
        .netzentgelt-loading-card {{
            border: 2px solid {border};
            background: {background};
            border-radius: 14px;
            padding: 1.05rem 1.15rem 1rem 1.15rem;
            margin: .35rem 0 1.1rem 0;
            box-shadow: 0 8px 22px rgba(31, 119, 180, .14);
        }}
        .netzentgelt-loading-title {{
            font-size: 1.08rem;
            font-weight: 800;
            color: #1f2937;
            margin-bottom: .25rem;
        }}
        .netzentgelt-loading-body {{
            font-size: .93rem;
            color: #374151;
            margin-bottom: .65rem;
        }}
        .netzentgelt-loading-detail {{
            font-size: .80rem;
            color: #4b5563;
            margin-top: .45rem;
        }}
        .netzentgelt-loading-bar {{
            position: relative;
            height: 9px;
            width: 100%;
            overflow: hidden;
            border-radius: 999px;
            background: rgba(31, 41, 55, .14);
        }}
        .netzentgelt-loading-bar::after {{
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 100%;
            border-radius: 999px;
            background: {accent};
            transform-origin: left center;
            animation: netzentgeltPulse 1.65s ease-in-out infinite;
        }}
        </style>
        <div class="netzentgelt-loading-card">
            <div class="netzentgelt-loading-title">{icon} {title}</div>
            <div class="netzentgelt-loading-body">{body}</div>
            <div class="netzentgelt-loading-bar"></div>
            <div class="netzentgelt-loading-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_async_rebuild_status() -> None:
    """Render rebuild status and allow clearing stale error states."""
    status = read_rebuild_status()
    state = str(status.get("state") or "CURRENT").upper()
    mode = str(status.get("mode") or DEFAULT_REBUILD_MODE)

    if state in {"QUEUED", "RUNNING"}:
        _render_loading_card(
            title="Neuberechnung läuft",
            body=(
                "Das Tool berechnet Datenqualität, GAPs, Zeitachse und Exporte gerade neu. "
                "Du kannst weiterarbeiten, aber Ergebnisse und Exporte sind bis zum Abschluss noch nicht final."
            ),
            detail=(
                f"Modus: {mode} · Lauf: {status.get('current_run_id') or '-'} · "
                f"Start: {status.get('started_at_utc') or 'wartet'}"
            ),
        )
        return

    if state == "PENDING":
        _render_loading_card(
            title="Weitere Neuberechnung vorgemerkt",
            body=(
                "Eine Neuberechnung läuft bereits. Deine letzten Änderungen wurden aufgenommen; "
                "nach dem aktuellen Lauf startet automatisch ein weiterer Prüflauf."
            ),
            detail=(
                f"Modus: {mode} · Aktueller Lauf: {status.get('current_run_id') or '-'} · "
                f"Vorgemerkt seit: {status.get('pending_since_utc') or '-'}"
            ),
            pending=True,
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
