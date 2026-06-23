from __future__ import annotations

"""UI lock for full import/rebuild while another rebuild is active.

The operational app has two rebuild paths:
- full import from Azure plus full calculation
- correction/override rebuild in the background

Only one calculation may write to DuckDB/export files at a time. This runtime
bridge disables the full-import button whenever rebuild_status.json shows an
active queued/running/pending rebuild.
"""

from typing import Any

import streamlit as st

from async_rebuild_runtime_module import read_rebuild_status


FULL_IMPORT_LOCK_MARKER = "NETZENTGELT_FULL_IMPORT_LOCK_PHASE13J_V1_20260623"
BUSY_REBUILD_STATES = {"QUEUED", "RUNNING", "PENDING"}
FULL_IMPORT_BUTTON_KEY = "overview_start_new_import"
_PATCHED = False


def is_rebuild_busy(status: dict[str, Any] | None) -> bool:
    """Return True when another pipeline/rebuild run is active."""
    if not isinstance(status, dict):
        return False
    state = str(status.get("state") or "").strip().upper()
    return state in BUSY_REBUILD_STATES


def install_full_import_lock_runtime() -> None:
    """Disable the full import button while a rebuild is already active."""
    global _PATCHED
    if _PATCHED:
        return

    original_button = st.button
    if getattr(original_button, "_netzentgelt_full_import_lock", False):
        _PATCHED = True
        return

    def button_with_full_import_lock(*args, **kwargs):
        key = str(kwargs.get("key") or "")
        if key == FULL_IMPORT_BUTTON_KEY:
            status = read_rebuild_status()
            if is_rebuild_busy(status):
                state = str(status.get("state") or "").upper()
                run_id = str(status.get("current_run_id") or "-")
                st.warning(
                    "Neuberechnung läuft bereits. Der vollständige Datenimport ist gesperrt, "
                    "bis der aktuelle Lauf abgeschlossen ist. Korrekturen können weiter gespeichert "
                    "werden und werden danach automatisch berücksichtigt."
                )
                st.caption(f"Aktueller Status: {state} · Lauf: {run_id}")
                locked_kwargs = dict(kwargs)
                locked_kwargs["disabled"] = True
                original_button(*args, **locked_kwargs)
                return False

        return original_button(*args, **kwargs)

    button_with_full_import_lock._netzentgelt_full_import_lock = True  # type: ignore[attr-defined]
    button_with_full_import_lock._netzentgelt_original_button = original_button  # type: ignore[attr-defined]
    st.button = button_with_full_import_lock
    _PATCHED = True
