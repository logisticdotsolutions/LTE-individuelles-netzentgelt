"""Runtime-Guard fuer die Fallbearbeitung waehrend Hintergrund-Neuberechnung.

Die manuelle Fallauswahl soll auch dann stabil bleiben, wenn im Hintergrund ein
schneller Rebuild laeuft. In diesem Zustand duerfen UI-Callbacks keine
DuckDB-gestuetzten Vorschlaege lesen, weil die Datenbasis gerade aktualisiert
werden kann. Der Guard erlaubt weiterhin manuelle Eingaben auf Basis des zuletzt
sichtbaren CSV-Snapshots und setzt nur die automatische Vorschlagsableitung aus.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import streamlit as st

from async_rebuild_runtime_module import read_rebuild_status
from manual_override_suggestion_module import Suggestion


MANUAL_OVERRIDE_ASYNC_GUARD_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_ASYNC_GUARD_PHASE13I_V1_20260623"
ACTIVE_REBUILD_STATES = {"QUEUED", "RUNNING", "PENDING"}
_PATCHED = False
_ORIGINAL_SUGGESTION_FOR_CASE: Callable[..., Suggestion] | None = None
_ORIGINAL_RENDER_SUGGESTIONS: Callable[..., None] | None = None


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _rebuild_state() -> str:
    status = read_rebuild_status()
    return str(status.get("state") or "CURRENT").strip().upper()


def is_rebuild_active() -> bool:
    return _rebuild_state() in ACTIVE_REBUILD_STATES


def _manual_review_suggestion(
    *,
    override_type: str,
    transport_number: str,
    loco_no: str,
    period_start_utc: str,
    period_end_utc: str = "",
    source_table: str = "",
    source_row_id: str = "",
) -> Suggestion:
    override_type = _clean(override_type).upper()
    suggested_value = ""
    if override_type in {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE"}:
        suggested_value = _clean(period_start_utc)
    elif override_type == "SET_ACTUAL_ARRIVAL":
        suggested_value = _clean(period_end_utc)

    return Suggestion(
        suggestion_id="",
        suggestion_type="MANUAL_REVIEW_DURING_REBUILD",
        override_type=override_type,
        classification_code="",
        confidence="LOW",
        suggested_value=suggested_value,
        transport_number=_clean(transport_number),
        loco_no=_clean(loco_no),
        period_start_utc=_clean(period_start_utc),
        period_end_utc=_clean(period_end_utc),
        source_table=_clean(source_table),
        source_row_id=_clean(source_row_id),
        reason=(
            "Die Hintergrund-Neuberechnung laeuft gerade. Automatische Vorschlaege "
            "werden fuer diesen Moment ausgesetzt; die manuelle Erfassung bleibt moeglich."
        ),
        evidence="Keine DuckDB-Leseoperation waehrend laufender Neuberechnung.",
    )


def _suggestion_for_case_guarded(*args, **kwargs) -> Suggestion:
    if is_rebuild_active():
        return _manual_review_suggestion(
            override_type=kwargs.get("override_type", ""),
            transport_number=kwargs.get("transport_number", ""),
            loco_no=kwargs.get("loco_no", ""),
            period_start_utc=kwargs.get("period_start_utc", ""),
            period_end_utc=kwargs.get("period_end_utc", ""),
            source_table=kwargs.get("source_table", ""),
            source_row_id=kwargs.get("source_row_id", ""),
        )

    if _ORIGINAL_SUGGESTION_FOR_CASE is None:
        raise RuntimeError("Originale Vorschlagsfunktion ist nicht installiert.")
    return _ORIGINAL_SUGGESTION_FOR_CASE(*args, **kwargs)


def _render_suggestions_guarded(*args, **kwargs) -> None:
    if is_rebuild_active():
        st.info(
            "Die Hintergrund-Neuberechnung laeuft gerade. Die Vorschlagsliste wird "
            "nach Abschluss automatisch wieder aus dem neuen Stand aufgebaut. "
            "Neue Korrekturen koennen weiterhin im Reiter 'Neue Korrektur' erfasst werden."
        )
        return

    if _ORIGINAL_RENDER_SUGGESTIONS is None:
        raise RuntimeError("Originale Vorschlagsanzeige ist nicht installiert.")
    _ORIGINAL_RENDER_SUGGESTIONS(*args, **kwargs)


def install_manual_override_async_guard() -> None:
    """Installiert Guards fuer DB-lesende Fallbearbeitungsfunktionen."""
    global _PATCHED, _ORIGINAL_SUGGESTION_FOR_CASE, _ORIGINAL_RENDER_SUGGESTIONS
    if _PATCHED:
        return

    import manual_override_ui_module

    current_suggestion = getattr(manual_override_ui_module, "suggestion_for_case", None)
    if getattr(current_suggestion, "_manual_override_async_guard", False):
        _PATCHED = True
        return

    _ORIGINAL_SUGGESTION_FOR_CASE = current_suggestion
    _ORIGINAL_RENDER_SUGGESTIONS = getattr(manual_override_ui_module, "_render_suggestions", None)

    _suggestion_for_case_guarded._manual_override_async_guard = True  # type: ignore[attr-defined]
    _render_suggestions_guarded._manual_override_async_guard = True  # type: ignore[attr-defined]

    manual_override_ui_module.suggestion_for_case = _suggestion_for_case_guarded
    if _ORIGINAL_RENDER_SUGGESTIONS is not None:
        manual_override_ui_module._render_suggestions = _render_suggestions_guarded

    _PATCHED = True


def restore_manual_override_async_guard() -> None:
    """Nur fuer Tests: setzt die Monkeypatches zurueck."""
    global _PATCHED, _ORIGINAL_SUGGESTION_FOR_CASE, _ORIGINAL_RENDER_SUGGESTIONS
    if not _PATCHED:
        return

    import manual_override_ui_module

    if _ORIGINAL_SUGGESTION_FOR_CASE is not None:
        manual_override_ui_module.suggestion_for_case = _ORIGINAL_SUGGESTION_FOR_CASE
    if _ORIGINAL_RENDER_SUGGESTIONS is not None:
        manual_override_ui_module._render_suggestions = _ORIGINAL_RENDER_SUGGESTIONS

    _PATCHED = False
    _ORIGINAL_SUGGESTION_FOR_CASE = None
    _ORIGINAL_RENDER_SUGGESTIONS = None
