from __future__ import annotations

from pathlib import Path
import runpy
from typing import Any


COMPACT_EXPORT_GRID_MARKER = "NETZENTGELT_EXPORT_COCKPIT_REDESIGN_PHASE14E_V1_20260624"
_LEGACY_EXPORT_MARKER = "\nwith tab_exports:\n"
_NEXT_TAB_MARKER = "\nwith tab_run:\n"

_REDESIGNED_EXPORT_BLOCK = '''
with tab_exports:
    # __COMPACT_EXPORT_GRID_MARKER__
    st.subheader("Exporte")
    st.caption(
        "Fachliche Downloads stehen oben. Kontrolllisten und technische Vorschauen sind "
        "eingeklappt, damit der Bereich nicht wie eine Fehlerseite wirkt."
    )

    if not DB_PATH.exists():
        st.info(
            "Es liegen noch keine berechneten Exportdaten vor. Bitte zuerst die Tagesprüfung "
            "ausführen oder die Daten neu berechnen."
        )

    else:
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

        else:
            if (
                export_date_from != operational_day_from
                or export_date_to != operational_day_to
            ):
                st.info(
                    "Der Exportzeitraum weicht vom aktuell geprüften Arbeitszeitraum ab. "
                    "Bitte vor dem Download kurz prüfen."
                )

            def _soft_open_case_message(detail: str) -> None:
                st.info(f"Hier ist noch etwas offen: {detail} Bitte Fall prüfen.")

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

            def _as_clean_text(source_df: pd.DataFrame, column: str | None, default: str = "") -> pd.Series:
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

                if rule.startswith("R011") or "ÜBERSCHNEID" in hint_upper or "OVERLAP" in hint_upper:
                    return "Überschneidung"
                if rule.startswith("R010") or "GAP" in hint_upper or "LÜCK" in hint_upper:
                    return "Zeitliche Lücke"
                if rule.startswith("R012") or "PFLICHT" in hint_upper or "REQUIRED" in hint_upper:
                    return "Pflichtfeld offen"
                if rule.startswith("R001") or "LOK" in hint_upper or "LOCO" in hint_upper:
                    return "Lokdaten prüfen"
                if "MARKTPARTNER" in hint_upper or "VENS" in hint_upper or "TENS" in hint_upper:
                    return "Zuordnung offen"
                if rule:
                    return f"Regel {rule}"
                if hint:
                    return hint[:80]
                return "Offener Punkt"

            def _build_open_case_details(group_config: dict) -> pd.DataFrame:
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

                    status_col = _first_existing_column(work, ["gate_status", "GateStatus", "status", "Status"])
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

                    detail_df = pd.DataFrame(index=work.index)
                    detail_df["Quelle"] = source_name
                    detail_df["Regel"] = _as_clean_text(work, rule_col, "")
                    detail_df["Hinweis"] = _as_clean_text(work, hint_col, "")
                    detail_df["Kategorie"] = [
                        _friendly_category(rule_value, hint_value)
                        for rule_value, hint_value in zip(detail_df["Regel"], detail_df["Hinweis"])
                    ]
                    detail_df["Lok"] = _as_clean_text(work, loco_col, "")
                    detail_df["TransportNumber"] = _as_clean_text(work, transport_col, "")

                    start_values = _as_clean_text(work, start_col, "")
                    end_values = _as_clean_text(work, end_col, "")
                    detail_df["Zeitraum"] = [
                        f"{start} bis {end}" if start and end else start or end
                        for start, end in zip(start_values, end_values)
                    ]

                    detail_frames.append(
                        detail_df[
                            [
                                "Kategorie",
                                "Lok",
                                "TransportNumber",
                                "Regel",
                                "Zeitraum",
                                "Hinweis",
                                "Quelle",
                            ]
                        ]
                    )

                if not detail_frames:
                    return pd.DataFrame(
                        columns=[
                            "Kategorie",
                            "Lok",
                            "TransportNumber",
                            "Regel",
                            "Zeitraum",
                            "Hinweis",
                            "Quelle",
                        ]
                    )

                details = pd.concat(detail_frames, ignore_index=True)
                details = details.drop_duplicates().reset_index(drop=True)
                return details

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
                technical_error: Exception | None = None,
            ) -> None:
                details = _build_open_case_details(group_config)
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
            ) -> None:
                if export_kind == "nutzung":
                    try:
                        result = build_nutzungsmeldung_download_cached(
                            db_path_text=str(DB_PATH),
                            db_mtime_ns=DB_PATH.stat().st_mtime_ns,
                            performing_ru_values=tuple(group_config["performing_ru_values"]),
                            export_label=group_config["file_label"],
                            date_from_iso=export_date_from.isoformat(),
                            date_to_iso=export_date_to.isoformat(),
                        )
                    except Exception as error:
                        _render_open_case_overview(
                            group_config=group_config,
                            context_label="Nutzung konnte noch nicht vorbereitet werden",
                            technical_error=error,
                        )
                        return

                    st.metric("Zeilen", result.row_count)
                    if result.missing_required_mapping_count > 0:
                        _soft_open_case_message(
                            f"{result.missing_required_mapping_count} Zeilen brauchen noch eine Zuordnung."
                        )

                    st.download_button(
                        label="Nutzung XLSX",
                        data=result.content,
                        file_name=result.file_name,
                        mime=(
                            "application/vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                        key=f"download_export_redesign_nutzung_{group_key.lower()}",
                        use_container_width=True,
                    )
                    return

                try:
                    result = build_aufenthaltsereignis_download_cached(
                        db_path_text=str(DB_PATH),
                        db_mtime_ns=DB_PATH.stat().st_mtime_ns,
                        performing_ru_values=tuple(group_config["performing_ru_values"]),
                        export_label=group_config["file_label"],
                        date_from_iso=export_date_from.isoformat(),
                        date_to_iso=export_date_to.isoformat(),
                    )
                except Exception as error:
                    _render_open_case_overview(
                        group_config=group_config,
                        context_label="Aufenthalt konnte noch nicht vorbereitet werden",
                        technical_error=error,
                    )
                    return

                st.metric("Zeilen", result.row_count)
                if result.missing_required_field_count > 0:
                    _soft_open_case_message(
                        f"{result.missing_required_field_count} Zeilen haben noch fehlende Pflichtfelder."
                    )

                st.download_button(
                    label="Aufenthalt XLSX",
                    data=result.content,
                    file_name=result.file_name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key=f"download_export_redesign_aufenthalt_{group_key.lower()}",
                    use_container_width=True,
                )

            primary_export_groups = list(PRIMARY_EXPORT_GROUPS.items())
            st.markdown("### LTE Arbeitsdateien")
            st.caption("Je EVU stehen Nutzung und Aufenthalt direkt untereinander.")

            if primary_export_groups:
                primary_columns = st.columns(len(primary_export_groups), gap="large")

                for primary_column, (group_key, group_config) in zip(
                    primary_columns,
                    primary_export_groups,
                ):
                    with primary_column:
                        st.markdown(f"#### {group_config['title']}")
                        with st.container():
                            st.markdown("**Nutzung**")
                            _render_primary_download_card(
                                group_key=group_key,
                                group_config=group_config,
                                export_kind="nutzung",
                            )
                        st.markdown("---")
                        with st.container():
                            st.markdown("**Aufenthalt**")
                            _render_primary_download_card(
                                group_key=group_key,
                                group_config=group_config,
                                export_kind="aufenthalt",
                            )
            else:
                st.info("Keine LTE Exportgruppen konfiguriert.")

            with st.expander("Weitere EVU / Rest", expanded=False):
                st.caption(
                    "Rest umfasst nutzende EVU außerhalb LTE DE und LTE NL. "
                    "Ein Download wird je EVU erzeugt, damit die Kopfdaten eindeutig bleiben."
                )

                rest_rows = list_rest_export_overview(
                    db_path=DB_PATH,
                    date_from=export_date_from,
                    date_to=export_date_to,
                )
                rest_df = pd.DataFrame(rest_rows)

                if rest_df.empty:
                    st.success("Keine weiteren EVU im gewählten Zeitraum vorhanden.")
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
                        _soft_open_case_message(f"{rest_blocked} Rest-Zeilen sind noch nicht freigegeben.")

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

    with st.expander("Kontrolllisten und technische Dateien", expanded=False):
        export_files = sorted(EXPORT_DIR.glob("*.*"))

        if not export_files:
            st.info("Keine technischen Exportdateien gefunden.")
        else:
            st.caption("Nur für Kontrolle, Audit und Fehleranalyse.")
            for file in export_files:
                size_kb = file.stat().st_size / 1024
                col1, col2 = st.columns([4, 1])

                with col1:
                    st.write(f"**{file.name}**  \\n{size_kb:.1f} KB")

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
'''.replace("__COMPACT_EXPORT_GRID_MARKER__", COMPACT_EXPORT_GRID_MARKER)


def patch_export_grid_source(source: str) -> str:
    """Replace the full legacy export tab with a compact working cockpit."""
    if COMPACT_EXPORT_GRID_MARKER in source:
        return source

    export_start = source.find(_LEGACY_EXPORT_MARKER)
    next_tab_start = source.find(_NEXT_TAB_MARKER)

    if export_start == -1 or next_tab_start == -1 or next_tab_start <= export_start:
        return source

    return source[: export_start + 1] + _REDESIGNED_EXPORT_BLOCK + source[next_tab_start:]


def install_compact_export_grid_runtime(legacy_app_path: Path):
    """Patch runpy.run_path so app.py is executed with the redesigned export cockpit."""
    original_run_path = runpy.run_path
    legacy_app_path = legacy_app_path.resolve()

    if getattr(original_run_path, "_compact_export_grid_installed", False):
        return original_run_path

    def patched_run_path(
        path_name: str | bytes | Path,
        init_globals: dict[str, Any] | None = None,
        run_name: str | None = None,
    ):
        candidate_path = Path(path_name).resolve()

        if candidate_path != legacy_app_path:
            return original_run_path(
                path_name,
                init_globals=init_globals,
                run_name=run_name,
            )

        source = candidate_path.read_text(encoding="utf-8-sig")
        patched_source = patch_export_grid_source(source)

        if patched_source == source:
            return original_run_path(
                path_name,
                init_globals=init_globals,
                run_name=run_name,
            )

        globals_for_run: dict[str, Any] = {
            "__name__": run_name or "<run_path>",
            "__file__": str(candidate_path),
            "__cached__": None,
            "__loader__": None,
            "__package__": "",
            "__spec__": None,
        }

        if init_globals:
            globals_for_run.update(init_globals)

        compiled = compile(
            patched_source,
            str(candidate_path),
            "exec",
        )
        exec(compiled, globals_for_run)
        return globals_for_run

    patched_run_path._compact_export_grid_installed = True
    runpy.run_path = patched_run_path
    return original_run_path


def restore_compact_export_grid_runtime(original_run_path) -> None:
    """Restore runpy.run_path after the Streamlit app was executed."""
    runpy.run_path = original_run_path
