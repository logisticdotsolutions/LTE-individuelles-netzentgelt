from __future__ import annotations

import getpass

import pandas as pd
import streamlit as st

from vens_selection_store import candidate_label, candidates_for_performing_ru, save_mapping


_RENDER_GUARD_KEY = "_vens_selection_ui_rendered_this_run"


def reset_vens_selection_render_guard() -> None:
    """Allow the vEns selection area to be rendered once during the current UI run."""
    st.session_state[_RENDER_GUARD_KEY] = False


def _claim_vens_selection_render() -> bool:
    """Return True only for the first real vEns widget render of one Streamlit run."""
    if bool(st.session_state.get(_RENDER_GUARD_KEY, False)):
        return False
    st.session_state[_RENDER_GUARD_KEY] = True
    return True


def _widget_key(key_prefix: str, name: str) -> str:
    return f"{key_prefix}_{name}"


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _case_rows(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline is None or timeline.empty:
        return pd.DataFrame()
    rows = timeline.copy()
    if "performing_ru" not in rows.columns:
        return pd.DataFrame()
    rows = rows[rows["performing_ru"].fillna("").astype(str).str.strip().ne("")].copy()
    if rows.empty:
        return rows
    for column in ("loco_no", "transport_number", "period_start_utc", "period_end_utc"):
        if column not in rows.columns:
            rows[column] = ""
    rows["_label"] = rows.apply(
        lambda row: (
            f"{_clean(row.get('performing_ru'))} | Lok {_clean(row.get('loco_no')) or '-'} "
            f"| Transport {_clean(row.get('transport_number')) or '-'} "
            f"| {_clean(row.get('period_start_utc')) or '-'}"
        ),
        axis=1,
    )
    return rows.drop_duplicates(subset=["_label"]).reset_index(drop=True)


def render_vens_selection_area(
    *,
    timeline: pd.DataFrame,
    key_prefix: str = "vens_selection",
) -> None:
    cases = _case_rows(timeline)
    if cases.empty:
        st.info("Keine Timeline-Zeilen mit nutzendem EVU gefunden.")
        return

    if not _claim_vens_selection_render():
        return

    st.divider()
    st.subheader("Nutzer-vEns auswählen oder korrigieren")
    st.caption(
        "Die Auswahl wirkt ausschließlich auf die UKL-Exporte. RailCube-Rohdaten bleiben unverändert. "
        "Bei mehreren gültigen Nutzer-vEns muss der fachlich passende Wert bewusst gewählt werden."
    )

    selected_label = st.selectbox(
        "Fall für vEns-Auswahl",
        cases["_label"].tolist(),
        key=_widget_key(key_prefix, "case"),
    )
    selected = cases[cases["_label"].eq(selected_label)].iloc[0]
    performing_ru = _clean(selected.get("performing_ru"))
    candidates = candidates_for_performing_ru(performing_ru)

    if not candidates:
        st.error(f"Keine Nutzer-vEns im UKL-Katalog für {performing_ru} gefunden.")
        return

    by_label = {candidate_label(row): row for row in candidates}
    st.write(f"Nutzendes EVU: **{performing_ru}**")
    selected_candidate_label = st.selectbox(
        "Nutzer-vEns",
        list(by_label),
        key=_widget_key(key_prefix, "value"),
    )
    selected_candidate = by_label[selected_candidate_label]

    scope = st.radio(
        "Gültigkeit der Auswahl",
        ["Nur für diesen Zeitraum", "Als Standard ab Fallbeginn"],
        key=_widget_key(key_prefix, "scope"),
    )
    start_value = _clean(selected.get("period_start_utc"))
    end_value = _clean(selected.get("period_end_utc"))
    valid_from = st.text_input(
        "Gültig ab (UTC)",
        value=start_value,
        key=_widget_key(key_prefix, "from"),
    )
    valid_to = st.text_input(
        "Gültig bis (UTC)",
        value=end_value if scope == "Nur für diesen Zeitraum" else "",
        key=_widget_key(key_prefix, "to"),
    )
    priority = 10 if scope == "Nur für diesen Zeitraum" else 100
    st.caption(f"Technische Priorität: {priority}. Kleinere Zahl gewinnt bei der Auflösung.")
    changed_by = st.text_input(
        "Bearbeiter",
        value=getpass.getuser(),
        key=_widget_key(key_prefix, "by"),
    )
    comment = st.text_area(
        "Begründung / Kommentar",
        key=_widget_key(key_prefix, "comment"),
    )

    if st.button(
        "vEns-Mapping speichern",
        type="primary",
        key=_widget_key(key_prefix, "save"),
    ):
        try:
            action = save_mapping(
                performing_ru=performing_ru,
                user_vens=selected_candidate["user_vens"],
                valid_from_utc=valid_from,
                valid_to_utc=valid_to,
                priority=priority,
                changed_by=changed_by or getpass.getuser(),
                comment=comment,
            )
        except ValueError as error:
            st.error(str(error))
            return
        if action == "UNCHANGED":
            st.info("Dieses Mapping ist bereits vorhanden.")
        else:
            st.success("vEns-Mapping wurde gespeichert. Bitte anschließend neu prüfen.")
