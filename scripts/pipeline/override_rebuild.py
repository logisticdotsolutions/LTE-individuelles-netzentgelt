"""Schneller Override-Rebuild auf Basis der vorhandenen Tages-DuckDB.

Der Modus ist fuer UI-Korrekturen gedacht, bei denen keine Rohdaten neu aus dem
Datalake importiert werden muessen. Aus Sicherheitsgruenden wird die produktive
DuckDB nie direkt bearbeitet: Zuerst wird eine Build-Kopie erzeugt. Erst nach
erfolgreichem Lauf ersetzt diese Kopie den produktiven Stand.

Wichtig: Rohdatenveraendernde Overrides duerfen in diesem schnellen Modus nicht
neu oder geaendert sein, weil die aktuelle produktive DuckDB bereits angewandte
Rohdatenkorrekturen enthalten kann. In diesem Fall wird bewusst abgebrochen und
ein FULL_IMPORT_REBUILD verlangt.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import duckdb

from .context import PipelineContext
from .csv_outputs import export_all_csv_outputs

RAW_AFFECTING_OVERRIDE_TYPES = (
    "SET_LOCO_NO",
    "SET_PERFORMING_RU",
    "SET_ACTUAL_DEPARTURE",
    "SET_ACTUAL_ARRIVAL",
)


def _ensure_scripts_dir_on_path() -> None:
    """Imports bestehender Legacy-Module aus dem scripts-Verzeichnis erlauben."""
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


def _quote_literal_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def _create_raw_override_snapshot(con, table_name: str) -> None:
    type_list = _quote_literal_list(RAW_AFFECTING_OVERRIDE_TYPES)

    if not _table_exists(con, "cfg_manual_overrides_effective"):
        con.execute(
            f"""
            create or replace temporary table {table_name} as
            select
                cast(null as varchar) as override_type_norm,
                cast(null as varchar) as override_id,
                cast(null as varchar) as transport_number,
                cast(null as varchar) as target_loco_no,
                cast(null as varchar) as target_actual_departure_utc,
                cast(null as varchar) as target_actual_arrival_utc,
                cast(null as varchar) as override_value
            where false
            """
        )
        return

    con.execute(
        f"""
        create or replace temporary table {table_name} as
        select
            upper(trim(coalesce(override_type, ''))) as override_type_norm,
            nullif(trim(coalesce(override_id, '')), '') as override_id,
            nullif(trim(coalesce(transport_number, '')), '') as transport_number,
            nullif(trim(coalesce(target_loco_no, '')), '') as target_loco_no,
            nullif(trim(coalesce(target_actual_departure_utc, '')), '') as target_actual_departure_utc,
            nullif(trim(coalesce(target_actual_arrival_utc, '')), '') as target_actual_arrival_utc,
            nullif(trim(coalesce(override_value, '')), '') as override_value
        from cfg_manual_overrides_effective
        where upper(trim(coalesce(override_type, ''))) in ({type_list})
        order by
            override_type_norm,
            override_id,
            transport_number,
            target_loco_no,
            target_actual_departure_utc,
            target_actual_arrival_utc,
            override_value
        """
    )


def _assert_raw_affecting_overrides_unchanged(con) -> None:
    old_count, new_count, changed_count = con.execute(
        """
        with old_rows as (
            select * from __override_rebuild_old_raw_overrides
        ),
        new_rows as (
            select * from __override_rebuild_new_raw_overrides
        ),
        delta as (
            (select * from old_rows except all select * from new_rows)
            union all
            (select * from new_rows except all select * from old_rows)
        )
        select
            (select count(*) from old_rows) as old_count,
            (select count(*) from new_rows) as new_count,
            (select count(*) from delta) as changed_count
        """
    ).fetchone()

    if int(changed_count or 0) > 0:
        raise RuntimeError(
            "OVERRIDE_REBUILD abgebrochen: Rohdatenveraendernde Overrides haben sich "
            "geaendert. Bitte FULL_IMPORT_REBUILD ausfuehren, damit die Rohdaten aus "
            "dem unveraenderten CSV-/Datalake-Snapshot sauber neu aufgebaut werden. "
            f"Vorherige Raw-Override-Zeilen: {old_count}, aktuelle Raw-Override-Zeilen: {new_count}."
        )


def run_override_rebuild(ctx: PipelineContext) -> str:
    """Korrekturen neu anwenden und ab Staging/Core bis Export atomar neu berechnen."""
    ctx.ensure_directories()

    if not ctx.db_path.exists():
        raise FileNotFoundError(
            f"Produktive DuckDB nicht gefunden: {ctx.db_path}. "
            "Zuerst FULL_IMPORT_REBUILD bzw. scripts/run_all.py ausfuehren."
        )

    _ensure_scripts_dir_on_path()

    from dummy_locomotive_module import (
        consolidate_dummy_locomotive_findings,
        exclude_dummy_locomotives_from_staging,
    )
    from error_rules import build_findings
    from export_module import build_export_tables
    from manual_override_module import (
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
        build_core,
        build_loco_events,
        build_transport_routes,
        build_unresolved_performing_ru_market_partner_alias,
    )

    _remove_if_exists(ctx.db_build_path)
    _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

    print(f"Erzeuge Build-Kopie aus produktiver Tages-Datenbank: {ctx.db_build_path}")
    shutil.copy2(ctx.db_path, ctx.db_build_path)

    con = None

    try:
        con = duckdb.connect(str(ctx.db_build_path))

        print("Pruefe Raw-Override-Sicherheit...")
        _create_raw_override_snapshot(con, "__override_rebuild_old_raw_overrides")
        import_manual_overrides(con)
        _create_raw_override_snapshot(con, "__override_rebuild_new_raw_overrides")
        _assert_raw_affecting_overrides_unchanged(con)

        print("Berechne Staging ab vorhandenen Raw-Tabellen neu...")
        build_loco_events(con)
        exclude_dummy_locomotives_from_staging(con)
        apply_staging_manual_overrides(con, ctx.run_id)

        print("Berechne Routen und Core-Timeline neu...")
        build_transport_routes(con)
        build_core(con, ctx.run_id)
        apply_core_assignment_fallbacks(con, ctx.run_id)
        prepare_timeline_context_phase6c(con, ctx.run_id)
        build_unresolved_performing_ru_market_partner_alias(con)

        print("Berechne Findings, Quality-Gate und Export neu...")
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

        print("Schreibe CSV-Ausgaben neu...")
        written_files = export_all_csv_outputs(con, ctx.export_dir)

        con.close()
        con = None

        os.replace(ctx.db_build_path, ctx.db_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

        return f"OVERRIDE_REBUILD abgeschlossen. CSV-Dateien geschrieben: {len(written_files)}"

    except Exception:
        if con is not None:
            con.close()
        _remove_if_exists(ctx.db_build_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))
        raise
