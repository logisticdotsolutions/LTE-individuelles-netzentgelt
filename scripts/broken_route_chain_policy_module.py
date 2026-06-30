from __future__ import annotations

BROKEN_ROUTE_CHAIN_POLICY_MARKER = "NETZENTGELT_NO_LTE_ASSIGNMENT_ONLY_POLICY_V3_20260630"
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
    return bool(
        con.execute(
            "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
            [table_name],
        ).fetchone()[0]
    )


def _columns(con, table_name: str) -> set[str]:
    if not _table_exists(con, table_name):
        return set()
    return {str(row[0]).lower() for row in con.execute(f"describe {qident(table_name)}").fetchall()}


def is_no_lte_assignment_marker(*values: object) -> bool:
    """Return True only for explicit no-LTE assignment markers in UI text."""
    combined = " ".join(str(value or "") for value in values).strip().casefold()
    return any(marker in combined for marker in NO_LTE_ASSIGNMENT_MARKERS)


def _marker_sql(existing_columns: set[str], candidates: tuple[str, ...], alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    terms: list[str] = []
    for column in candidates:
        if column.lower() not in existing_columns:
            continue
        expr = f"lower(coalesce(cast({prefix}{qident(column)} as varchar), ''))"
        for marker in NO_LTE_ASSIGNMENT_MARKERS:
            terms.append("{} like '%{}%'".format(expr, marker.replace("'", "''")))
    return "(" + " or ".join(terms) + ")" if terms else "false"


def _mark_explicit_no_lte_gaps_outside_de(con) -> None:
    if not _table_exists(con, "core_loco_timeline"):
        return
    cols = _columns(con, "core_loco_timeline")
    predicate = _marker_sql(
        cols,
        (
            "holder_name",
            "performing_ru",
            "decision_reason",
            "dq_message",
            "dq_messages",
            "de_event_label",
            "cal_route_type_home",
        ),
    )
    if predicate == "false":
        return
    assignments = []
    if "gap_relevant_de" in cols:
        assignments.append("gap_relevant_de = false")
    if "report_scope" in cols:
        assignments.append("report_scope = 'NOT_IN_REPORT'")
    if "de_event_label" in cols:
        assignments.append("de_event_label = 'Außerhalb DE'")
    if "cal_route_type_home" in cols:
        assignments.append("cal_route_type_home = 'Außerhalb DE'")
    if "dq_severity" in cols:
        assignments.append("dq_severity = ''")
    if "needs_manual_review" in cols:
        assignments.append("needs_manual_review = false")
    if not assignments:
        return
    con.execute(
        "update core_loco_timeline set "
        + ", ".join(assignments)
        + " where row_type = 'GAP' and "
        + predicate
    )


def _remove_explicit_no_lte_findings(con) -> None:
    if not _table_exists(con, "dq_findings"):
        return
    f_cols = _columns(con, "dq_findings")
    marker_on_finding = _marker_sql(f_cols, ("message", "suggested_action", "performing_ru"), alias="f")
    marker_on_core = "false"
    join_core = ""
    if _table_exists(con, "core_loco_timeline"):
        c_cols = _columns(con, "core_loco_timeline")
        marker_on_core = _marker_sql(
            c_cols,
            ("holder_name", "performing_ru", "decision_reason", "dq_message", "dq_messages"),
            alias="c",
        )
        join_core = """
            left join core_loco_timeline c
              on c.row_type is not distinct from f.row_type
             and c.loco_no is not distinct from f.loco_no
             and c.transport_number is not distinct from f.transport_number
             and c.period_start_utc is not distinct from f.period_start_utc
             and c.period_end_utc is not distinct from f.period_end_utc
             and c.source_table is not distinct from f.source_table
             and c.source_row_id is not distinct from f.source_row_id
        """
    con.execute(
        f"""
        create or replace table dq_findings as
        select f.*
        from dq_findings f
        {join_core}
        where not (
            f.rule_id in ('R010', 'R010.5', 'R016')
            and ({marker_on_finding} or {marker_on_core})
        )
        """
    )


def disable_broken_route_chain_rules(con) -> None:
    """Only explicit no-LTE assignment gaps are neutralized; normal GAPs stay active."""
    _mark_explicit_no_lte_gaps_outside_de(con)
    _remove_explicit_no_lte_findings(con)


def neutralize_broken_route_chain_quality_gate(con) -> None:
    """No blanket gate neutralization; the scoped core marker is applied before gate build."""
    _mark_explicit_no_lte_gaps_outside_de(con)


def patch_error_rules_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_POLICY_PATCHED", False):
        return
    if hasattr(module, "build_findings"):
        original = module.build_findings

        def patched_build_findings(con, run_id: str, *args, **kwargs):
            result = original(con, run_id, *args, **kwargs)
            disable_broken_route_chain_rules(con)
            if hasattr(module, "refresh_core_quality_flags"):
                module.refresh_core_quality_flags(con)
            return result

        module.build_findings = patched_build_findings
    module._BROKEN_ROUTE_CHAIN_POLICY_PATCHED = True


def patch_quality_gate_module(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED", False):
        return
    if hasattr(module, "build_quality_gate_tables"):
        original = module.build_quality_gate_tables

        def patched_build_quality_gate_tables(con, run_id: str, *args, **kwargs):
            disable_broken_route_chain_rules(con)
            result = original(con, run_id, *args, **kwargs)
            return result

        module.build_quality_gate_tables = patched_build_quality_gate_tables
    module._BROKEN_ROUTE_CHAIN_QG_POLICY_PATCHED = True


def patch_phase6d_gap_only_rule(module) -> None:
    if getattr(module, "_BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED", False):
        return
    module._BROKEN_ROUTE_CHAIN_R016_POLICY_PATCHED = True
