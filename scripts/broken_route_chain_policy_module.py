from __future__ import annotations

from typing import Iterable

BROKEN_ROUTE_CHAIN_POLICY_MARKER = "NETZENTGELT_NO_LTE_ASSIGNMENT_ONLY_POLICY_V2_20260630"
NO_LTE_ASSIGNMENT_RULE_IDS = ("R010", "R010.5", "R016")
NO_LTE_ASSIGNMENT_MARKERS = (
    "keine lte zuweisung",
    "keine lte zuordnung",
    "kein lte bezug",
    "keine lte-zuweisung",
    "keine lte-zuordnung",
    "no lte assignment",
)


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


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


def _columns(con, table_name: str) -> set[str]:
    if not _table_exists(con, table_name):
        return set()
    return {str(row[0]).lower() for row in con.execute(f"describe {qident(table_name)}").fetchall()}


def _has_columns(con, table_name: str, required_columns: Iterable[str]) -> bool:
    existing = _columns(con, table_name)
    return all(column.lower() in existing for column in required_columns)


def _text_marker_predicate(existing_columns: set[str], table_alias: str | None = None) -> str:
    searchable_columns = [
        column
        for column in [
            "message",
            "suggested_action",
            "performing_ru",
            "gate_reason",
            "finding_rule_ids",
            "performing_rus",
        ]
        if column in existing_columns
    ]
    if not searchable_columns:
        return "false"

    prefix = f"{table_alias}." if table_alias else ""
    terms: list[str] = []
    for column in searchable_columns:
        expr = f"lower(coalesce(cast({prefix}{qident(column)} as varchar), ''))"
        for marker in NO_LTE_ASSIGNMENT_MARKERS:
            terms.append(f"{expr} like '%{marker.replace("'", "''")}%' ")
    return "(" + " or ".join(terms) + ")"


def is_no_lte_assignment_marker(*values: object) -> bool:
    """Return True only for explicit no-LTE assignment markers in UI text."""
    combined = " ".join(str(value or "") for value in values).strip().casefold()
    return any(marker in combined for marker in NO_LTE_ASSIGNMENT_MARKERS)


def _mark_catalog_documentation(con) -> None:
    """Keep R010/R010.5/R016 active; document the explicit no-LTE exception."""
    if not _table_exists(con, "cfg_dq_rule_catalog"):
        return
    if not _has_columns(
        con,
        "cfg_dq_rule_catalog",
        ["rule_id", "description", "active_flag"],
    ):
        return

    con.execute(
        """
        update cfg_dq_rule_catalog
        set description = description || ' Sonderfall: explizite Keine-LTE-Zuordnung wird nicht als GAP-Fehler gewertet.'
        where rule_id in ('R010', 'R010.5', 'R016')
          and active_flag = true
          and position('Keine-LTE-Zuordnung' in description) = 0
        """
    )


def disable_broken_route_chain_rules(con) -> None:
    """Deactivate only explicit no-LTE assignment findings; keep normal GAP rules active."""
    if _table_exists(con, "dq_findings") and _has_columns(con, "dq_findings", ["rule_id"]):
        existing_columns = _columns(con, "dq_findings")
        marker_predicate = _text_marker_predicate(existing_columns)
        con.execute(
            f"""
            delete from dq_findings
            where rule_id in ('R010', 'R010.5', 'R016')
              and {marker_predicate}
            """
        )
    _mark_catalog_documentation(con)


def _coalesce_number(column_name: str, default: str = "0") -> str:
    return f"coalesce({qident(column_name)}, {default})"


def _gate_status_expression(existing_columns: set[str]) -> str:
    blocking_terms: list[str] = []
    warning_terms: list[str] = []

    for column in ["error_findings", "manual_review_findings", "not_export_ready_movement_rows"]:
        if column in existing_columns:
            blocking_terms.append(f"{_coalesce_number(column)} > 0")
    if "overlap_slot_count" in existing_columns:
        blocking_terms.append(f"{_coalesce_number('overlap_slot_count')} > 0")
    if "exact_overlap_seconds" in existing_columns:
        blocking_terms.append(f"{_coalesce_number('exact_overlap_seconds')} > 0")
    if "long_gap_rows" in existing_columns:
        blocking_terms.append(f"{_coalesce_number('long_gap_rows')} > 0")
    if "relevant_gap_slot_count" in existing_columns and "assignment_slot_count" in existing_columns:
        blocking_terms.append(
            f"({_coalesce_number('assignment_slot_count')} = 0 and {_coalesce_number('relevant_gap_slot_count')} > 0)"
        )

    if "relevant_gap_slot_count" in existing_columns:
        warning_terms.append(f"{_coalesce_number('relevant_gap_slot_count')} > 0")
    for column in ["warning_findings", "info_findings"]:
        if column in existing_columns:
            warning_terms.append(f"{_coalesce_number(column)} > 0")

    blocking_sql = " or ".join(blocking_terms) if blocking_terms else "false"
    warning_sql = " or ".join(warning_terms) if warning_terms else "false"
    return (
        "case "
        f"when {blocking_sql} then 'BLOCKED' "
        f"when {warning_sql} then 'WARNING' "
        "else 'READY' end"
    )


def _gate_reason_expression(existing_columns: set[str]) -> str:
    parts: list[str] = []
    if "error_findings" in existing_columns:
        parts.append(
            "case when coalesce(error_findings, 0) > 0 "
            "then 'ERROR-Findings=' || cast(error_findings as varchar) end"
        )
    if "manual_review_findings" in existing_columns:
        parts.append(
            "case when coalesce(manual_review_findings, 0) > 0 "
            "then 'Manual Reviews=' || cast(manual_review_findings as varchar) end"
        )
    if "overlap_slot_count" in existing_columns:
        parts.append(
            "case when coalesce(overlap_slot_count, 0) > 0 "
            "then 'Overlap-Minuten=' || cast(overlap_slot_count * 15 as varchar) end"
        )
    if "long_gap_rows" in existing_columns:
        parts.append(
            "case when coalesce(long_gap_rows, 0) > 0 "
            "then 'GAPs über 8h=' || cast(long_gap_rows as varchar) end"
        )
    if "not_export_ready_movement_rows" in existing_columns:
        parts.append(
            "case when coalesce(not_export_ready_movement_rows, 0) > 0 "
            "then 'Nicht exportfähige Movements=' || cast(not_export_ready_movement_rows as varchar) end"
        )
    if "relevant_gap_slot_count" in existing_columns:
        parts.append(
            "case when coalesce(relevant_gap_slot_count, 0) > 0 "
            "then 'Ungeklärte GAP-Minuten=' || cast(relevant_gap_slot_count * 15 as varchar) end"
        )
    if "warning_findings" in existing_columns:
        parts.append(
            "case when coalesce(warning_findings, 0) > 0 "
            "then 'WARNING-Findings=' || cast(warning_findings as varchar) end"
        )
    if "info_findings" in existing_columns:
        parts.append(
            "case when coalesce(info_findings, 0) > 0 "
            "then 'INFO-Findings=' || cast(info_findings as varchar) end"
        )
    if "exact_overlap_minutes" in existing_columns:
        parts.append(
            "case when coalesce(exact_overlap_minutes, 0) > 0 "
            "then 'Tatsaechliche Ueberschneidung=' || cast(round(exact_overlap_minutes, 2) as varchar) || ' Minuten' end"
        )

    if not parts:
        return "''"
    return "concat_ws(' | ', " + ", ".join(parts) + ")"


def neutralize_broken_route_chain_quality_gate(con) -> None:
    """Neutralize gate metrics only when the row itself explicitly says Keine LTE Zuordnung."""
    gap_metric_defaults = {
        "relevant_gap_slot_count": "0",
        "unresolved_gap_minutes": "0",
        "relevant_gap_rows": "0",
        "long_gap_rows": "0",
        "max_gap_minutes": "0",
    }

    for table_name in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        if not _table_exists(con, table_name):
            continue
        existing_columns = _columns(con, table_name)
        marker_predicate = _text_marker_predicate(existing_columns)
        if marker_predicate == "false":
            continue
        assignments = [
            f"{qident(column)} = {default}"
            for column, default in gap_metric_defaults.items()
            if column in existing_columns
        ]
        if "gate_status" in existing_columns:
            assignments.append(f"gate_status = {_gate_status_expression(existing_columns)}")
        if "gate_reason" in existing_columns:
            assignments.append(f"gate_reason = {_gate_reason_expression(existing_columns)}")
        if assignments:
            con.execute(
                f"update {qident(table_name)} set " + ", ".join(assignments) + f" where {marker_predicate}"
            )


def patch_error_rules_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_POLICY_PATCHED", False):
        return

    if hasattr(module, "build_rule_catalog"):
        original_build_rule_catalog = module.build_rule_catalog

        def patched_build_rule_catalog(con, *args, **kwargs):
            result = original_build_rule_catalog(con, *args, **kwargs)
            disable_broken_route_chain_rules(con)
            return result

        module.build_rule_catalog = patched_build_rule_catalog

    if hasattr(module, "build_findings"):
        original_build_findings = module.build_findings

        def patched_build_findings(con, run_id: str, *args, **kwargs):
            result = original_build_findings(con, run_id, *args, **kwargs)
            disable_broken_route_chain_rules(con)
            if hasattr(module, "refresh_core_quality_flags"):
                module.refresh_core_quality_flags(con)
            return result

        module.build_findings = patched_build_findings

    module._BROKEN_ROUTE_CHAIN_POLICY_PATCHED = True


def patch_quality_gate_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED", False):
        return
    if not hasattr(module, "build_quality_gate_tables"):
        return

    original_build_quality_gate_tables = module.build_quality_gate_tables

    def patched_build_quality_gate_tables(con, run_id: str, *args, **kwargs):
        result = original_build_quality_gate_tables(con, run_id, *args, **kwargs)
        disable_broken_route_chain_rules(con)
        neutralize_broken_route_chain_quality_gate(con)
        return result

    module.build_quality_gate_tables = patched_build_quality_gate_tables
    module._BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED = True


def patch_phase6d_gap_only_rule(module) -> None:
    """Keep normal R016 active; no global patch for GAP-only days."""
    if getattr(module, "_BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED", False):
        return
    module._BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED = True
