from __future__ import annotations

from pathlib import Path
import runpy
from typing import Any


COMPACT_EXPORT_GRID_MARKER = "NETZENTGELT_EXPORT_COCKPIT_REDESIGN_PHASE14D_V1_20260624"
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

            def _technical_error_hint(label: str, error: Exception) -> None:
                st.info(f"{label}: Hier ist noch etwas offen. Bitte Fall prüfen.")
                with st.expander("Technische Ursache anzeigen", expanded=False):
                    st.code(str(error))

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
                        _technical_error_hint("Nutzung konnte nicht vorbereitet werden", error)
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
                    _technical_error_hint("Aufenthalt konnte nicht vorbereitet werden", error)
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
