"""Show the audit correction id in the active override table."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import streamlit as st

PHASE10F_ACTIVE_OVERRIDE_ID_MARKER = "NETZENTGELT_ACTIVE_OVERRIDE_ID_PHASE10F_V1_20260611"


def build_active_override_display(active: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    """Return the controller-facing active override table including its correction id."""
    if active is None or active.empty:
        return pd.DataFrame()
    display = active.copy()
    display["override_type"] = display["override_type"].map(labels).fillna(display["override_type"])
    display = display.rename(
        columns={
            "override_id": "Korrektur-ID",
            "override_type": "Korrektur",
            "transport_number": "Transportnummer",
            "target_loco_no": "Loknummer",
            "target_actual_departure_utc": "Von",
            "target_actual_arrival_utc": "Bis",
            "override_value": "Neuer Wert",
            "comment": "Begründung",
            "created_by": "Bearbeiter",
            "created_at_utc": "Erstellt am",
        }
    )
    visible_columns = [
        "Korrektur-ID",
        "Korrektur",
        "Loknummer",
        "Transportnummer",
        "Von",
        "Bis",
        "Neuer Wert",
        "Begründung",
        "Bearbeiter",
        "Erstellt am",
    ]
    return display[[column for column in visible_columns if column in display.columns]].copy()


@contextmanager
def active_override_id_runtime() -> Iterator[None]:
    """Patch only the active-override table rendering for one authenticated UI run."""
    import manual_override_ui_module as override_ui

    original_render = override_ui._render_active_overrides

    def render_active_overrides_with_id() -> None:
        overrides = override_ui._read_overrides()
        if overrides.empty:
            st.info("Noch keine manuellen Overrides vorhanden.")
            return

        active = overrides[
            ~overrides["active_flag"].fillna("Y").astype(str).str.strip().str.upper().isin(["N", "NO", "FALSE", "0"])
        ].copy()
        if active.empty:
            st.success("Keine aktiven Overrides vorhanden.")
            return

        st.dataframe(
            build_active_override_display(active, override_ui.OVERRIDE_TYPE_LABELS),
            use_container_width=True,
            hide_index=True,
        )

        options = active["override_id"].fillna("").astype(str).tolist()
        selected = st.selectbox("Lokale Korrektur deaktivieren", options, key="manual_override_deactivate_id")
        deactivate_comment = st.text_input(
            "Begründung für die Deaktivierung",
            key="manual_override_deactivate_comment",
        )
        if st.button("Ausgewählte lokale Korrektur deaktivieren", key="manual_override_deactivate_button"):
            if not deactivate_comment.strip():
                st.error("Bitte eine Begründung für die Deaktivierung erfassen.")
                return
            mask = overrides["override_id"].fillna("").astype(str).eq(selected)
            overrides.loc[mask, "active_flag"] = "N"
            overrides.loc[mask, "updated_at_utc"] = override_ui.utc_now_text()
            override_ui._write_overrides_atomic(overrides)
            override_ui._append_change_log(
                action="DEACTIVATE",
                override_id=selected,
                override_type=override_ui._clean(overrides.loc[mask, "override_type"].iloc[0]),
                changed_by=override_ui.getpass.getuser(),
                comment=deactivate_comment,
            )
            st.success("Lokale Korrektur wurde deaktiviert. Bitte anschließend neu berechnen.")
            st.rerun()

    override_ui._render_active_overrides = render_active_overrides_with_id
    try:
        yield
    finally:
        override_ui._render_active_overrides = original_render
