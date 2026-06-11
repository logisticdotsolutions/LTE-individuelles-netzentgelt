"""Show audit correction ids and allow batch deactivation of active overrides."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pandas as pd
import streamlit as st

PHASE10G_ACTIVE_OVERRIDE_BATCH_MARKER = "NETZENTGELT_ACTIVE_OVERRIDE_BATCH_PHASE10G_V1_20260611"


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


def deactivate_selected_overrides(
    overrides: pd.DataFrame,
    selected_ids: list[str],
    *,
    comment: str,
    changed_by: str,
    updated_at_utc: str,
) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    """Deactivate selected active overrides and return one audit row per changed override."""
    selected = {str(value or "").strip() for value in selected_ids if str(value or "").strip()}
    if not selected:
        raise ValueError("Bitte mindestens eine lokale Korrektur auswählen.")
    if not str(comment or "").strip():
        raise ValueError("Bitte eine gemeinsame Begründung für die Deaktivierung erfassen.")

    updated = overrides.copy()
    audit_rows: list[dict[str, str]] = []
    active_mask = ~updated["active_flag"].fillna("Y").astype(str).str.strip().str.upper().isin(["N", "NO", "FALSE", "0"])
    id_mask = updated["override_id"].fillna("").astype(str).str.strip().isin(selected)
    matched = updated.loc[active_mask & id_mask].copy()
    if matched.empty:
        raise ValueError("Keine der ausgewählten Korrekturen ist noch aktiv.")

    matched_ids = set(matched["override_id"].fillna("").astype(str).str.strip().tolist())
    missing = sorted(selected - matched_ids)
    if missing:
        raise ValueError("Mindestens eine ausgewählte Korrektur ist nicht mehr aktiv: " + ", ".join(missing))

    update_mask = updated["override_id"].fillna("").astype(str).str.strip().isin(matched_ids)
    updated.loc[update_mask, "active_flag"] = "N"
    updated.loc[update_mask, "updated_at_utc"] = str(updated_at_utc or "")

    for _, row in matched.iterrows():
        audit_rows.append(
            {
                "action": "DEACTIVATE",
                "override_id": str(row.get("override_id") or "").strip(),
                "override_type": str(row.get("override_type") or "").strip(),
                "changed_by": str(changed_by or "").strip(),
                "comment": str(comment or "").strip(),
            }
        )
    return updated, audit_rows


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
        selected = st.multiselect(
            "Lokale Korrekturen deaktivieren",
            options,
            key="manual_override_deactivate_ids",
            help="Wähle eine oder mehrere Korrektur-IDs aus der Tabelle. Für jede deaktivierte Korrektur wird ein eigener Audit-Eintrag geschrieben.",
        )
        st.caption(f"Ausgewählt zur Deaktivierung: **{len(selected)}**")
        deactivate_comment = st.text_input(
            "Gemeinsame Begründung für die Deaktivierung",
            key="manual_override_deactivate_comment",
        )
        if st.button(
            "Ausgewählte lokale Korrekturen deaktivieren",
            key="manual_override_deactivate_button",
            disabled=not selected,
        ):
            try:
                updated, audit_rows = deactivate_selected_overrides(
                    overrides,
                    selected,
                    comment=deactivate_comment,
                    changed_by=override_ui.getpass.getuser(),
                    updated_at_utc=override_ui.utc_now_text(),
                )
            except ValueError as error:
                st.error(str(error))
                return

            override_ui._write_overrides_atomic(updated)
            for audit_row in audit_rows:
                override_ui._append_change_log(**audit_row)
            st.success(
                f"{len(audit_rows)} lokale Korrektur(en) wurden deaktiviert. Bitte anschließend neu berechnen."
            )
            st.rerun()

    override_ui._render_active_overrides = render_active_overrides_with_id
    try:
        yield
    finally:
        override_ui._render_active_overrides = original_render
