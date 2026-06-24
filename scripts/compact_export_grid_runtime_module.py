from __future__ import annotations

from pathlib import Path
import runpy
from typing import Any


COMPACT_EXPORT_GRID_MARKER = "NETZENTGELT_EXPORT_COCKPIT_REDESIGN_PHASE14F_V1_20260624"
_LEGACY_EXPORT_MARKER = "\nwith tab_exports:\n"
_NEXT_TAB_MARKER = "\nwith tab_run:\n"

_REDESIGNED_EXPORT_BLOCK = '''
with tab_exports:
    # __COMPACT_EXPORT_GRID_MARKER__
    from export_cockpit_ui_module import render_export_cockpit

    render_export_cockpit(
        db_path=DB_PATH,
        export_dir=EXPORT_DIR,
        operational_day_from=operational_day_from,
        operational_day_to=operational_day_to,
        findings=findings,
        export_gate_ru=export_gate_ru,
        global_export_blockers=global_export_blockers,
        zuordnungen=zuordnungen,
        nutzungsmeldung=nutzungsmeldung,
        primary_export_groups=PRIMARY_EXPORT_GROUPS,
        list_rest_export_overview=list_rest_export_overview,
        build_nutzungsmeldung_download_cached=build_nutzungsmeldung_download_cached,
        build_aufenthaltsereignis_download_cached=build_aufenthaltsereignis_download_cached,
        render_nutzungsmeldung_export_section=render_nutzungsmeldung_export_section,
        render_aufenthaltsereignis_export_section=render_aufenthaltsereignis_export_section,
    )
'''.replace("__COMPACT_EXPORT_GRID_MARKER__", COMPACT_EXPORT_GRID_MARKER)


def patch_export_grid_source(source: str) -> str:
    """Replace the full legacy export tab with the dedicated export cockpit UI."""
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

        runtime_path = candidate_path.with_name("_app_export_cockpit_runtime.py")
        runtime_path.write_text(patched_source, encoding="utf-8")
        return original_run_path(
            str(runtime_path),
            init_globals=init_globals,
            run_name=run_name,
        )

    patched_run_path._compact_export_grid_installed = True
    runpy.run_path = patched_run_path
    return original_run_path


def restore_compact_export_grid_runtime(original_run_path) -> None:
    """Restore runpy.run_path after the Streamlit app was executed."""
    runpy.run_path = original_run_path
