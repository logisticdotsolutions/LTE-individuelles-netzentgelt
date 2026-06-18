from __future__ import annotations


OVERLAP_POLICY_MARKER = "NETZENTGELT_OVERLAP_POLICY_DIFF_EVU_ONLY_PHASE11N_V1_20260618"


def _table_exists(con, table_name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
        [table_name],
    ).fetchone()[0] > 0


def _columns(con, table_name: str) -> set[str]:
    if not _table_exists(con, table_name):
        return set()
    return {row[0].lower() for row in con.execute(f'describe "{table_name}"').fetchall()}


def _ensure_audit(con) -> None:
    con.execute(
        """
        create table if not exists dq_overlap_policy_audit (
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
    _ensure_audit(con)
    con.execute(
        """
        insert into dq_overlap_policy_audit values (?, ?, ?, ?, current_timestamp, ?)
        """,
        [OVERLAP_POLICY_MARKER, str(run_id), str(metric), int(value or 0), str(comment)],
    )


def _delete_non_relevant_r011(con, run_id: str) -> None:
    if not _table_exists(con, "dq_findings") or not _table_exists(con, "core_loco_timeline"):
        return
    before = con.execute("select count(*) from dq_findings where rule_id = 'R011'").fetchone()[0]
    con.execute(
        """
        delete from dq_findings as f
        where f.rule_id = 'R011'
          and not exists (
                select 1
                from core_loco_timeline b
                join core_loco_timeline a
                  on a.row_type = 'MOVEMENT'
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
                 and nullif(trim(a.performing_ru), '') is not null
                 and nullif(trim(b.performing_ru), '') is not null
                 and trim(a.performing_ru) <> trim(b.performing_ru)
                where b.row_type = 'MOVEMENT'
                  and b.report_scope = 'IN_REPORT'
                  and b.source_table is not distinct from f.source_table
                  and b.source_row_id is not distinct from f.source_row_id
          )
        """
    )
    after = con.execute("select count(*) from dq_findings where rule_id = 'R011'").fetchone()[0]
    _audit(
        con,
        run_id,
        "r011_same_evu_or_incomplete_removed",
        before - after,
        "R011 bleibt nur fuer echte Ueberschneidung mit anderem nicht-leerem EVU bestehen.",
    )


def _rebuild_diff_evu_overlap_days(con, run_id: str) -> None:
    if not _table_exists(con, "core_usage_assignment_segment_movements") or not _table_exists(con, "dq_run_metadata"):
        return
    con.execute(
        """
        create or replace table dq_phase6d_exact_overlap_days as
        with intervals as (
            select
                row_number() over (order by loco_no, de_period_start_utc, de_period_end_utc, source_row_id) as interval_id,
                loco_no,
                nullif(trim(performing_ru), '') as performing_ru,
                de_period_start_utc as interval_start_utc,
                de_period_end_utc as interval_end_utc
            from core_usage_assignment_segment_movements
            where nullif(trim(loco_no), '') is not null
              and nullif(trim(performing_ru), '') is not null
              and de_period_start_utc is not null
              and de_period_end_utc is not null
              and de_period_end_utc > de_period_start_utc
              and de_period_start_utc <= (select max(error_cutoff_utc) from dq_run_metadata)
        ), pairs as (
            select
                a.loco_no,
                greatest(a.interval_start_utc, b.interval_start_utc) as overlap_start_utc,
                least(a.interval_end_utc, b.interval_end_utc) as overlap_end_utc
            from intervals a
            join intervals b
              on b.loco_no = a.loco_no
             and b.interval_id > a.interval_id
             and a.interval_start_utc < b.interval_end_utc
             and b.interval_start_utc < a.interval_end_utc
             and trim(a.performing_ru) <> trim(b.performing_ru)
        ), day_spans as (
            select
                p.loco_no,
                cast(days.day_start_utc as date) as coverage_date,
                greatest(p.overlap_start_utc, days.day_start_utc) as overlap_start_utc,
                least(p.overlap_end_utc, days.day_start_utc + interval '1 day') as overlap_end_utc
            from pairs p
            cross join unnest(
                generate_series(
                    date_trunc('day', p.overlap_start_utc),
                    date_trunc('day', p.overlap_end_utc - interval '1 microsecond'),
                    interval '1 day'
                )
            ) as days(day_start_utc)
            where p.overlap_end_utc > p.overlap_start_utc
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
    count_days = con.execute("select count(*) from dq_phase6d_exact_overlap_days").fetchone()[0]
    _audit(
        con,
        run_id,
        "diff_evu_overlap_loco_days",
        count_days,
        "Overlap-Minuten werden nur fuer Ueberschneidungen mit anderem nicht-leerem EVU gezaehlt.",
    )


def _apply_overlap_minutes_to_gate(con) -> None:
    if not _table_exists(con, "dq_phase6d_exact_overlap_days"):
        return
    for table_name in ["core_loco_day_coverage", "dq_export_gate", "dq_export_gate_ru"]:
        if not _table_exists(con, table_name):
            continue
        cols = _columns(con, table_name)
        if "overlap_minutes" not in cols:
            continue
        con.execute(
            f"""
            update "{table_name}"
            set overlap_minutes = 0
            """
        )
        con.execute(
            f"""
            update "{table_name}" as target
            set overlap_minutes = cast(round(source.exact_overlap_minutes, 0) as bigint)
            from dq_phase6d_exact_overlap_days source
            where target.loco_no is not distinct from source.loco_no
              and target.coverage_date is not distinct from source.coverage_date
            """
        )
        if "exact_overlap_seconds" in cols and "exact_overlap_minutes" in cols:
            con.execute(
                f"""
                update "{table_name}"
                set exact_overlap_seconds = 0,
                    exact_overlap_minutes = 0.0
                """
            )
            con.execute(
                f"""
                update "{table_name}" as target
                set exact_overlap_seconds = source.exact_overlap_seconds,
                    exact_overlap_minutes = source.exact_overlap_minutes
                from dq_phase6d_exact_overlap_days source
                where target.loco_no is not distinct from source.loco_no
                  and target.coverage_date is not distinct from source.coverage_date
                """
            )
        if {"gate_status", "gate_reason"}.issubset(cols):
            con.execute(
                f"""
                update "{table_name}"
                set gate_status = case
                    when coalesce(error_findings, 0) > 0
                      or coalesce(manual_review_findings, 0) > 0
                      or coalesce(overlap_minutes, 0) > 0
                      or coalesce(long_gap_rows, 0) > 0
                      or coalesce(not_export_ready_movement_rows, 0) > 0
                      or (coalesce(assigned_minutes, 0) = 0 and coalesce(unresolved_gap_minutes, 0) > 0)
                        then 'BLOCKED'
                    when coalesce(unresolved_gap_minutes, 0) > 0
                      or coalesce(warning_findings, 0) > 0
                      or coalesce(info_findings, 0) > 0
                        then 'WARNING'
                    else 'READY'
                end,
                gate_reason = concat_ws(
                    ' | ',
                    case when coalesce(error_findings, 0) > 0 then 'ERROR-Findings=' || cast(error_findings as varchar) end,
                    case when coalesce(manual_review_findings, 0) > 0 then 'Manual Reviews=' || cast(manual_review_findings as varchar) end,
                    case when coalesce(overlap_minutes, 0) > 0 then 'Overlap-Minuten=' || cast(overlap_minutes as varchar) end,
                    case when coalesce(long_gap_rows, 0) > 0 then 'GAPs über 120 Minuten=' || cast(long_gap_rows as varchar) end,
                    case when coalesce(not_export_ready_movement_rows, 0) > 0 then 'Nicht exportfähige Movements=' || cast(not_export_ready_movement_rows as varchar) end,
                    case when coalesce(unresolved_gap_minutes, 0) > 0 then 'Ungeklärte GAP-Minuten=' || cast(unresolved_gap_minutes as varchar) end,
                    case when coalesce(info_findings, 0) > 0 then 'INFO-Findings=' || cast(info_findings as varchar) end
                )
                """
            )


def apply_overlap_policy_diff_evu_only(con, run_id: str) -> None:
    """Same-EVU overlaps have no report impact; only different-EVU overlaps remain relevant."""
    _delete_non_relevant_r011(con, run_id)
    _rebuild_diff_evu_overlap_days(con, run_id)
    _apply_overlap_minutes_to_gate(con)
    _audit(con, run_id, "overlap_policy_applied", 1, "Same-EVU-Ueberschneidungen komplett ignoriert; nur anderes EVU bleibt reportrelevant.")
