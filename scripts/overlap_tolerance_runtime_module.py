"""Fachliche Toleranz fuer kurze zeitliche Ueberschneidungen.

Anforderung:
- Zeitliche Ueberschneidungen bis einschliesslich 5 Minuten sollen ignoriert
  werden.

Dieses Modul aendert keine Rohdaten. Es entfernt nur R011-Findings und
Quality-Gate-Blockaden, wenn die tatsaechliche Ueberschneidungsdauer maximal
300 Sekunden betraegt. Die eigentliche Pipeline bleibt unveraendert und wird nur
zur Laufzeit um diese Toleranzschicht ergaenzt.
"""

from __future__ import annotations

OVERLAP_TOLERANCE_SECONDS = 5 * 60
OVERLAP_TOLERANCE_MARKER = "NETZENTGELT_OVERLAP_TOLERANCE_PHASE13B_V1_20260621"
_PATCHED = False


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
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


def columns(con, table_name: str) -> list[str]:
    if not table_exists(con, table_name):
        return []
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def _ensure_column(con, table_name: str, column_name: str, data_type: str) -> None:
    existing = {column.lower() for column in columns(con, table_name)}
    if column_name.lower() not in existing:
        con.execute(
            f"alter table {qident(table_name)} add column {qident(column_name)} {data_type}"
        )


def apply_overlap_tolerance_to_findings(con) -> int:
    """R011-Findings bis einschliesslich 5 Minuten entfernen."""
    if not table_exists(con, "dq_findings") or not table_exists(con, "core_loco_timeline"):
        return 0

    con.execute(
        f"""
        create or replace temp table tmp_short_r011_findings as
        with ordered as (
            select
                source_table,
                source_row_id,
                lag(period_end_utc) over (
                    partition by loco_no
                    order by
                        coalesce(sequence_ts, period_start_utc, period_end_utc) asc nulls last,
                        source_row_id asc
                ) as prev_end
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
        )
        select
            f.source_table,
            f.source_row_id,
            greatest(0, date_diff('second', f.period_start_utc, o.prev_end)) as overlap_seconds
        from dq_findings f
        join ordered o
          on f.source_table is not distinct from o.source_table
         and f.source_row_id is not distinct from o.source_row_id
        where f.rule_id = 'R011'
          and f.period_start_utc is not null
          and o.prev_end is not null
          and f.period_start_utc < o.prev_end
          and greatest(0, date_diff('second', f.period_start_utc, o.prev_end)) <= {OVERLAP_TOLERANCE_SECONDS}
        """
    )

    removed = int(con.execute("select count(*) from tmp_short_r011_findings").fetchone()[0])

    con.execute(
        """
        delete from dq_findings as f
        using tmp_short_r011_findings as s
        where f.rule_id = 'R011'
          and f.source_table is not distinct from s.source_table
          and f.source_row_id is not distinct from s.source_row_id
        """
    )

    if removed:
        con.execute(
            """
            create table if not exists dq_overlap_tolerance_audit (
                phase_id varchar,
                rule_id varchar,
                source_table varchar,
                source_row_id bigint,
                overlap_seconds bigint,
                tolerance_seconds bigint,
                action varchar,
                calculated_at_utc timestamp
            )
            """
        )
        con.execute(
            """
            insert into dq_overlap_tolerance_audit
            select
                ?::varchar,
                'R011'::varchar,
                source_table,
                source_row_id,
                overlap_seconds,
                ?::bigint,
                'IGNORED_SHORT_OVERLAP'::varchar,
                current_timestamp
            from tmp_short_r011_findings
            """,
            [OVERLAP_TOLERANCE_MARKER, OVERLAP_TOLERANCE_SECONDS],
        )

    try:
        import error_rules

        error_rules.refresh_core_quality_flags(con)
    except Exception:
        pass

    if removed:
        print(
            "Overlap-Toleranz aktiv: "
            f"{removed} R011-Finding(s) bis einschliesslich 5 Minuten ignoriert."
        )
    return removed


def _build_exact_overlap_table(con) -> None:
    if not table_exists(con, "core_usage_assignment_segment_movements"):
        return
    if not table_exists(con, "dq_run_metadata"):
        return
    con.execute(
        """
        create or replace temp table tmp_overlap_tolerance_exact_days as
        with intervals as (
            select
                loco_no,
                de_period_start_utc as interval_start_utc,
                de_period_end_utc as interval_end_utc
            from core_usage_assignment_segment_movements
            where nullif(trim(loco_no), '') is not null
              and de_period_start_utc is not null
              and de_period_end_utc is not null
              and de_period_end_utc > de_period_start_utc
              and de_period_start_utc <= (select max(error_cutoff_utc) from dq_run_metadata)
        ), events as (
            select loco_no, interval_start_utc as event_utc, 1::bigint as delta from intervals
            union all
            select loco_no, interval_end_utc as event_utc, -1::bigint as delta from intervals
        ), grouped_events as (
            select loco_no, event_utc, sum(delta) as delta
            from events
            group by loco_no, event_utc
        ), spans as (
            select
                loco_no,
                event_utc as span_start_utc,
                lead(event_utc) over (partition by loco_no order by event_utc) as span_end_utc,
                sum(delta) over (
                    partition by loco_no
                    order by event_utc
                    rows between unbounded preceding and current row
                ) as active_interval_count
            from grouped_events
        ), overlap_spans as (
            select loco_no, span_start_utc, span_end_utc
            from spans
            where active_interval_count > 1
              and span_end_utc is not null
              and span_end_utc > span_start_utc
        ), day_spans as (
            select
                o.loco_no,
                cast(days.day_start_utc as date) as coverage_date,
                greatest(o.span_start_utc, days.day_start_utc) as overlap_start_utc,
                least(o.span_end_utc, days.day_start_utc + interval '1 day') as overlap_end_utc
            from overlap_spans o
            cross join unnest(
                generate_series(
                    date_trunc('day', o.span_start_utc),
                    date_trunc('day', o.span_end_utc - interval '1 microsecond'),
                    interval '1 day'
                )
            ) as days(day_start_utc)
        )
        select
            loco_no,
            coverage_date,
            sum(date_diff('second', overlap_start_utc, overlap_end_utc))::bigint as exact_overlap_seconds
        from day_spans
        where overlap_end_utc > overlap_start_utc
        group by loco_no, coverage_date
        """
    )


def apply_overlap_tolerance_to_quality_gate(con) -> int:
    """Overlap-Gate-Blockaden bis einschliesslich 5 Minuten neutralisieren."""
    if not table_exists(con, "core_loco_day_coverage"):
        return 0

    _build_exact_overlap_table(con)
    if not table_exists(con, "tmp_overlap_tolerance_exact_days"):
        return 0

    short_days = int(
        con.execute(
            f"""
            select count(*)
            from tmp_overlap_tolerance_exact_days
            where exact_overlap_seconds <= {OVERLAP_TOLERANCE_SECONDS}
            """
        ).fetchone()[0]
    )

    if not short_days:
        return 0

    con.execute(
        f"""
        update core_loco_day_coverage as c
        set
            overlap_slot_count = 0,
            overlap_minutes = 0,
            gate_status = case
                when coalesce(error_findings, 0) > 0
                  or coalesce(manual_review_findings, 0) > 0
                  or coalesce(long_gap_rows, 0) > 0
                  or coalesce(not_export_ready_movement_rows, 0) > 0
                  or (
                        coalesce(assignment_slot_count, 0) = 0
                    and coalesce(relevant_gap_slot_count, 0) > 0
                  )
                    then 'BLOCKED'
                when coalesce(relevant_gap_slot_count, 0) > 0
                  or coalesce(warning_findings, 0) > 0
                  or coalesce(info_findings, 0) > 0
                    then 'WARNING'
                else 'READY'
            end,
            gate_reason = concat_ws(
                ' | ',
                case when coalesce(error_findings, 0) > 0
                    then 'ERROR-Findings=' || cast(error_findings as varchar) end,
                case when coalesce(manual_review_findings, 0) > 0
                    then 'Manual Reviews=' || cast(manual_review_findings as varchar) end,
                case when coalesce(long_gap_rows, 0) > 0
                    then 'GAPs über 8h=' || cast(long_gap_rows as varchar) end,
                case when coalesce(not_export_ready_movement_rows, 0) > 0
                    then 'Nicht exportfähige Movements=' || cast(not_export_ready_movement_rows as varchar) end,
                case when coalesce(relevant_gap_slot_count, 0) > 0
                    then 'Ungeklärte GAP-Minuten=' || cast(relevant_gap_slot_count * 15 as varchar) end,
                case when coalesce(info_findings, 0) > 0
                    then 'INFO-Findings=' || cast(info_findings as varchar) end
            )
        from tmp_overlap_tolerance_exact_days s
        where s.loco_no = c.loco_no
          and s.coverage_date = c.coverage_date
          and s.exact_overlap_seconds <= {OVERLAP_TOLERANCE_SECONDS}
        """
    )

    for table_name in ["dq_export_gate", "dq_export_gate_ru"]:
        if not table_exists(con, table_name):
            continue
        con.execute(
            f"""
            update {qident(table_name)} as target
            set
                overlap_minutes = source.overlap_minutes,
                gate_status = source.gate_status,
                gate_reason = source.gate_reason
            from core_loco_day_coverage source
            where target.loco_no = source.loco_no
              and target.coverage_date = source.coverage_date
            """
        )

    print(
        "Overlap-Toleranz aktiv: "
        f"{short_days} Lok-Tag(e) mit Overlap bis einschliesslich 5 Minuten nicht blockierend."
    )
    return short_days


def install_overlap_tolerance_runtime() -> None:
    """Patcht Regelwerk/Gates fuer Pipeline-Laeufe im aktuellen Prozess."""
    global _PATCHED
    if _PATCHED:
        return

    import error_rules
    import quality_gate_module
    import rule_engine_hardening_phase6d

    original_build_findings = error_rules.build_findings
    original_build_quality_gate = quality_gate_module.build_quality_gate_tables
    original_finalize_phase6d = rule_engine_hardening_phase6d.finalize_quality_gate_phase6d

    if not getattr(original_build_findings, "_overlap_tolerance", False):
        def build_findings_with_tolerance(con, run_id: str, home_country_iso: str = "DE") -> None:
            original_build_findings(con, run_id, home_country_iso=home_country_iso)
            apply_overlap_tolerance_to_findings(con)

        build_findings_with_tolerance._overlap_tolerance = True  # type: ignore[attr-defined]
        error_rules.build_findings = build_findings_with_tolerance

    if not getattr(original_build_quality_gate, "_overlap_tolerance", False):
        def build_quality_gate_with_tolerance(con, run_id: str) -> None:
            original_build_quality_gate(con, run_id)
            apply_overlap_tolerance_to_quality_gate(con)

        build_quality_gate_with_tolerance._overlap_tolerance = True  # type: ignore[attr-defined]
        quality_gate_module.build_quality_gate_tables = build_quality_gate_with_tolerance

    if not getattr(original_finalize_phase6d, "_overlap_tolerance", False):
        def finalize_phase6d_with_tolerance(con, run_id: str) -> None:
            original_finalize_phase6d(con, run_id)
            if table_exists(con, "dq_phase6d_exact_overlap_days"):
                con.execute(
                    f"""
                    delete from dq_phase6d_exact_overlap_days
                    where coalesce(exact_overlap_seconds, 0) <= {OVERLAP_TOLERANCE_SECONDS}
                    """
                )
            apply_overlap_tolerance_to_quality_gate(con)

        finalize_phase6d_with_tolerance._overlap_tolerance = True  # type: ignore[attr-defined]
        rule_engine_hardening_phase6d.finalize_quality_gate_phase6d = finalize_phase6d_with_tolerance

    _PATCHED = True
