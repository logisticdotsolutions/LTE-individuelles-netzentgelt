"""Streamlit cockpit for documented export exceptions in the local pilot."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from export_exception_query_module import list_required_export_blockers
from export_exception_state_module import (
    create_exception,
    evaluate_release_status,
    list_exceptions,
    list_export_releases,
    revoke_exception,
)
from local_auth_module import DEFAULT_DB_PATH, LocalAuthError, UserContext
from rest_export_module import PRIMARY_EXPORT_GROUPS
from role_scope_module import restrict_performing_ru_values_for_role, visible_primary_export_groups


PHASE9C_EXCEPTION_UI_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_UI_PHASE9C_V1_20260610"
ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
SESSION_EXCEPTION_MODE_KEY = "export_exception_mode"


def render_export_exception_sidebar_toggle() -> bool:
    return st.sidebar.toggle(
        "⚠️ Export-Ausnahmen öffnen",
        value=bool(st.session_state.get(SESSION_EXCEPTION_MODE_KEY, False)),
        key=SESSION_EXCEPTION_MODE_KEY,
    )


def _group_options(user: UserContext) -> dict[str, dict[str, object]]:
    return visible_primary_export_groups(PRIMARY_EXPORT_GROUPS, user.role_code)


def _blocker_table(blockers) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Regel": blocker.rule_id,
                "Typ": blocker.blocker_type,
                "Lok": blocker.loco_no,
                "PerformingRU": blocker.performing_ru,
                "Von": blocker.period_start_utc,
                "Bis": blocker.period_end_utc,
                "Fehler": blocker.message,
                "Fingerprint": blocker.fingerprint,
            }
            for blocker in blockers
        ]
    )


def _render_active_exceptions(user: UserContext) -> None:
    st.markdown("### Dokumentierte Ausnahmen")
    rows = list_exceptions(active_only=False, db_path=DEFAULT_DB_PATH)
    if not rows:
        st.info("Noch keine fachlichen Export-Ausnahmen dokumentiert.")
        return

    data = pd.DataFrame(rows)
    st.dataframe(data, use_container_width=True, hide_index=True)

    if not user.is_admin:
        return

    active_ids = [str(row["exception_id"]) for row in rows if str(row.get("status", "")) == "ACTIVE"]
    if not active_ids:
        return

    with st.expander("Aktive Ausnahme widerrufen", expanded=False):
        selected = st.selectbox("Ausnahme-ID", active_ids, key="export_exception_revoke_id")
        comment = st.text_area(
            "Begründung für den Widerruf",
            key="export_exception_revoke_comment",
        )
        if st.button("Ausnahme widerrufen", key="export_exception_revoke_button"):
            try:
                revoke_exception(
                    actor=user,
                    exception_id=selected,
                    comment=comment,
                    db_path=DEFAULT_DB_PATH,
                )
            except LocalAuthError as error:
                st.error(str(error))
            else:
                st.success("Ausnahme wurde widerrufen.")
                st.rerun()


def _render_export_releases() -> None:
    st.markdown("### Erzeugte Exportfreigaben")
    rows = list_export_releases(DEFAULT_DB_PATH)
    if not rows:
        st.info("Noch keine XLSX-Freigaben protokolliert.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_export_exception_area(user: UserContext) -> None:
    st.title("⚠️ Export-Ausnahmen")
    st.warning(
        "Blockierende Fehler werden nicht gelöscht oder ausgeblendet. Ein Export ist nur möglich, "
        "wenn für jeden relevanten Root-Fehler eine fachliche Ausnahme mit Begründung dokumentiert wurde."
    )

    if not DUCKDB_PATH.exists():
        st.error(f"DuckDB-Datei fehlt: {DUCKDB_PATH}")
        return

    groups = _group_options(user)
    group_labels = {key: str(config.get("title", key)) for key, config in groups.items()}
    group_labels["REST_MANUELL"] = "Rest / nicht zugeordnetes EVU manuell prüfen"

    selected_group = st.selectbox(
        "Exportgruppe",
        list(group_labels),
        format_func=lambda key: group_labels[key],
        key="export_exception_group",
    )

    if selected_group == "REST_MANUELL":
        manual_ru = st.text_input(
            "PerformingRU für Rest-Export",
            placeholder="Exakte Schreibweise aus der Restkontrolle",
            key="export_exception_manual_ru",
        ).strip()
        performing_ru_values = (manual_ru,) if manual_ru else tuple()
        export_label = manual_ru or "Rest"
    else:
        config = groups[selected_group]
        performing_ru_values = tuple(str(value) for value in config["performing_ru_values"])
        export_label = str(config.get("file_label", selected_group))

    default_day = date.today() - timedelta(days=2)
    col_from, col_to = st.columns(2)
    with col_from:
        date_from = st.date_input("Von-Tag", value=default_day, key="export_exception_date_from")
    with col_to:
        date_to = st.date_input("Bis-Tag", value=default_day, key="export_exception_date_to")

    if date_from > date_to:
        st.error("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")
        return
    if not performing_ru_values:
        st.info("Bitte zuerst eine PerformingRU für den Rest-Export erfassen.")
        _render_active_exceptions(user)
        _render_export_releases()
        return

    try:
        allowed_ru_values = restrict_performing_ru_values_for_role(performing_ru_values, user.role_code)
        blockers = list_required_export_blockers(
            db_path=DUCKDB_PATH,
            performing_ru_values=allowed_ru_values,
            date_from=date_from,
            date_to=date_to,
        )
        status = evaluate_release_status(blockers, DEFAULT_DB_PATH)
    except Exception as error:
        st.error(f"Export-Ausnahmen konnten nicht ermittelt werden: {error}")
        return

    col_total, col_documented, col_missing = st.columns(3)
    col_total.metric("Root-Fehler gesamt", len(status.required_blockers))
    col_documented.metric("Dokumentierte Ausnahmen", len(status.active_exception_ids))
    col_missing.metric("Noch offen", len(status.missing_blockers))

    if not status.required_blockers:
        st.success("Für diese Exportgruppe und diesen Zeitraum bestehen keine blockierenden Root-Fehler.")
    elif status.released:
        st.success(
            "Alle blockierenden Root-Fehler besitzen eine aktive fachliche Ausnahme. "
            "Der XLSX-Download ist auf der normalen Exportseite freigegeben."
        )
    else:
        st.error(
            f"Der Export bleibt gesperrt. Noch {len(status.missing_blockers)} Root-Fehler benötigen eine Begründung."
        )
        st.dataframe(_blocker_table(status.missing_blockers), use_container_width=True, hide_index=True)

        selected_fingerprint = st.selectbox(
            "Root-Fehler dokumentieren",
            [blocker.fingerprint for blocker in status.missing_blockers],
            format_func=lambda fingerprint: next(
                blocker.label() for blocker in status.missing_blockers if blocker.fingerprint == fingerprint
            ),
            key="export_exception_selected_fingerprint",
        )
        selected_blocker = next(
            blocker for blocker in status.missing_blockers if blocker.fingerprint == selected_fingerprint
        )
        st.info(selected_blocker.message or "Keine zusätzliche Fehlerbeschreibung vorhanden.")
        comment = st.text_area(
            "Fachliche Begründung für die Ausnahme",
            placeholder="Warum darf dieser konkrete Root-Fehler für den Export bewusst freigegeben werden?",
            key="export_exception_comment",
        )
        if st.button("Fachliche Ausnahme dokumentieren", key="export_exception_create_button", type="primary"):
            try:
                create_exception(
                    actor=user,
                    blocker=selected_blocker,
                    comment=comment,
                    db_path=DEFAULT_DB_PATH,
                )
            except LocalAuthError as error:
                st.error(str(error))
            else:
                st.success("Fachliche Ausnahme wurde dokumentiert.")
                st.rerun()

    st.caption(f"Prüfung für Exportlabel: {export_label}")
    st.divider()
    _render_active_exceptions(user)
    st.divider()
    _render_export_releases()
