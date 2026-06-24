from __future__ import annotations

from pathlib import Path
import runpy
from typing import Any


COMPACT_EXPORT_GRID_MARKER = "NETZENTGELT_COMPACT_EXPORT_GRID_PHASE14C_V1_20260624"

_PRIMARY_EXPORT_LOOP_BLOCK = '''            for group_key, group_config in PRIMARY_EXPORT_GROUPS.items():
                st.divider()
                st.markdown(f"### {group_config['title']}")

                render_nutzungsmeldung_export_section(
                    title="Nutzungsmeldung",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_nutzung_{group_key.lower()}",
                )

                render_aufenthaltsereignis_export_section(
                    title="Aufenthaltsereignisse",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_aufenthalt_{group_key.lower()}",
                )
'''

_COMPACT_EXPORT_GRID_BLOCK = '''            # {marker}
            primary_export_groups = list(PRIMARY_EXPORT_GROUPS.items())

            def _render_compact_primary_nutzungsmeldung(
                *,
                group_key: str,
                group_config: dict,
            ) -> None:
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
                    st.error(f"Nutzungsmeldung konnte nicht erzeugt werden: {error}")
                    return

                st.caption(f"{result.row_count} Zeilen")
                if result.missing_required_mapping_count > 0:
                    st.warning(
                        f"{result.missing_required_mapping_count} Zeilen mit unvollständiger "
                        "ANU_VENS-/ANE_TENS-Zuordnung."
                    )

                st.download_button(
                    label="Nutzung herunterladen",
                    data=result.content,
                    file_name=result.file_name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key=f"download_compact_nutzung_{group_key.lower()}",
                    use_container_width=True,
                )

            def _render_compact_primary_aufenthalt(
                *,
                group_key: str,
                group_config: dict,
            ) -> None:
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
                    st.error(f"Aufenthalt konnte nicht erzeugt werden: {error}")
                    return

                st.caption(f"{result.row_count} Zeilen")
                if result.missing_required_field_count > 0:
                    st.warning(
                        f"{result.missing_required_field_count} Zeilen mit leerem Pflichtfeld."
                    )

                st.download_button(
                    label="Aufenthalt herunterladen",
                    data=result.content,
                    file_name=result.file_name,
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key=f"download_compact_aufenthalt_{group_key.lower()}",
                    use_container_width=True,
                )

            if primary_export_groups:
                st.caption(
                    "Kompakte Arbeitsansicht: LTE DE und LTE NL stehen nebeneinander; "
                    "Nutzung und Aufenthalt liegen direkt unter dem jeweiligen EVU."
                )
                primary_columns = st.columns(len(primary_export_groups), gap="large")

                for primary_column, (group_key, group_config) in zip(
                    primary_columns,
                    primary_export_groups,
                ):
                    with primary_column:
                        st.markdown(f"### {group_config['title']}")
                        st.markdown("#### Nutzung")
                        _render_compact_primary_nutzungsmeldung(
                            group_key=group_key,
                            group_config=group_config,
                        )
                        st.markdown("#### Aufenthalt")
                        _render_compact_primary_aufenthalt(
                            group_key=group_key,
                            group_config=group_config,
                        )
            else:
                st.info("Keine primären Exportgruppen konfiguriert.")
'''.format(marker=COMPACT_EXPORT_GRID_MARKER)


def patch_export_grid_source(source: str) -> str:
    """Replace the verbose primary export loop with a compact 2-column UX grid."""
    if COMPACT_EXPORT_GRID_MARKER in source:
        return source

    if _PRIMARY_EXPORT_LOOP_BLOCK not in source:
        return source

    return source.replace(_PRIMARY_EXPORT_LOOP_BLOCK, _COMPACT_EXPORT_GRID_BLOCK, 1)


def install_compact_export_grid_runtime(legacy_app_path: Path):
    """Patch runpy.run_path so app.py is executed with the compact export grid."""
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
