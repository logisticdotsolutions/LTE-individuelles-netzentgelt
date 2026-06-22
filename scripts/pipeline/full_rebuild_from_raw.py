"""Full-Rebuild aus einer vorhandenen Raw-DuckDB."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from time import perf_counter

import duckdb

from .context import PipelineContext
from .csv_outputs import export_all_csv_outputs
from .quality_gate_incremental import apply_r016_to_quality_gate_tables


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)

    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _write_timing_log(ctx: PipelineContext, timings: list[dict[str, object]]) -> None:
    ctx.ensure_directories()
    timing_path = ctx.log_dir / f"{ctx.run_id}_pipeline_timing.json"
    timing_path.write_text(
        json.dumps(
            {
                "run_id": ctx.run_id,
                "timings": timings,
                "total_seconds": round(sum(float(item["seconds"]) for item in timings), 3),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Pipeline-Timing-Log: {timing_path}")


def run_full_rebuild_from_raw(
    ctx: PipelineContext,
    *,
    write_csv_outputs: bool = True,
) -> str:
    """Fachliche Datenbank aus bestehender Raw-DuckDB neu erzeugen."""
    ctx.ensure_directories()

    if not ctx.raw_db_path.exists():
        raise FileNotFoundError(
            f"Raw-DuckDB nicht gefunden: {ctx.raw_db_path}. "
            "Bitte zuerst RAW_IMPORT_REBUILD ausfuehren."
        )

    _ensure_scripts_dir_on_path()

    from dummy_locomotive_module import (
        build_dummy_locomotive_catalog,
        consolidate_dummy_locomotive_findings,
        exclude_dummy_locomotives_from_staging,
    )
    from error_rules import build_findings
    from export_module import build_export_tables
    from manual_override_module import (
        apply_raw_manual_overrides,
        apply_staging_manual_overrides,
        import_manual_overrides,
    )
    from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table
    from rule_engine_hardening_phase6b import (
        apply_core_assignment_fallbacks,
        harden_findings_and_export_policy,
    )
    from rule_engine_hardening_phase6c import (
        harden_findings_and_segments_phase6c,
        prepare_timeline_context_phase6c,
    )
    from rule_engine_hardening_phase6d import (
        finalize_quality_gate_phase6d,
        insert_gap_only_day_findings_phase6d,
    )
    from run_all import (
        build_cancelled_transport_exclusions,
        build_core,
        build_loco_events,
        build_transport_routes,
        build_unresolved_performing_ru_market_partner_alias,
        import_mapping,
        import_market_partner_mapping,
        import_market_partner_reference,
        import_vens_tens_exception,
    )

    timings: list[dict[str, object]] = []

    def timed(label: str, func):
        started = perf_counter()
        result = func()
        seconds = round(perf_counter() - started, 3)
        timings.append({"step": label, "seconds": seconds})
        print(f"TIMING {label}: {seconds:.3f}s")
        return result

    def timed_if_missing(label: str, table_name: str, func):
        if _table_exists(con, table_name):
            timings.append({"step": label, "seconds": 0.0, "skipped": True})
            print(f"TIMING {label}: 0.000s skipped")
            return None
        return timed(label, func)

    _remove_if_exists(ctx.db_build_path)
    _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

    print(f"Kopiere Raw-DuckDB in Build-Datenbank: {ctx.db_build_path}")
    timed("copy_raw_to_build", lambda: shutil.copy2(ctx.raw_db_path, ctx.db_build_path))

    con = None

    try:
        con = duckdb.connect(str(ctx.db_build_path))

        print("Berechne Exclusions, Referenzen und manuelle Overrides...")
        timed_if_missing(
            "build_cancelled_transport_exclusions",
            "audit_excluded_cancelled_transports",
            lambda: build_cancelled_transport_exclusions(con),
        )
        timed_if_missing(
            "build_dummy_locomotive_catalog",
            "cfg_dummy_locomotives_effective",
            lambda: build_dummy_locomotive_catalog(con),
        )
        timed_if_missing("import_mapping", "cfg_loco_mapping", lambda: import_mapping(con))
        timed_if_missing(
            "import_market_partner_reference",
            "cfg_market_partner_role_effective",
            lambda: import_market_partner_reference(con),
        )
        timed_if_missing(
            "import_market_partner_mapping",
            "cfg_market_partner_mapping_effective",
            lambda: import_market_partner_mapping(con),
        )
        timed_if_missing(
            "import_vens_tens_exception",
            "cfg_vens_tens_exception_effective",
            lambda: import_vens_tens_exception(con),
        )
        timed("import_manual_overrides", lambda: import_manual_overrides(con))
        timed("apply_raw_manual_overrides", lambda: apply_raw_manual_overrides(con, ctx.run_id))

        print("Berechne Staging, Routen und Core-Timeline...")
        timed("build_loco_events", lambda: build_loco_events(con))
        timed("exclude_dummy_locomotives_from_staging", lambda: exclude_dummy_locomotives_from_staging(con))
        timed("apply_staging_manual_overrides", lambda: apply_staging_manual_overrides(con, ctx.run_id))
        timed("build_transport_routes", lambda: build_transport_routes(con))
        timed("build_core", lambda: build_core(con, ctx.run_id))
        timed("apply_core_assignment_fallbacks", lambda: apply_core_assignment_fallbacks(con, ctx.run_id))
        timed("prepare_timeline_context_phase6c", lambda: prepare_timeline_context_phase6c(con, ctx.run_id))
        timed("build_unresolved_performing_ru_alias", lambda: build_unresolved_performing_ru_market_partner_alias(con))

        print("Berechne Findings, Quality-Gate und Exporttabellen...")
        timed("build_findings", lambda: build_findings(con, ctx.run_id, home_country_iso=ctx.home_country_iso))
        timed("consolidate_dummy_locomotive_findings", lambda: consolidate_dummy_locomotive_findings(con, ctx.run_id))
        timed("harden_findings_and_export_policy", lambda: harden_findings_and_export_policy(con, ctx.run_id))
        timed("harden_findings_and_segments_phase6c", lambda: harden_findings_and_segments_phase6c(con, ctx.run_id))
        timed("build_quality_gate_tables", lambda: build_quality_gate_tables(con, ctx.run_id))
        timed("insert_gap_only_day_findings_phase6d", lambda: insert_gap_only_day_findings_phase6d(con, ctx.run_id))
        timed("apply_r016_to_quality_gate_tables", lambda: apply_r016_to_quality_gate_tables(con))
        timed("finalize_quality_gate_phase6d", lambda: finalize_quality_gate_phase6d(con, ctx.run_id))
        timed("build_export_tables", lambda: build_export_tables(con))
        timed("refresh_reconciliation_table", lambda: refresh_reconciliation_table(con, ctx.run_id))

        written_files = []
        if write_csv_outputs:
            print("Schreibe CSV-Ausgaben...")
            written_files = timed("export_all_csv_outputs", lambda: export_all_csv_outputs(con, ctx.export_dir))
        else:
            print("CSV-Ausgaben werden fuer schnellen Korrekturlauf uebersprungen.")

        con.close()
        con = None

        timed("replace_build_database", lambda: os.replace(ctx.db_build_path, ctx.db_path))
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))
        _write_timing_log(ctx, timings)

        if write_csv_outputs:
            return f"FULL_REBUILD_FROM_RAW abgeschlossen. CSV-Dateien geschrieben: {len(written_files)}"
        return "FULL_REBUILD_FROM_RAW abgeschlossen. CSV-Schreiben uebersprungen."

    except Exception:
        if con is not None:
            con.close()
        _remove_if_exists(ctx.db_build_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))
        if timings:
            _write_timing_log(ctx, timings)
        raise
