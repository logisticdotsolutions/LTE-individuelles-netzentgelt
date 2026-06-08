from __future__ import annotations

"""
Netzentgelt MVP - Rule Engine Hardening Phase 6D
================================================

Kleine Nachschaerfung fuer die nach Phase 6C verbleibenden operativen Themen:

- sichtbarer R016-Prueffall fuer Lok-Tage mit ausschliesslich ungeklärter GAP-Zeit,
- exakte Ueberschneidungsdauer zusaetzlich zur konservativen 15-Minuten-Slotzahl,
- auditierbare Phase-6D-Kennzahlen.

Die Schicht veraendert keine Rohdaten. Sie wird nach dem ersten Aufbau des
Quality Gates ausgefuehrt. Danach wird das Quality Gate einmal neu aufgebaut,
damit R016 in der Tagesampel sichtbar ist.
"""

PHASE_ID = "NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6D_V1_20260608"


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


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create table if not exists dq_rule_engine_hardening_phase6d_audit (
            phase_id varchar,
            run_id varchar,
            metric varchar,
            metric_value bigint,
            calculated_at_utc timestamp,
            comment varchar
        )
        """
    )


def _audit(con, run_id: str, metric: str, value: int, comment: str) -> None:
    _ensure_audit_table(con)
    con.execute(
        """
        insert into dq_rule_engine_hardening_phase6d_audit values (
            ?, ?, ?, ?, current_timestamp, ?
        )
        """,
        [PHASE_ID, str(run_id), str(metric), int(value or 0), str(comment)],
    )


def insert_gap_only_day_findings_phase6d(con, run_id: str) -> None:
    """R016 fuer bisher unsichtbar blockierte GAP-only-Lok-Tage einfuegen."""
    required = ["dq_export_gate", "dq_findings", "cfg_dq_rule_catalog"]
    missing = [name for name in required if not table_exists(con, name)]
    if missing:
        raise RuntimeError(
            "Phase 6D kann R016 nicht erzeugen. Fehlende Tabellen: " + ", ".join(missing)
        )

    con.execute("delete from dq_findings where rule_id = 'R016'")
    con.execute(
        """
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        select
            ?::varchar,
            'MANUAL_REVIEW'::varchar,
            'R016'::varchar,
            'TIMELINE'::varchar,
            loco_no,
            null::varchar,
            null::varchar,
            'GAP_DAY'::varchar,
            null::bigint,
            cast(coverage_date as timestamp),
            cast(coverage_date as timestamp) + interval '1 day',
            'Für diesen Lok-Tag liegt ausschließlich ungeklärte Unterbrechungszeit vor. Eine belastbare Nutzung konnte nicht abgeleitet werden.'::varchar,
            'Lok-Zeitachse und Ortskette prüfen. Fehlende RailCube-Daten ergänzen oder den Fall fachlich bewerten.'::varchar,
            'open'::varchar,
            'dq_export_gate'::varchar,
            null::bigint,
            null::varchar
        from dq_export_gate
        where gate_status = 'BLOCKED'
          and coalesce(assigned_minutes, 0) = 0
          and coalesce(unresolved_gap_minutes, 0) > 0
          and coalesce(error_findings, 0) = 0
          and coalesce(manual_review_findings, 0) = 0
          and coalesce(overlap_minutes, 0) = 0
          and coalesce(long_gap_rows, 0) = 0
        """,
        [str(run_id)],
    )

    con.execute("delete from cfg_dq_rule_catalog where rule_id = 'R016'")
    con.execute(
        """
        insert into cfg_dq_rule_catalog values (
            'R016',
            'TIMELINE',
            'MANUAL_REVIEW',
            'Lok-Tag enthält ausschließlich ungeklärte Unterbrechungszeit. Eine belastbare Nutzung konnte nicht abgeleitet werden.',
            true
        )
        """
    )

    count_r016 = int(
        con.execute("select count(*) from dq_findings where rule_id = 'R016'").fetchone()[0]
    )
    _audit(
        con,
        run_id,
        "r016_gap_only_day_findings",
        count_r016,
        "GAP-only-Lok-Tage erhalten einen sichtbaren MANUAL_REVIEW-Prueffall.",
    )
    print(f"Phase 6D: sichtbare R016-GAP-only-Prueffaelle={count_r016}")


def _build_exact_overlap_day_table(con, run_id: str) -> None:
    if not table_exists(con, "core_usage_assignment_segment_movements"):
        raise RuntimeError(
            "core_usage_assignment_segment_movements fehlt. Phase 6C muss vor Phase 6D aktiv sein."
        )
    if not table_exists(con, "dq_run_metadata"):
        raise RuntimeError("dq_run_metadata fehlt. Phase 6D kann den 24h-Cutoff nicht anwenden.")

    con.execute(
        """
        create or replace table dq_phase6d_exact_overlap_days as
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
            ?::varchar as run_id,
            loco_no,
            coverage_date,
            sum(date_diff('second', overlap_start_utc, overlap_end_utc))::bigint as exact_overlap_seconds,
            round(sum(date_diff('second', overlap_start_utc, overlap_end_utc)) / 60.0, 2) as exact_overlap_minutes,
            count(*)::bigint as overlap_span_count
        from day_spans
        where overlap_end_utc > overlap_start_utc
        group by loco_no, coverage_date
        order by coverage_date desc, loco_no
        """,
        [str(run_id)],
    )


def _add_exact_overlap_columns(con, table_name: str) -> None:
    if not table_exists(con, table_name):
        return
    _ensure_column(con, table_name, "exact_overlap_seconds", "bigint")
    _ensure_column(con, table_name, "exact_overlap_minutes", "double")
    con.execute(
        f"""
        update {qident(table_name)}
        set exact_overlap_seconds = 0,
            exact_overlap_minutes = 0.0
        """
    )
    con.execute(
        f"""
        update {qident(table_name)} as target
        set
            exact_overlap_seconds = source.exact_overlap_seconds,
            exact_overlap_minutes = source.exact_overlap_minutes
        from dq_phase6d_exact_overlap_days source
        where source.loco_no = target.loco_no
          and source.coverage_date = target.coverage_date
        """
    )


def _append_exact_overlap_reason(con, table_name: str) -> None:
    if not table_exists(con, table_name):
        return
    existing = {column.lower() for column in columns(con, table_name)}
    if "gate_reason" not in existing:
        return
    con.execute(
        f"""
        update {qident(table_name)}
        set gate_reason = concat_ws(
            ' | ',
            nullif(trim(coalesce(gate_reason, '')), ''),
            case
                when coalesce(exact_overlap_seconds, 0) > 0
                    then 'Tatsaechliche Ueberschneidung=' || cast(round(exact_overlap_minutes, 2) as varchar) || ' Minuten'
                else null
            end
        )
        where coalesce(exact_overlap_seconds, 0) > 0
          and position('Tatsaechliche Ueberschneidung=' in coalesce(gate_reason, '')) = 0
        """
    )


def finalize_quality_gate_phase6d(con, run_id: str) -> None:
    """Exakte Overlap-Dauer in Audit- und Gate-Tabellen ergänzen."""
    _build_exact_overlap_day_table(con, run_id)
    for table_name in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        _add_exact_overlap_columns(con, table_name)
        _append_exact_overlap_reason(con, table_name)

    exact_days = int(
        con.execute("select count(*) from dq_phase6d_exact_overlap_days").fetchone()[0]
    )
    total_seconds = int(
        con.execute(
            "select coalesce(sum(exact_overlap_seconds), 0) from dq_phase6d_exact_overlap_days"
        ).fetchone()[0]
    )
    _audit(
        con,
        run_id,
        "exact_overlap_loco_days",
        exact_days,
        "Lok-Tage mit tatsaechlicher Ueberschneidungsdauer zusaetzlich zur Slotzahl.",
    )
    _audit(
        con,
        run_id,
        "exact_overlap_seconds_total",
        total_seconds,
        "Tatsaechliche Ueberschneidungsdauer in Sekunden ohne Slot-Rundung.",
    )
    print(
        "Phase 6D aktiv: R016 sichtbar, exakte Overlap-Dauer ergänzt. "
        f"Overlap-Lok-Tage={exact_days} | Sekunden={total_seconds}"
    )
