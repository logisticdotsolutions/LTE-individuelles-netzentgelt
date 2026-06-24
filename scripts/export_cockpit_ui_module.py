from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from zuordnungen_export_module import (
    LTE_HOLDING_MARKET_PARTNER_IDS,
    LTE_HOLDING_MARKET_PARTNER_NAME,
    build_zuordnungen_holding_xlsx,
)
from zuordnungen_preview_module import (
    build_zuordnungen_holding_preview,
    preview_to_xlsx_bytes,
)


EXPORT_COCKPIT_UI_MARKER = "NETZENTGELT_EXPORT_COCKPIT_UI_PHASE14F_V1_20260624"

RULE_LABELS = {
    "R003": "Ankunft fehlt",
    "R010": "Zeitliche Lücke",
    "R011": "Überschneidung",
    "R012": "Pflichtfeld offen",
}


def _first_existing_column(source_df: pd.DataFrame, candidates: list[str]) -> str | None:
    if source_df.empty:
        return None

    lower_columns = {
        str(column).lower(): column
        for column in source_df.columns
    }

    for candidate in candidates:
        if candidate.lower() in lower_columns:
            return lower_columns[candidate.lower()]

    return None


def _as_clean_text(
    source_df: pd.DataFrame,
    column: str | None,
    default: str = "",
) -> pd.Series:
    if column and column in source_df.columns:
        return (
            source_df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    return pd.Series(default, index=source_df.index, dtype="object")


def _normalize_values(values: tuple[str, ...] | list[str]) -> set[str]:
    return {
        str(value).strip().casefold()
        for value in values
        if str(value).strip()
    }


def _filter_by_export_group(
    source_df: pd.DataFrame,
    group_config: dict,
) -> pd.DataFrame:
    if source_df.empty:
        return source_df

    group_values = _normalize_values(
        tuple(group_config.get("performing_ru_values", ()))
    )
    if not group_values:
        return source_df

    performing_col = _first_existing_column(
        source_df,
        [
            "performing_ru",
            "PerformingRU",
            "performing_ru_value",
            "current_contractant",
            "CurrentContractant",
            "RailwayUndertaking",
        ],
    )

    if not performing_col:
        return source_df

    return source_df[
        source_df[performing_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin(group_values)
    ].copy()


def _friendly_category(rule_value: str, hint_value: str = "") -> str:
    rule = str(rule_value or "").strip().upper()
    hint = str(hint_value or "").strip()
    hint_upper = hint.upper()

    for rule_code, label in RULE_LABELS.items():
        if rule_code in rule:
            return label

    if "ANKUNFT" in hint_upper or "ARRIVAL" in hint_upper:
        return "Ankunft fehlt"
    if "ÜBERSCHNEID" in hint_upper or "OVERLAP" in hint_upper:
        return "Überschneidung"
    if "GAP" in hint_upper or "LÜCK" in hint_upper:
        return "Zeitliche Lücke"
    if "PFLICHT" in hint_upper or "REQUIRED" in hint_upper:
        return "Pflichtfeld offen"
    if "MARKTPARTNER" in hint_upper or "VENS" in hint_upper or "TENS" in hint_upper:
        return "Zuordnung offen"
    if "LOK" in hint_upper or "LOCO" in hint_upper:
        return "Lokdaten prüfen"
    if rule:
        return "Offener Punkt"
    if hint:
        return hint[:80]
    return "Offener Punkt"


def _build_open_case_details(
    *,
    group_config: dict,
    findings: pd.DataFrame,
    export_gate_ru: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
) -> pd.DataFrame:
    detail_frames: list[pd.DataFrame] = []

    sources = [
        (findings, "Prüfregel"),
        (export_gate_ru, "Exportprüfung"),
        (global_export_blockers, "Exportprüfung"),
    ]

    for source_df, source_name in sources:
        if source_df.empty:
            continue

        work = _filter_by_export_group(source_df.copy(), group_config)
        if work.empty:
            continue

        severity_col = _first_existing_column(work, ["severity", "Severity"])
        if severity_col:
            severity_values = (
                work[severity_col]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            relevant_mask = severity_values.isin(["ERROR", "MANUAL_REVIEW"])
            if bool(relevant_mask.any()):
                work = work.loc[relevant_mask].copy()

        status_col = _first_existing_column(
            work,
            ["gate_status", "GateStatus", "status", "Status"],
        )
        if status_col:
            status_values = (
                work[status_col]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            blocked_mask = status_values.isin(["BLOCKED", "ERROR", "MANUAL_REVIEW"])
            if bool(blocked_mask.any()):
                work = work.loc[blocked_mask].copy()

        if work.empty:
            continue

        rule_col = _first_existing_column(work, ["rule_id", "rule", "Rule", "dq_rule_ids"])
        loco_col = _first_existing_column(work, ["loco_no", "LocomotiveNo", "locomotive_no", "Lok"])
        transport_col = _first_existing_column(
            work,
            ["transport_number", "TransportNumber", "transport_no", "TransportNo"],
        )
        start_col = _first_existing_column(
            work,
            ["period_start_utc", "actual_departure_ts", "ActualDeparture", "coverage_date", "blocker_date"],
        )
        end_col = _first_existing_column(
            work,
            ["period_end_utc", "actual_arrival_ts", "ActualArrival"],
        )
        hint_col = _first_existing_column(
            work,
            [
                "dq_messages",
                "message",
                "error_message",
                "gate_message",
                "blocked_reason",
                "reason",
                "decision_reason",
                "Prüfung",
            ],
        )

        technical_rule = _as_clean_text(work, rule_col, "")
        hint = _as_clean_text(work, hint_col, "")
        category = [
            _friendly_category(rule_value, hint_value)
            for rule_value, hint_value in zip(technical_rule, hint)
        ]

        start_values = _as_clean_text(work, start_col, "")
        end_values = _as_clean_text(work, end_col, "")

        detail_df = pd.DataFrame(
            {
                "Kategorie": category,
                "Lok": _as_clean_text(work, loco_col, ""),
                "TransportNumber": _as_clean_text(work, transport_col, ""),
                "Zeitraum": [
                    f"{start} bis {end}" if start and end else start or end
                    for start, end in zip(start_values, end_values)
                ],
                "Hinweis": hint,
                "Quelle": source_name,
            }
        )

        detail_frames.append(detail_df)

    if not detail_frames:
        return pd.DataFrame(
            columns=[
                "Kategorie",
                "Lok",
                "TransportNumber",
                "Zeitraum",
                "Hinweis",
                "Quelle",
            ]
        )

    details = pd.concat(detail_frames, ignore_index=True)
    return details.drop_duplicates().reset_index(drop=True)


def _build_open_case_summary(details: pd.DataFrame) -> pd.DataFrame:
    if details.empty:
        return pd.DataFrame(
            columns=[
                "Kategorie",
                "Anzahl",
                "Betroffene Loks",
                "Betroffene Transporte",
                "Aktion",
            ]
        )

    work = details.copy()
    for column in ["Lok", "TransportNumber", "Kategorie"]:
        work[column] = (
            work[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    summary = (
        work.groupby("Kategorie", as_index=False, dropna=False)
        .agg(
            Anzahl=("Kategorie", "size"),
            **{
                "Betroffene Loks": (
                    "Lok",
                    lambda values: len({
                        value
                        for value in values
                        if str(value).strip()
                    }),
                ),
                "Betroffene Transporte": (
                    "TransportNumber",
                    lambda values: len({
                        value
                        for value in values
                        if str(value).strip()
                    }),
                ),
            },
        )
        .sort_values(by=["Anzahl", "Kategorie"], ascending=[False, True])
    )
    summary["Aktion"] = "Fall prüfen"
    return summary


def _render_open_case_overview(
    *,
    group_config: dict,
    context_label: str,
    findings: pd.DataFrame,
    export_gate_ru: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    technical_error: Exception | None = None,
) -> None:
    details = _build_open_case_details(
        group_config=group_config,
        findings=findings,
        export_gate_ru=export_gate_ru,
        global_export_blockers=global_export_blockers,
    )
    summary = _build_open_case_summary(details)

    st.info(f"{context_label}: Hier ist noch etwas offen. Bitte die Fälle prüfen.")

    if summary.empty:
        st.caption(
            "Für diese Kachel konnte keine eigene Detailtabelle ermittelt werden. "
            "Bitte den Reiter '2. Offene Aufgaben' öffnen."
        )
    else:
        st.dataframe(summary, use_container_width=True, hide_index=True)

        with st.expander("Betroffene Fälle anzeigen", expanded=False):
            st.dataframe(
                details.head(150),
                use_container_width=True,
                hide_index=True,
                height=320,
            )

    if technical_error is not None:
        with st.expander("Technischer Hinweis anzeigen", expanded=False):
            st.code(str(technical_error))


def _render_primary_download_card(
    *,
    group_key: str,
    group_config: dict,
    export_kind: str,
    db_path: Path,
    export_date_from: date,
    export_date_to: date,
    findings: pd.DataFrame,
    export_gate_ru: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    build_nutzungsmeldung_download_cached: Callable,
    build_aufenthaltsereignis_download_cached: Callable,
) -> None:
    if export_kind == "nutzung":
        try:
            result = build_nutzungsmeldung_download_cached(
                db_path_text=str(db_path),
                db_mtime_ns=db_path.stat().st_mtime_ns,
                performing_ru_values=tuple(group_config["performing_ru_values"]),
                export_label=group_config["file_label"],
                date_from_iso=export_date_from.isoformat(),
                date_to_iso=export_date_to.isoformat(),
            )
        except Exception as error:
            _render_open_case_overview(
                group_config=group_config,
                context_label="Nutzung konnte noch nicht vorbereitet werden",
                findings=findings,
                export_gate_ru=export_gate_ru,
                global_export_blockers=global_export_blockers,
                technical_error=error,
            )
            return

        st.metric("Zeilen", result.row_count)
        if result.missing_required_mapping_count > 0:
            st.info(
                "Hier ist noch etwas offen: "
                f"{result.missing_required_mapping_count} Zeilen brauchen noch eine Zuordnung. "
                "Bitte Fall prüfen."
            )

        st.download_button(
            label="Nutzung XLSX",
            data=result.content,
            file_name=result.file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_export_redesign_nutzung_{group_key.lower()}",
            use_container_width=True,
        )
        return

    try:
        result = build_aufenthaltsereignis_download_cached(
            db_path_text=str(db_path),
            db_mtime_ns=db_path.stat().st_mtime_ns,
            performing_ru_values=tuple(group_config["performing_ru_values"]),
            export_label=group_config["file_label"],
            date_from_iso=export_date_from.isoformat(),
            date_to_iso=export_date_to.isoformat(),
        )
    except Exception as error:
        _render_open_case_overview(
            group_config=group_config,
            context_label="Aufenthalt konnte noch nicht vorbereitet werden",
            findings=findings,
            export_gate_ru=export_gate_ru,
            global_export_blockers=global_export_blockers,
            technical_error=error,
        )
        return

    st.metric("Zeilen", result.row_count)
    if result.missing_required_field_count > 0:
        st.info(
            "Hier ist noch etwas offen: "
            f"{result.missing_required_field_count} Zeilen haben noch fehlende Pflichtfelder. "
            "Bitte Fall prüfen."
        )

    st.download_button(
        label="Aufenthalt XLSX",
        data=result.content,
        file_name=result.file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"download_export_redesign_aufenthalt_{group_key.lower()}",
        use_container_width=True,
    )


def _disable_legacy_holding_extension() -> None:
    try:
        import zuordnungen_ui_runtime_bridge as bridge
    except Exception:
        return

    if not hasattr(bridge, "_original_render_zuordnungen_export_extension"):
        bridge._original_render_zuordnungen_export_extension = (  # type: ignore[attr-defined]
            bridge.render_zuordnungen_export_extension
        )

    bridge.render_zuordnungen_export_extension = lambda: None


@st.cache_data(show_spinner=False)
def _build_holding_download_cached(
    db_path_text: str,
    db_mtime_ns: int,
    holding_market_partner_id: str,
    date_from_iso: str,
    date_to_iso: str,
):
    _ = db_mtime_ns
    return build_zuordnungen_holding_xlsx(
        db_path=Path(db_path_text),
        holding_market_partner_id=holding_market_partner_id,
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


@st.cache_data(show_spinner=False)
def _build_holding_preview_cached(
    db_path_text: str,
    db_mtime_ns: int,
    date_from_iso: str,
    date_to_iso: str,
):
    _ = db_mtime_ns
    return build_zuordnungen_holding_preview(
        db_path=Path(db_path_text),
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


def _render_holding_assignment_section(
    *,
    db_path: Path,
    export_date_from: date,
    export_date_to: date,
) -> None:
    st.divider()
    st.markdown("### Zuordnungen LTE Holding / LTE-Gesellschaften mit DE-Bezug")
    st.caption(
        "Hier werden Loks betrachtet, bei denen LTE Holding, LTE Germany oder ein anderes "
        "LTE-Unternehmen mit DE-Bezug als Holder gepflegt ist."
    )

    if not db_path.exists():
        st.info("Noch keine berechneten Daten gefunden. Bitte zuerst die Tagesprüfung ausführen.")
        return

    with st.expander("Vorschau anzeigen", expanded=False):
        try:
            preview_df = _build_holding_preview_cached(
                db_path_text=str(db_path),
                db_mtime_ns=db_path.stat().st_mtime_ns,
                date_from_iso=export_date_from.isoformat(),
                date_to_iso=export_date_to.isoformat(),
            )
        except Exception as error:
            st.info("Vorschau konnte noch nicht vorbereitet werden. Bitte Fall prüfen.")
            with st.expander("Technischer Hinweis anzeigen", expanded=False):
                st.code(str(error))
            preview_df = pd.DataFrame()

        if not preview_df.empty:
            status_col = _first_existing_column(preview_df, ["Exportstatus", "status", "Status"])
            if status_col:
                blocked_count = int(
                    preview_df[status_col]
                    .fillna("")
                    .astype(str)
                    .str.upper()
                    .eq("BLOCKIERT")
                    .sum()
                )
                exportable_count = int(
                    preview_df[status_col]
                    .fillna("")
                    .astype(str)
                    .str.upper()
                    .eq("EXPORTFÄHIG")
                    .sum()
                )
            else:
                blocked_count = 0
                exportable_count = len(preview_df)

            metric_all, metric_ready, metric_open = st.columns(3)
            with metric_all:
                st.metric("Vorschauzeilen", len(preview_df))
            with metric_ready:
                st.metric("Exportfähig", exportable_count)
            with metric_open:
                st.metric("Noch offen", blocked_count)

            if blocked_count > 0:
                st.info(f"Hier ist noch etwas offen: {blocked_count} Zeilen bitte prüfen.")

            st.dataframe(
                preview_df,
                use_container_width=True,
                hide_index=True,
                height=360,
            )
            st.download_button(
                label="Vorschau XLSX",
                data=preview_to_xlsx_bytes(preview_df),
                file_name=(
                    "Vorschau_Zuordnungen_LTE_Holding_"
                    f"{export_date_from.isoformat()}_bis_{export_date_to.isoformat()}.xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_zuordnungen_holding_preview_redesign",
                use_container_width=True,
            )
        elif preview_df.empty:
            st.info("Für den gewählten Zeitraum wurden keine DE-relevanten Zuordnungssegmente gefunden.")

    st.markdown("#### Downloads")
    holding_columns = st.columns(len(LTE_HOLDING_MARKET_PARTNER_IDS), gap="large")
    for holding_column, holding_market_partner_id in zip(
        holding_columns,
        LTE_HOLDING_MARKET_PARTNER_IDS,
    ):
        with holding_column:
            st.markdown(f"**{holding_market_partner_id}**")
            try:
                result = _build_holding_download_cached(
                    db_path_text=str(db_path),
                    db_mtime_ns=db_path.stat().st_mtime_ns,
                    holding_market_partner_id=holding_market_partner_id,
                    date_from_iso=export_date_from.isoformat(),
                    date_to_iso=export_date_to.isoformat(),
                )
            except Exception as error:
                st.info("Zuordnungen konnten noch nicht vorbereitet werden. Bitte Fall prüfen.")
                with st.expander("Technischer Hinweis anzeigen", expanded=False):
                    st.code(str(error))
                continue

            st.metric("Zeilen", result.row_count)
            if result.missing_required_field_count > 0:
                st.info(
                    "Hier ist noch etwas offen: "
                    f"{result.missing_required_field_count} Zeilen haben noch fehlende Pflichtfelder. "
                    "Bitte Fall prüfen."
                )

            st.download_button(
                label="Zuordnungen XLSX",
                data=result.content,
                file_name=result.file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_zuordnungen_holding_redesign_{holding_market_partner_id}",
                use_container_width=True,
            )


def render_export_cockpit(
    *,
    db_path: Path,
    export_dir: Path,
    operational_day_from: date,
    operational_day_to: date,
    findings: pd.DataFrame,
    export_gate_ru: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    zuordnungen: pd.DataFrame,
    nutzungsmeldung: pd.DataFrame,
    primary_export_groups: dict,
    list_rest_export_overview: Callable,
    build_nutzungsmeldung_download_cached: Callable,
    build_aufenthaltsereignis_download_cached: Callable,
    render_nutzungsmeldung_export_section: Callable,
    render_aufenthaltsereignis_export_section: Callable,
) -> None:
    _disable_legacy_holding_extension()

    st.subheader("Exporte")
    st.caption(
        "Fachliche Downloads stehen oben. Kontrolllisten und technische Vorschauen sind "
        "eingeklappt, damit der Bereich nicht wie eine Fehlerseite wirkt."
    )

    if not db_path.exists():
        st.info(
            "Es liegen noch keine berechneten Exportdaten vor. Bitte zuerst die Tagesprüfung "
            "ausführen oder die Daten neu berechnen."
        )
        return

    today = datetime.now().date()
    first_allowed_day = today - timedelta(days=29)
    export_min_day = min(first_allowed_day, operational_day_from)
    export_max_day = max(today, operational_day_to)

    with st.expander("Zeitraum anpassen", expanded=False):
        date_col_1, date_col_2 = st.columns(2)
        with date_col_1:
            export_date_from = st.date_input(
                "Von",
                value=operational_day_from,
                min_value=export_min_day,
                max_value=export_max_day,
                key="nutzungsmeldung_export_date_from",
            )
        with date_col_2:
            export_date_to = st.date_input(
                "Bis",
                value=operational_day_to,
                min_value=export_min_day,
                max_value=export_max_day,
                key="nutzungsmeldung_export_date_to",
            )

    if export_date_from > export_date_to:
        st.info("Der Zeitraum ist noch nicht gültig: Bitte Von- und Bis-Datum prüfen.")
        return

    if export_date_from != operational_day_from or export_date_to != operational_day_to:
        st.info(
            "Der Exportzeitraum weicht vom aktuell geprüften Arbeitszeitraum ab. "
            "Bitte vor dem Download kurz prüfen."
        )

    st.markdown("### LTE Arbeitsdateien")
    st.caption("Je EVU stehen Nutzung und Aufenthalt direkt untereinander.")

    primary_items = list(primary_export_groups.items())
    if primary_items:
        primary_columns = st.columns(len(primary_items), gap="large")
        for primary_column, (group_key, group_config) in zip(primary_columns, primary_items):
            with primary_column:
                st.markdown(f"#### {group_config['title']}")
                st.markdown("**Nutzung**")
                _render_primary_download_card(
                    group_key=group_key,
                    group_config=group_config,
                    export_kind="nutzung",
                    db_path=db_path,
                    export_date_from=export_date_from,
                    export_date_to=export_date_to,
                    findings=findings,
                    export_gate_ru=export_gate_ru,
                    global_export_blockers=global_export_blockers,
                    build_nutzungsmeldung_download_cached=build_nutzungsmeldung_download_cached,
                    build_aufenthaltsereignis_download_cached=build_aufenthaltsereignis_download_cached,
                )
                st.markdown("---")
                st.markdown("**Aufenthalt**")
                _render_primary_download_card(
                    group_key=group_key,
                    group_config=group_config,
                    export_kind="aufenthalt",
                    db_path=db_path,
                    export_date_from=export_date_from,
                    export_date_to=export_date_to,
                    findings=findings,
                    export_gate_ru=export_gate_ru,
                    global_export_blockers=global_export_blockers,
                    build_nutzungsmeldung_download_cached=build_nutzungsmeldung_download_cached,
                    build_aufenthaltsereignis_download_cached=build_aufenthaltsereignis_download_cached,
                )
    else:
        st.info("Keine LTE Exportgruppen konfiguriert.")

    st.divider()
    st.markdown("### Restliche EVUs")
    st.caption("Alle weiteren nutzenden EVUs außerhalb LTE DE und LTE NL.")

    with st.expander("Restliche EVUs anzeigen", expanded=False):
        rest_rows = list_rest_export_overview(
            db_path=db_path,
            date_from=export_date_from,
            date_to=export_date_to,
        )
        rest_df = pd.DataFrame(rest_rows)

        if rest_df.empty:
            st.success("Keine restlichen EVUs im gewählten Zeitraum vorhanden.")
        else:
            rest_total = int(rest_df["Betroffene Bewegungszeilen"].sum())
            rest_blocked = int(rest_df["Davon gesperrt"].sum())
            rest_ru_count = int(rest_df["PerformingRU"].nunique())

            metric_rest_1, metric_rest_2, metric_rest_3 = st.columns(3)
            with metric_rest_1:
                st.metric("Weitere Zeilen", rest_total)
            with metric_rest_2:
                st.metric("Weitere EVU", rest_ru_count)
            with metric_rest_3:
                st.metric("Noch offen", rest_blocked)

            if rest_blocked > 0:
                st.info(f"Hier ist noch etwas offen: {rest_blocked} Rest-Zeilen sind noch nicht freigegeben. Bitte Fall prüfen.")

            rest_summary = (
                rest_df
                .groupby("PerformingRU", as_index=False, dropna=False)
                .agg({
                    "Betroffene Bewegungszeilen": "sum",
                    "Davon exportfähig": "sum",
                    "Davon gesperrt": "sum",
                    "Betroffene Loks": "sum",
                    "Betroffene Transporte": "sum",
                })
                .sort_values(
                    by=["Betroffene Bewegungszeilen", "PerformingRU"],
                    ascending=[False, True],
                )
            )

            st.dataframe(rest_summary, use_container_width=True, hide_index=True)

            selected_rest_ru = st.selectbox(
                "EVU auswählen",
                rest_summary["PerformingRU"].astype(str).tolist(),
                key="rest_export_selected_performing_ru",
            )

            rest_col_1, rest_col_2 = st.columns(2, gap="large")
            with rest_col_1:
                st.markdown("**Nutzung**")
                render_nutzungsmeldung_export_section(
                    title="",
                    export_label=f"REST_{selected_rest_ru}",
                    performing_ru_values=(selected_rest_ru,),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix="rest_nutzung",
                )
            with rest_col_2:
                st.markdown("**Aufenthalt**")
                render_aufenthaltsereignis_export_section(
                    title="",
                    export_label=f"REST_{selected_rest_ru}",
                    performing_ru_values=(selected_rest_ru,),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix="rest_aufenthalt",
                )

            with st.expander("Restdetails / OrderOwner", expanded=False):
                if (
                    "OrderOwner" not in rest_df.columns
                    or rest_df["OrderOwner"].fillna("").eq("Nicht verfügbar").all()
                ):
                    st.info("OrderOwner ist in den aktuellen Daten nicht verfügbar.")
                st.dataframe(rest_df, use_container_width=True, hide_index=True)

                rest_csv = rest_df.to_csv(index=False, sep=";").encode("utf-8-sig")
                st.download_button(
                    "Restübersicht CSV",
                    data=rest_csv,
                    file_name="rest_export_uebersicht.csv",
                    mime="text/csv",
                    key="download_rest_export_overview",
                    use_container_width=True,
                )

    _render_holding_assignment_section(
        db_path=db_path,
        export_date_from=export_date_from,
        export_date_to=export_date_to,
    )

    st.divider()
    with st.expander("Kontrolllisten und technische Dateien", expanded=False):
        export_files = sorted(export_dir.glob("*.*"))
        if not export_files:
            st.info("Keine technischen Exportdateien gefunden.")
        else:
            st.caption("Nur für Kontrolle, Audit und Fehleranalyse.")
            for file in export_files:
                size_kb = file.stat().st_size / 1024
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(f"**{file.name}**  \n{size_kb:.1f} KB")
                with col2:
                    with open(file, "rb") as export_file:
                        st.download_button(
                            label="Download",
                            data=export_file,
                            file_name=file.name,
                            key=f"download_{file.name}",
                            use_container_width=True,
                        )

    with st.expander("Interne Vorschauen", expanded=False):
        st.markdown("#### Zuordnungen")
        if not zuordnungen.empty:
            st.dataframe(
                zuordnungen.head(100),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Keine export_zuordnungen.csv vorhanden.")

        st.markdown("#### Nutzungsmeldung")
        if not nutzungsmeldung.empty:
            st.dataframe(
                nutzungsmeldung.head(100),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Keine export_nutzungsmeldung.csv vorhanden.")
