from __future__ import annotations


PHASE11I_FEEDBACK_RULES_MARKER = "NETZENTGELT_FEEDBACK_RULES_PHASE11I_V1_20260618"


def _qident(value: str) -> str:
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


def _columns(con, table_name: str) -> list[str]:
    if not _table_exists(con, table_name):
        return []
    return [row[0] for row in con.execute(f"describe {_qident(table_name)}").fetchall()]


def _ensure_column(con, table_name: str, column_name: str, data_type: str) -> None:
    existing = {column.lower() for column in _columns(con, table_name)}
    if column_name.lower() not in existing:
        con.execute(f"alter table {_qident(table_name)} add column {_qident(column_name)} {data_type}")


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create table if not exists dq_feedback_rule_adjustments_audit (
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
        insert into dq_feedback_rule_adjustments_audit values (
            ?, ?, ?, ?, current_timestamp, ?
        )
        """,
        [PHASE11I_FEEDBACK_RULES_MARKER, str(run_id), str(metric), int(value or 0), str(comment)],
    )


def _suppress_same_ru_overlaps(con, run_id: str) -> None:
    if not _table_exists(con, "dq_findings") or not _table_exists(con, "core_loco_timeline"):
        return

    before = int(con.execute("select count(*) from dq_findings where rule_id = 'R011'").fetchone()[0])
    con.execute(
        """
        delete from dq_findings as f
        where f.rule_id = 'R011'
          and exists (
                select 1
                from core_loco_timeline b
                where b.row_type = 'MOVEMENT'
                  and b.report_scope = 'IN_REPORT'
                  and b.source_table is not distinct from f.source_table
                  and b.source_row_id is not distinct from f.source_row_id
                  and nullif(trim(b.performing_ru), '') is not null
                  and exists (
                        select 1
                        from core_loco_timeline a
                        where a.row_type = 'MOVEMENT'
                          and a.report_scope = 'IN_REPORT'
                          and a.loco_no is not distinct from b.loco_no
                          and a.period_start_utc < b.period_end_utc
                          and b.period_start_utc < a.period_end_utc
                          and (
                                a.period_start_utc < b.period_start_utc
                             or (
                                    a.period_start_utc = b.period_start_utc
                                and coalesce(a.source_row_id, -1) < coalesce(b.source_row_id, -1)
                             )
                          )
                  )
                  and not exists (
                        select 1
                        from core_loco_timeline a
                        where a.row_type = 'MOVEMENT'
                          and a.report_scope = 'IN_REPORT'
                          and a.loco_no is not distinct from b.loco_no
                          and a.period_start_utc < b.period_end_utc
                          and b.period_start_utc < a.period_end_utc
                          and (
                                a.period_start_utc < b.period_start_utc
                             or (
                                    a.period_start_utc = b.period_start_utc
                                and coalesce(a.source_row_id, -1) < coalesce(b.source_row_id, -1)
                             )
                          )
                          and coalesce(nullif(trim(a.performing_ru), ''), '#')
                              <> coalesce(nullif(trim(b.performing_ru), ''), '#')
                  )
          )
        """
    )
    after = int(con.execute("select count(*) from dq_findings where rule_id = 'R011'").fetchone()[0])
    _audit(
        con,
        run_id,
        "same_ru_overlap_r011_suppressed",
        before - after,
        "R011-Ueberschneidungen mit identischem PerformingRU wurden fachlich ignoriert.",
    )


def _apply_confirmed_cold_stands(con, run_id: str) -> None:
    if not _table_exists(con, "cfg_manual_overrides_effective") or not _table_exists(con, "core_loco_timeline"):
        return

    con.execute(
        """
        create or replace temp table tmp_feedback_confirmed_cold_stands as
        select
            nullif(trim(target_loco_no), '') as loco_no,
            try_cast(nullif(trim(target_actual_departure_utc), '') as timestamp) as period_start_utc,
            try_cast(nullif(trim(target_actual_arrival_utc), '') as timestamp) as period_end_utc,
            nullif(trim(target_source_table), '') as source_table,
            try_cast(nullif(trim(target_source_row_id), '') as bigint) as source_row_id,
            override_id
        from cfg_manual_overrides_effective
        where upper(trim(coalesce(active_flag, 'Y'))) not in ('N', 'NO', 'FALSE', '0')
          and upper(trim(coalesce(override_type, ''))) = 'CLASSIFY_GAP'
          and upper(trim(coalesce(classification_code, ''))) = 'COLD_STAND'
        """
    )
    confirmed = int(con.execute("select count(*) from tmp_feedback_confirmed_cold_stands").fetchone()[0])
    if confirmed == 0:
        _audit(con, run_id, "confirmed_cold_stand_overrides", 0, "Keine aktive Kaltabstellungs-Klassifikation gefunden.")
        return

    con.execute(
        """
        update core_loco_timeline as g
        set
            gap_relevant_de = false,
            needs_manual_review = false,
            dq_severity = 'INFO',
            dq_message = concat_ws(
                ' ',
                'Kalte Abstellung manuell bestätigt.',
                'Keine blockierende GAP-Prüfung mehr.',
                'Ort davor:', coalesce(nullif(trim(g.origin_name), ''), '-'),
                'Ort danach:', coalesce(nullif(trim(g.destination_name), ''), '-')
            ),
            gap_message = concat_ws(
                ' ',
                coalesce(nullif(trim(g.gap_message), ''), 'Unterbrechung der Lok-Zeitachse.'),
                'Ort davor:', coalesce(nullif(trim(g.origin_name), ''), '-'),
                'Ort danach:', coalesce(nullif(trim(g.destination_name), ''), '-'),
                'Kalte Abstellung manuell bestätigt.'
            )
        from tmp_feedback_confirmed_cold_stands c
        where g.row_type = 'GAP'
          and (
                (
                    c.source_table is not null
                and c.source_row_id is not null
                and g.source_table is not distinct from c.source_table
                and g.source_row_id is not distinct from c.source_row_id
                )
             or (
                    c.loco_no is not null
                and g.loco_no is not distinct from c.loco_no
                and c.period_start_utc is not null
                and g.period_start_utc is not distinct from c.period_start_utc
                and (
                        c.period_end_utc is null
                     or g.period_end_utc is not distinct from c.period_end_utc
                )
             )
          )
        """
    )

    if _table_exists(con, "dq_findings"):
        before = int(
            con.execute(
                """
                select count(*)
                from dq_findings f
                where f.rule_id in ('R010', 'R010.5', 'R015', 'R016')
                """
            ).fetchone()[0]
        )
        con.execute(
            """
            delete from dq_findings as f
            where f.rule_id in ('R010', 'R010.5', 'R015', 'R016')
              and exists (
                    select 1
                    from tmp_feedback_confirmed_cold_stands c
                    where (
                            c.source_table is not null
                        and c.source_row_id is not null
                        and f.source_table is not distinct from c.source_table
                        and f.source_row_id is not distinct from c.source_row_id
                    )
                       or (
                            c.loco_no is not null
                        and f.loco_no is not distinct from c.loco_no
                        and c.period_start_utc is not null
                        and f.period_start_utc is not distinct from c.period_start_utc
                        and (
                                c.period_end_utc is null
                             or f.period_end_utc is not distinct from c.period_end_utc
                        )
                    )
                       or (
                            f.rule_id = 'R016'
                        and c.loco_no is not null
                        and f.loco_no is not distinct from c.loco_no
                        and c.period_start_utc is not null
                        and cast(f.period_start_utc as date) = cast(c.period_start_utc as date)
                    )
              )
            """
        )
        after = int(
            con.execute(
                """
                select count(*)
                from dq_findings f
                where f.rule_id in ('R010', 'R010.5', 'R015', 'R016')
                """
            ).fetchone()[0]
        )
        _audit(
            con,
            run_id,
            "cold_stand_gap_findings_removed",
            before - after,
            "Bestaetigte Kaltabstellungen entfernen blockierende GAP-Findings.",
        )

    _audit(
        con,
        run_id,
        "confirmed_cold_stand_overrides",
        confirmed,
        "Aktive CLASSIFY_GAP/COLD_STAND-Overrides wurden auf die Timeline angewandt.",
    )


def _enrich_gap_location_context(con, run_id: str) -> None:
    if not _table_exists(con, "core_loco_timeline"):
        return

    con.execute(
        """
        update core_loco_timeline
        set gap_message = concat_ws(
                ' ',
                coalesce(nullif(trim(gap_message), ''), 'Unterbrechung der Lok-Zeitachse.'),
                'Ort davor:', coalesce(nullif(trim(origin_name), ''), '-'),
                'Ort danach:', coalesce(nullif(trim(destination_name), ''), '-')
            ),
            dq_message = case
                when row_type = 'GAP' then concat_ws(
                    ' ',
                    coalesce(nullif(trim(dq_message), ''), 'Unterbrechung der Lok-Zeitachse.'),
                    'Ort davor:', coalesce(nullif(trim(origin_name), ''), '-'),
                    'Ort danach:', coalesce(nullif(trim(destination_name), ''), '-')
                )
                else dq_message
            end
        where row_type = 'GAP'
          and position('Ort davor:' in coalesce(gap_message, '')) = 0
        """
    )

    if _table_exists(con, "dq_findings"):
        con.execute(
            """
            update dq_findings as f
            set message = concat_ws(
                ' ',
                coalesce(nullif(trim(f.message), ''), 'Unterbrechung der Lok-Zeitachse.'),
                'Ort davor:', coalesce(nullif(trim(g.origin_name), ''), '-'),
                'Ort danach:', coalesce(nullif(trim(g.destination_name), ''), '-')
            )
            from core_loco_timeline g
            where g.row_type = 'GAP'
              and f.loco_no is not distinct from g.loco_no
              and f.source_table is not distinct from g.source_table
              and f.source_row_id is not distinct from g.source_row_id
              and f.rule_id in ('R010', 'R010.5', 'R015', 'R016')
              and position('Ort davor:' in coalesce(f.message, '')) = 0
            """
        )

    _audit(con, run_id, "gap_location_context_enriched", 1, "GAP-Meldungen enthalten Ort davor und Ort danach.")


def _refresh_timeline_quality_flags(con) -> None:
    if not _table_exists(con, "dq_findings") or not _table_exists(con, "core_loco_timeline"):
        return
    con.execute(
        """
        create or replace temp table tmp_feedback_dq_row_summary as
        select
            row_type,
            loco_no,
            transport_number,
            performing_ru,
            period_start_utc,
            period_end_utc,
            source_table,
            source_row_id,
            case
                when count(*) filter (where severity = 'ERROR') > 0 then 'ERROR'
                when count(*) filter (where severity = 'MANUAL_REVIEW') > 0 then 'MANUAL_REVIEW'
                when count(*) filter (where severity = 'WARNING') > 0 then 'WARNING'
                when count(*) filter (where severity = 'INFO') > 0 then 'INFO'
                else ''
            end as dq_severity,
            string_agg(rule_id || ': ' || message, ' | ' order by rule_id, message) as dq_message,
            count(*) filter (where severity in ('ERROR', 'MANUAL_REVIEW')) > 0 as needs_manual_review
        from dq_findings
        group by row_type, loco_no, transport_number, performing_ru, period_start_utc, period_end_utc, source_table, source_row_id
        """
    )
    con.execute(
        """
        update core_loco_timeline
        set
            needs_manual_review = false,
            dq_severity = case when report_scope = 'NOT_IN_REPORT' then 'INFO' else coalesce(nullif(dq_severity, ''), '') end,
            dq_message = case when report_scope = 'NOT_IN_REPORT' then 'Außerhalb DE; Not in the Report.' else coalesce(nullif(dq_message, ''), '') end
        """
    )
    con.execute(
        """
        update core_loco_timeline as c
        set
            needs_manual_review = s.needs_manual_review,
            dq_severity = s.dq_severity,
            dq_message = s.dq_message
        from tmp_feedback_dq_row_summary s
        where c.row_type = s.row_type
          and c.loco_no is not distinct from s.loco_no
          and c.transport_number is not distinct from s.transport_number
          and c.performing_ru is not distinct from s.performing_ru
          and c.period_start_utc is not distinct from s.period_start_utc
          and c.period_end_utc is not distinct from s.period_end_utc
          and c.source_table is not distinct from s.source_table
          and c.source_row_id is not distinct from s.source_row_id
        """
    )


def _refresh_movement_export_flags(con) -> None:
    if not _table_exists(con, "core_loco_timeline"):
        return
    _ensure_column(con, "core_loco_timeline", "export_blocking", "boolean")
    con.execute(
        """
        update core_loco_timeline
        set export_ready = case
            when row_type = 'MOVEMENT'
             and report_scope = 'IN_REPORT'
             and coalesce(needs_manual_review, false) = false
             and sequence_ts is not null
             and period_start_utc is not null
             and period_end_utc is not null
             and period_start_utc <= period_end_utc
             and nullif(trim(loco_no), '') is not null
             and trim(loco_no) <> '00000000000-0'
             and nullif(trim(performing_ru), '') is not null
             and nullif(trim(holder_market_partner_id), '') is not null
                then true
            else false
        end
        """
    )
    con.execute(
        """
        update core_loco_timeline
        set export_blocking = case
            when row_type = 'MOVEMENT'
             and report_scope = 'IN_REPORT'
             and coalesce(export_ready, false) = false
                then true
            else false
        end
        """
    )


def _apply_minute_exact_gate_values(con, run_id: str) -> None:
    if not _table_exists(con, "core_loco_day_coverage"):
        return

    if _table_exists(con, "core_usage_assignment_segments"):
        con.execute(
            """
            create or replace temp table tmp_feedback_exact_assignment_days as
            with day_spans as (
                select
                    s.loco_no,
                    cast(days.day_start_utc as date) as coverage_date,
                    greatest(s.segment_start_utc, days.day_start_utc) as span_start_utc,
                    least(s.segment_end_utc, days.day_start_utc + interval '1 day') as span_end_utc
                from core_usage_assignment_segments s
                cross join unnest(
                    generate_series(
                        date_trunc('day', s.segment_start_utc),
                        date_trunc('day', s.segment_end_utc - interval '1 microsecond'),
                        interval '1 day'
                    )
                ) as days(day_start_utc)
                where s.segment_start_utc is not null
                  and s.segment_end_utc is not null
                  and s.segment_end_utc > s.segment_start_utc
            )
            select
                loco_no,
                coverage_date,
                cast(round(sum(date_diff('second', span_start_utc, span_end_utc)) / 60.0, 0) as bigint) as assigned_minutes_exact
            from day_spans
            where span_end_utc > span_start_utc
            group by loco_no, coverage_date
            """
        )
    else:
        con.execute("create or replace temp table tmp_feedback_exact_assignment_days(loco_no varchar, coverage_date date, assigned_minutes_exact bigint)")

    con.execute(
        """
        create or replace temp table tmp_feedback_exact_gap_days as
        with gap_rows as (
            select *
            from core_loco_timeline
            where row_type = 'GAP'
              and coalesce(gap_relevant_de, false) = true
              and coalesce(gap_time_basis_safe, true) = true
              and nullif(trim(loco_no), '') is not null
              and period_start_utc is not null
              and period_end_utc is not null
              and period_end_utc > period_start_utc
        ), day_spans as (
            select
                g.loco_no,
                cast(days.day_start_utc as date) as coverage_date,
                greatest(g.period_start_utc, days.day_start_utc) as span_start_utc,
                least(g.period_end_utc, days.day_start_utc + interval '1 day') as span_end_utc
            from gap_rows g
            cross join unnest(
                generate_series(
                    date_trunc('day', g.period_start_utc),
                    date_trunc('day', g.period_end_utc - interval '1 microsecond'),
                    interval '1 day'
                )
            ) as days(day_start_utc)
        )
        select
            loco_no,
            coverage_date,
            cast(round(sum(date_diff('second', span_start_utc, span_end_utc)) / 60.0, 0) as bigint) as unresolved_gap_minutes_exact
        from day_spans
        where span_end_utc > span_start_utc
        group by loco_no, coverage_date
        """
    )

    if _table_exists(con, "dq_phase6d_exact_overlap_days"):
        con.execute(
            """
            create or replace temp table tmp_feedback_exact_overlap_days as
            select
                loco_no,
                coverage_date,
                cast(round(coalesce(exact_overlap_seconds, 0) / 60.0, 0) as bigint) as overlap_minutes_exact
            from dq_phase6d_exact_overlap_days
            """
        )
    else:
        con.execute("create or replace temp table tmp_feedback_exact_overlap_days(loco_no varchar, coverage_date date, overlap_minutes_exact bigint)")

    con.execute(
        """
        update core_loco_day_coverage as d
        set
            assigned_minutes = coalesce(a.assigned_minutes_exact, 0),
            unresolved_gap_minutes = coalesce(g.unresolved_gap_minutes_exact, 0),
            overlap_minutes = coalesce(o.overlap_minutes_exact, 0),
            coverage_pct = case
                when coalesce(a.assigned_minutes_exact, 0) + coalesce(g.unresolved_gap_minutes_exact, 0) = 0 then 0::double
                else round(
                    100.0 * coalesce(a.assigned_minutes_exact, 0)
                    / (coalesce(a.assigned_minutes_exact, 0) + coalesce(g.unresolved_gap_minutes_exact, 0)),
                    2
                )
            end,
            gate_status = case
                when coalesce(error_findings, 0) > 0
                  or coalesce(manual_review_findings, 0) > 0
                  or coalesce(o.overlap_minutes_exact, 0) > 0
                  or coalesce(long_gap_rows, 0) > 0
                  or coalesce(not_export_ready_movement_rows, 0) > 0
                  or (coalesce(a.assigned_minutes_exact, 0) = 0 and coalesce(g.unresolved_gap_minutes_exact, 0) > 0)
                    then 'BLOCKED'
                when coalesce(g.unresolved_gap_minutes_exact, 0) > 0
                  or coalesce(warning_findings, 0) > 0
                  or coalesce(info_findings, 0) > 0
                    then 'WARNING'
                else 'READY'
            end,
            gate_reason = concat_ws(
                ' | ',
                case when coalesce(error_findings, 0) > 0 then 'ERROR-Findings=' || cast(error_findings as varchar) end,
                case when coalesce(manual_review_findings, 0) > 0 then 'Manual Reviews=' || cast(manual_review_findings as varchar) end,
                case when coalesce(o.overlap_minutes_exact, 0) > 0 then 'Overlap-Minuten=' || cast(o.overlap_minutes_exact as varchar) end,
                case when coalesce(long_gap_rows, 0) > 0 then 'GAPs über 120 Minuten=' || cast(long_gap_rows as varchar) end,
                case when coalesce(not_export_ready_movement_rows, 0) > 0 then 'Nicht exportfähige Movements=' || cast(not_export_ready_movement_rows as varchar) end,
                case when coalesce(g.unresolved_gap_minutes_exact, 0) > 0 then 'Ungeklärte GAP-Minuten=' || cast(g.unresolved_gap_minutes_exact as varchar) end,
                case when coalesce(info_findings, 0) > 0 then 'INFO-Findings=' || cast(info_findings as varchar) end
            )
        from tmp_feedback_exact_assignment_days a
        full outer join tmp_feedback_exact_gap_days g
          on g.loco_no = a.loco_no and g.coverage_date = a.coverage_date
        full outer join tmp_feedback_exact_overlap_days o
          on o.loco_no = coalesce(a.loco_no, g.loco_no)
         and o.coverage_date = coalesce(a.coverage_date, g.coverage_date)
        where d.loco_no = coalesce(a.loco_no, g.loco_no, o.loco_no)
          and d.coverage_date = coalesce(a.coverage_date, g.coverage_date, o.coverage_date)
        """
    )

    for table_name in ["dq_export_gate", "dq_export_gate_ru"]:
        if not _table_exists(con, table_name):
            continue
        con.execute(
            f"""
            update {_qident(table_name)} as target
            set
                coverage_pct = source.coverage_pct,
                assigned_minutes = source.assigned_minutes,
                unresolved_gap_minutes = source.unresolved_gap_minutes,
                overlap_minutes = source.overlap_minutes,
                gate_status = source.gate_status,
                gate_reason = source.gate_reason,
                error_findings = source.error_findings,
                manual_review_findings = source.manual_review_findings,
                warning_findings = source.warning_findings,
                info_findings = source.info_findings,
                long_gap_rows = source.long_gap_rows,
                not_export_ready_movement_rows = source.not_export_ready_movement_rows
            from core_loco_day_coverage source
            where target.loco_no is not distinct from source.loco_no
              and target.coverage_date is not distinct from source.coverage_date
            """
        )

    _audit(con, run_id, "minute_exact_gate_values_applied", 1, "Gate-Minuten wurden auf echte Minutensummen statt 15-Minuten-Slots nachgezogen.")


def apply_feedback_rule_adjustments_phase11i(con, run_id: str) -> None:
    """Apply operator feedback after the standard rule engine and before export."""
    _suppress_same_ru_overlaps(con, run_id)
    _apply_confirmed_cold_stands(con, run_id)
    _enrich_gap_location_context(con, run_id)
    _refresh_timeline_quality_flags(con)
    _refresh_movement_export_flags(con)
    _apply_minute_exact_gate_values(con, run_id)
    print("Phase 11I aktiv: Feedback-Regeln fuer Overlaps, Kaltabstellung, Orte und Minutenwerte angewandt. vEns ist keine Export-Sperre mehr.")
