"""Partieller Rebuild fuer eine Teilmenge von Loknummern (Fast-Correction-Rebuild).

Strategie: Raw-DB kopieren → alle Staging-/Core-Schritte vollstaendig ausfuehren →
DQ-Tabellen aus Prod-DB uebernehmen → nur fuer betroffene Loknummern DQ neu berechnen.

Dieses Vorgehen ist korrekt, weil:
- Raw-Daten und Overrides fuer nicht-betroffene Loknummern unveraendert sind.
- Staging/Core fuer nicht-betroffene Loknummern produziert daher identische Ergebnisse.
- Die aus der Prod-DB uebernommenen DQ-Zeilen spiegeln daher den richtigen Zustand wider.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from time import perf_counter

import duckdb

from .context import PipelineContext


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[1]
    scripts_dir_text = str(scripts_dir)
    if scripts_dir_text not in sys.path:
        sys.path.insert(0, scripts_dir_text)


_ensure_scripts_on_path()


_DQ_TABLES_TO_COPY = (
    # phase6c-Kontexttabellen — muessen vor prepare_timeline_context_phase6c da sein
    "dq_phase6c_uncertain_gaps",
    "dq_phase6c_gap_context_review",
    "dq_phase6c_nested_event_skips",
    "core_loco_stand_candidates",
    # DQ-Ergebnistabellen
    "dq_findings",
    "core_loco_day_coverage",
    "dq_export_gate",
    "export_excluded_rows",
    "core_usage_assignment_segments",
    "core_usage_assignment_segment_movements",
)


def _copy_dq_tables_from_prod(con, prod_db_path: Path) -> None:
    """DQ-Tabellen aus Prod-DB in Build-DB kopieren (Basis fuer loco_filter)."""
    escaped = str(prod_db_path).replace("'", "''")
    con.execute(f"attach '{escaped}' as _prod_source (READ_ONLY)")
    try:
        for table in _DQ_TABLES_TO_COPY:
            exists_in_prod = con.execute(
                "select count(*) from duckdb_tables() "
                "where database_name = '_prod_source' and lower(table_name) = lower(?)",
                [table],
            ).fetchone()[0]
            if exists_in_prod:
                con.execute(
                    f"create or replace table {table} as "
                    f"select * from _prod_source.main.{table}"
                )
                print(f"  DQ-Tabelle von Prod kopiert: {table}")
    finally:
        con.execute("detach _prod_source")


def _remove_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def run_partial_correction_rebuild(
    ctx: PipelineContext,
    *,
    affected_loco_nos: frozenset[str],
) -> str:
    """Partieller Rebuild nur fuer die angegebenen Loknummern.

    Voraussetzung: affected_loco_nos ist nicht leer und eine Prod-DB existiert.
    """
    if not affected_loco_nos:
        return "Partieller Rebuild: keine betroffenen Loknummern. Nichts zu tun."

    if not ctx.raw_db_path.exists():
        raise FileNotFoundError(
            f"Raw-DuckDB nicht gefunden: {ctx.raw_db_path}. "
            "Bitte zuerst RAW_IMPORT_REBUILD ausfuehren."
        )

    if not ctx.db_path.exists():
        raise FileNotFoundError(
            f"Prod-DuckDB nicht gefunden: {ctx.db_path}. "
            "Partieller Rebuild benoetigt eine bestehende Prod-DB. "
            "Bitte zuerst FULL_REBUILD_FROM_RAW ausfuehren."
        )

    _ensure_scripts_on_path()

    from dummy_locomotive_module import (
        build_dummy_locomotive_catalog,
        consolidate_dummy_locomotive_findings,
        exclude_dummy_locomotives_from_staging,
    )
    from error_rules import build_findings, table_exists
    from export_module import build_export_tables
    from manual_override_module import (
        apply_raw_manual_overrides,
        apply_staging_manual_overrides,
        import_manual_overrides,
    )
    from process_decision_module import build_process_decision_layer
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
    from .quality_gate_incremental import apply_r016_to_quality_gate_tables

    timings: list[dict] = []

    def timed(label: str, func):
        started = perf_counter()
        result = func()
        seconds = round(perf_counter() - started, 3)
        timings.append({"step": label, "seconds": seconds})
        print(f"TIMING [{label}]: {seconds:.3f}s")
        return result

    def timed_if_missing(label: str, table_name: str, func):
        if table_exists(con, table_name):
            timings.append({"step": label, "seconds": 0.0, "skipped": True})
            print(f"TIMING [{label}]: 0.000s skipped")
            return None
        return timed(label, func)

    print(
        f"Partieller Rebuild gestartet. "
        f"Betroffene Loknummern: {sorted(affected_loco_nos)}"
    )

    _remove_if_exists(ctx.db_build_path)
    _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

    timed("copy_raw_to_build", lambda: shutil.copy2(ctx.raw_db_path, ctx.db_build_path))

    con = None
    try:
        con = duckdb.connect(str(ctx.db_build_path))
        thread_count = max(1, min(os.cpu_count() or 1, 8))
        con.execute(f"set threads to {thread_count}")

        # Referenz-/Konfig-Schritte: ueberspringen wenn schon im Raw-DB-Copy vorhanden
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

        # Staging- und Core-Schritte vollstaendig (schnell)
        timed("import_manual_overrides", lambda: import_manual_overrides(con))
        timed("apply_raw_manual_overrides", lambda: apply_raw_manual_overrides(con, ctx.run_id))
        timed("build_loco_events", lambda: build_loco_events(con))
        timed("exclude_dummy_locomotives_from_staging", lambda: exclude_dummy_locomotives_from_staging(con))
        timed("apply_staging_manual_overrides", lambda: apply_staging_manual_overrides(con, ctx.run_id))
        timed_if_missing(
            "build_transport_routes",
            "core_transport_route",
            lambda: build_transport_routes(con),
        )
        timed("build_core", lambda: build_core(con, ctx.run_id))
        timed("apply_core_assignment_fallbacks", lambda: apply_core_assignment_fallbacks(con, ctx.run_id))
        timed("build_unresolved_performing_ru_alias", lambda: build_unresolved_performing_ru_market_partner_alias(con))

        # lf muss vor dem ersten Gebrauch in einer Lambda definiert sein
        lf = affected_loco_nos

        # DQ- und phase6c-Tabellen aus Prod-DB uebernehmen — muss vor
        # prepare_timeline_context_phase6c liegen, damit der loco_filter-Modus greift.
        timed("copy_dq_tables_from_prod", lambda: _copy_dq_tables_from_prod(con, ctx.db_path))

        timed("prepare_timeline_context_phase6c", lambda: prepare_timeline_context_phase6c(con, ctx.run_id, loco_filter=lf))

        # DQ-Schritte partiell (nur betroffene Loknummern)
        timed("build_findings", lambda: build_findings(con, ctx.run_id, home_country_iso=ctx.home_country_iso, loco_filter=lf))
        timed("consolidate_dummy_locomotive_findings", lambda: consolidate_dummy_locomotive_findings(con, ctx.run_id))
        timed("harden_findings_and_export_policy", lambda: harden_findings_and_export_policy(con, ctx.run_id, loco_filter=lf))
        timed("harden_findings_and_segments_phase6c", lambda: harden_findings_and_segments_phase6c(con, ctx.run_id, loco_filter=lf))
        timed("build_quality_gate_tables", lambda: build_quality_gate_tables(con, ctx.run_id, loco_filter=lf))
        timed("insert_gap_only_day_findings_phase6d", lambda: insert_gap_only_day_findings_phase6d(con, ctx.run_id, loco_filter=lf))
        timed("apply_r016_to_quality_gate_tables", lambda: apply_r016_to_quality_gate_tables(con))
        timed("finalize_quality_gate_phase6d", lambda: finalize_quality_gate_phase6d(con, ctx.run_id, loco_filter=lf))
        timed("build_export_tables", lambda: build_export_tables(con))
        timed("build_process_decision_layer", lambda: build_process_decision_layer(con, ctx.run_id))
        timed("refresh_reconciliation_table", lambda: refresh_reconciliation_table(con, ctx.run_id))

        con.close()
        con = None

        os.replace(ctx.db_build_path, ctx.db_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))

        total = round(sum(float(t["seconds"]) for t in timings), 3)
        print(f"Partieller Rebuild abgeschlossen in {total:.3f}s. "
              f"Betroffene Loknummern: {len(affected_loco_nos)}")
        return (
            f"PARTIAL_CORRECTION_REBUILD abgeschlossen. "
            f"Loknummern={len(affected_loco_nos)}, Gesamt={total:.3f}s"
        )

    except Exception:
        if con is not None:
            con.close()
        _remove_if_exists(ctx.db_build_path)
        _remove_if_exists(Path(str(ctx.db_build_path) + ".wal"))
        raise
