"""CSV-Ausgabe der Netzentgelt-Pipeline.

Dieses Modul kapselt die bisher in scripts/run_all.py fest verdrahtete Liste der
CSV-Ausgaben. Der erste Schritt ist bewusst mechanisch gehalten: Tabellenliste,
Dateinamen und COPY-Optionen bleiben fachlich unveraendert.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


CSV_OUTPUT_TABLES: tuple[tuple[str, str], ...] = (
    ("raw_import_run", "raw_import_run.csv"),
    ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),
    ("cfg_dummy_locomotives_effective", "cfg_dummy_locomotives_effective.csv"),
    ("audit_excluded_dummy_locomotives", "audit_excluded_dummy_locomotives.csv"),
    ("audit_excluded_dummy_locomotive_staging", "audit_excluded_dummy_locomotive_staging.csv"),
    ("cfg_manual_overrides", "cfg_manual_overrides.csv"),
    ("cfg_manual_overrides_effective", "cfg_manual_overrides_effective.csv"),
    ("dq_manual_override_conflicts", "dq_manual_override_conflicts.csv"),
    ("audit_manual_override_application", "audit_manual_override_application.csv"),
    ("dq_rule_engine_hardening_audit", "dq_rule_engine_hardening_audit.csv"),
    ("dq_rule_engine_hardening_blockers", "dq_rule_engine_hardening_blockers.csv"),
    ("dq_rule_engine_hardening_phase6c_audit", "dq_rule_engine_hardening_phase6c_audit.csv"),
    ("dq_rule_engine_hardening_phase6d_audit", "dq_rule_engine_hardening_phase6d_audit.csv"),
    ("dq_phase6d_exact_overlap_days", "dq_phase6d_exact_overlap_days.csv"),
    ("dq_phase6c_uncertain_gaps", "dq_phase6c_uncertain_gaps.csv"),
    ("dq_phase6c_gap_context_review", "dq_phase6c_gap_context_review.csv"),
    ("core_loco_stand_candidates", "core_loco_stand_candidates.csv"),
    ("core_usage_assignment_segment_movements", "core_usage_assignment_segment_movements.csv"),
    ("core_usage_assignment_segments", "core_usage_assignment_segments.csv"),
    ("stg_loco_events", "stg_loco_events.csv"),
    ("core_loco_timeline", "core_loco_timeline.csv"),
    ("dq_findings", "dq_findings.csv"),
    ("dq_run_metadata", "dq_run_metadata.csv"),
    ("core_loco_day_coverage", "core_loco_day_coverage.csv"),
    ("dq_export_gate", "dq_export_gate.csv"),
    ("dq_export_gate_ru", "dq_export_gate_ru.csv"),
    ("dq_global_export_blockers", "dq_global_export_blockers.csv"),
    ("export_excluded_rows", "export_excluded_rows.csv"),
    ("dq_reconciliation", "dq_reconciliation.csv"),
    ("dq_operational_kpis", "dq_operational_kpis.csv"),
    ("cfg_dq_rule_catalog", "cfg_dq_rule_catalog.csv"),
    ("cfg_market_partner_role", "cfg_market_partner_role.csv"),
    ("cfg_market_partner_role_conflicts", "cfg_market_partner_role_conflicts.csv"),
    ("cfg_market_partner_mapping", "cfg_market_partner_mapping.csv"),
    ("cfg_market_partner_mapping_effective", "cfg_market_partner_mapping_effective.csv"),
    ("cfg_market_partner_mapping_conflicts", "cfg_market_partner_mapping_conflicts.csv"),
    ("cfg_market_partner_mapping_invalid", "cfg_market_partner_mapping_invalid.csv"),
    ("cfg_vens_tens_exception", "cfg_vens_tens_exception.csv"),
    ("cfg_vens_tens_exception_effective", "cfg_vens_tens_exception_effective.csv"),
    ("cfg_vens_tens_exception_conflicts", "cfg_vens_tens_exception_conflicts.csv"),
    ("dq_unresolved_performing_ru_market_partner_alias", "dq_unresolved_performing_ru_market_partner_alias.csv"),
    ("export_zuordnungen", "export_zuordnungen.csv"),
    ("export_nutzungsmeldung", "export_nutzungsmeldung.csv"),
    ("stg_loco_events_skipped", "stg_loco_events_skipped.csv"),
    ("stg_transport_details_enriched", "stg_transport_details_enriched.csv"),
    ("core_transport_route", "core_transport_route.csv"),
)


def quote_identifier(name: str) -> str:
    """SQL-Identifier fuer DuckDB sicher quoten."""
    return '"' + name.replace('"', '""') + '"'


def export_table(con, export_dir: Path, table: str, file_name: str) -> Path:
    """Eine DuckDB-Tabelle als Semikolon-CSV exportieren."""
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / file_name
    con.execute(
        f"copy {quote_identifier(table)} to ? (header true, delimiter ';')",
        [str(path)],
    )
    print(f"Export: {path}")
    return path


def export_all_csv_outputs(
    con,
    export_dir: Path,
    outputs: Iterable[tuple[str, str]] = CSV_OUTPUT_TABLES,
) -> list[Path]:
    """Alle Standard-CSV-Ausgaben schreiben."""
    written_files: list[Path] = []

    for table, file_name in outputs:
        written_files.append(export_table(con, export_dir, table, file_name))

    return written_files
