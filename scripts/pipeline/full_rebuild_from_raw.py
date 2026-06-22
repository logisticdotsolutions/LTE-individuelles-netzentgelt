"""Full-Rebuild aus einer vorhandenen Raw-DuckDB.

Dieser Modus trennt den teuren CSV-Import von der fachlichen Berechnung. Die
Raw-DuckDB bleibt die unveraenderte Importbasis. Aus ihr wird eine Build-DuckDB
kopiert, auf der Mapping, Overrides, Staging, Core, Findings, Quality-Gate und
Exporte neu berechnet werden.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import duckdb

from .context import PipelineContext
from .csv_outputs import export_all_csv_outputs


def _ensure_scripts_dir_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)

    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def run_full_rebuild_from_raw(
    ctx: PipelineContext,
    *,
    write_csv_outputs: bool = True,
) -> str:
    """Fachliche Datenbank aus bestehender Raw-DuckDB neu erzeugen.

    `write_csv_outputs=False` ist fuer schnelle UI-Korrekturen gedacht: Die
    Exporttabellen werden in DuckDB trotzdem berechnet, aber die vielen CSV-
    Dateien werden nicht bei jeder Korrektur neu geschrieben.
    """
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

    _remove_if_exists(ctx.db_build_path)
    _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

    print(f"Kopiere Raw-DuckDB in Build-Datenbank: {ctx.db_build_path}")
    shutil.copy2(ctx.raw_db_path, ctx.db_build_path)

    con = None

    try:
        con = duckdb.connect(str(ctx.db_build_path))

        print("Berechne Exclusions, Referenzen und manuelle Overrides...")
        build_cancelled_transport_exclusions(con)
        build_dummy_locomotive_catalog(con)
        import_mapping(con)
        import_market_partner_reference(con)
        import_market_partner_mapping(con)
        import_vens_tens_exception(con)
        import_manual_overrides(con)
        apply_raw_manual_overrides(con, ctx.run_id)

        print("Berechne Staging, Routen und Core-Timeline...")
        build_loco_events(con)
        exclude_dummy_locomotives_from_staging(con)
        apply_staging_manual_overrides(con, ctx.run_id)
        build_transport_routes(con)
        build_core(con, ctx.run_id)
        apply_core_assignment_fallbacks(con, ctx.run_id)
        prepare_timeline_context_phase6c(con, ctx.run_id)
        build_unresolved_performing_ru_market_partner_alias(con)

        print("Berechne Findings, Quality-Gate und Exporttabellen...")
        build_findings(con, ctx.run_id, home_country_iso=ctx.home_country_iso)
        consolidate_dummy_locomotive_findings(con, ctx.run_id)
        harden_findings_and_export_policy(con, ctx.run_id)
        harden_findings_and_segments_phase6c(con, ctx.run_id)
        build_quality_gate_tables(con, ctx.run_id)
        insert_gap_only_day_findings_phase6d(con, ctx.run_id)
        build_quality_gate_tables(con, ctx.run_id)
        finalize_quality_gate_phase6d(con, ctx.run_id)
        build_export_tables(con)
        refresh_reconciliation_table(con, ctx.run_id)

        written_files = []
        if write_csv_outputs:
            print("Schreibe CSV-Ausgaben...")
            written_files = export_all_csv_outputs(con, ctx.export_dir)
        else:
            print("CSV-Ausgaben werden fuer schnellen Korrekturlauf uebersprungen.")

        con.close()
        con = None

        os.replace(ctx.db_build_path, ctx.db_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

        if write_csv_outputs:
            return f"FULL_REBUILD_FROM_RAW abgeschlossen. CSV-Dateien geschrieben: {len(written_files)}"
        return "FULL_REBUILD_FROM_RAW abgeschlossen. CSV-Schreiben uebersprungen."

    except Exception:
        if con is not None:
            con.close()
        _remove_if_exists(ctx.db_build_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))
        raise
