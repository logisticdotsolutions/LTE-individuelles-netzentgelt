"""
Netzentgelt MVP - Quality Gate und operative KPIs
=================================================

Diese Phase-2-Erweiterung ergänzt die bestehende Lok-Zeitachse um eine
rechnerische Kontrollschicht. Sie ersetzt weder die Timeline noch das zentrale
Regelwerk. Stattdessen verdichtet sie beide Quellen in auditierbare Tabellen:

- core_loco_day_coverage:     15-Minuten-Deckung je Lok und Kalendertag
- dq_export_gate:             fachliche Freigabe je Lok und Kalendertag
- dq_export_gate_ru:          Export-Gate je Lok, Tag und PerformingRU
- dq_global_export_blockers:  nicht lokbezogene Blocker, insbesondere R012
- export_excluded_rows:       Bewegungen, die bewusst nicht exportiert werden
- dq_reconciliation:          Mengenabgleich des Pipeline-Laufs
- dq_operational_kpis:        Betriebsampel für die Streamlit-Oberfläche

Fachliche Annahme des MVP
-------------------------
Die rechnerische Zeitdeckung bezieht sich auf die aus RailCube ableitbaren,
ununterbrochenen Nutzungssegmente. Eine GAP-Zeile beendet ein Segment. Ein
Wechsel der PerformingRU beendet ein Segment ebenfalls. Die Berechnung erfolgt
15-minutenscharf, damit sie mit der späteren Zuordnung-Meldetag-Logik kompatibel
ist. Sie ist eine prüfbare MVP-Kontrollschicht, aber noch keine AS4-/XML-
Marktkommunikation.
"""

from __future__ import annotations

from datetime import datetime, timezone


QUALITY_GATE_MARKER = "NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607"
BLOCKING_SEVERITIES = ("ERROR", "MANUAL_REVIEW")


def table_exists(con, table_name: str) -> bool:
    """Prüfen, ob eine DuckDB-Tabelle existiert."""
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


def _count(con, table_name: str, where_sql: str | None = None) -> int:
    """Defensiven Tabellenzähler liefern."""
    if not table_exists(con, table_name):
        return 0

    sql = f'select count(*) from "{table_name}"'

    if where_sql:
        sql += f" where {where_sql}"

    return int(con.execute(sql).fetchone()[0])


def _require_tables(con, table_names: list[str]) -> None:
    """Fehlende technische Voraussetzungen früh und verständlich melden."""
    missing = [name for name in table_names if not table_exists(con, name)]

    if missing:
        raise RuntimeError(
            "Quality Gate kann nicht aufgebaut werden. Fehlende Tabellen: "
            + ", ".join(sorted(missing))
        )


def build_quality_gate_tables(con, run_id: str) -> None:
    """
    Auditierbare 15-Minuten-Zeitdeckung und Export-Gates aufbauen.

    Der Gate-Status folgt bewusst einer konservativen Reihenfolge:
    - BLOCKED: offene ERROR-/MANUAL_REVIEW-Findings, Overlap, GAP > 8h,
               nicht exportfähige Bewegungen oder ausschließlich GAP-Zeit
    - WARNING: kurze relevante GAPs oder reine INFO-/WARNING-Findings
    - READY:   keine der genannten Auffälligkeiten
    """
    _require_tables(
        con,
        [
            "core_loco_timeline",
            "dq_findings",
            "dq_run_metadata",
        ],
    )

    run_id_text = str(run_id)

    # ------------------------------------------------------------------
    # 1. Nutzungssegmente aus der bereits vorhandenen Timeline ableiten.
    # ------------------------------------------------------------------
    con.execute(
        """
        create or replace temp table tmp_qg_usage_segments as
        with ordered as (
            select
                c.*,
                lag(row_type) over (
                    partition by loco_no
                    order by
                        sort_sequence asc,
                        case when row_type = 'MOVEMENT' then 0 else 1 end,
                        source_row_id asc
                ) as previous_row_type,
                lag(performing_ru) over (
                    partition by loco_no
                    order by
                        sort_sequence asc,
                        case when row_type = 'MOVEMENT' then 0 else 1 end,
                        source_row_id asc
                ) as previous_performing_ru
            from core_loco_timeline c
            where nullif(trim(loco_no), '') is not null
        ),
        marked as (
            select
                *,
                case
                    when row_type <> 'MOVEMENT' then 0
                    when previous_row_type is null then 1
                    when previous_row_type = 'GAP' then 1
                    when previous_performing_ru is distinct from performing_ru then 1
                    else 0
                end as starts_new_usage_segment
            from ordered
        ),
        segmented as (
            select
                *,
                sum(starts_new_usage_segment) over (
                    partition by loco_no
                    order by
                        sort_sequence asc,
                        case when row_type = 'MOVEMENT' then 0 else 1 end,
                        source_row_id asc
                    rows between unbounded preceding and current row
                ) as usage_segment_no
            from marked
        )
        select
            loco_no,
            performing_ru,
            usage_segment_no,
            min(actual_departure_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_departure_ts is not null
            ) as segment_start_utc,
            max(actual_arrival_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_arrival_ts is not null
            ) as segment_end_utc,
            count(*) filter (
                where row_type = 'MOVEMENT'
                  and report_scope = 'IN_REPORT'
            ) as in_report_movement_rows,
            count(*) filter (
                where row_type = 'MOVEMENT'
                  and report_scope = 'IN_REPORT'
                  and coalesce(export_ready, false) = false
            ) as not_export_ready_movement_rows
        from segmented
        group by
            loco_no,
            performing_ru,
            usage_segment_no
        having count(*) filter (
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
        ) > 0
           and min(actual_departure_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_departure_ts is not null
           ) is not null
           and max(actual_arrival_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_arrival_ts is not null
           ) is not null
           and max(actual_arrival_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_arrival_ts is not null
           ) > min(actual_departure_ts) filter (
                where row_type = 'MOVEMENT'
                  and actual_departure_ts is not null
           )
        """
    )

    # ------------------------------------------------------------------
    # 2. 15-Minuten-Slots für Nutzungssegmente, Movements und GAPs.
    # ------------------------------------------------------------------
    con.execute(
        """
        create or replace temp table tmp_qg_assignment_slots as
        select
            s.loco_no,
            s.performing_ru,
            s.usage_segment_no,
            slots.slot_start_utc,
            slots.slot_start_utc + interval '15 minutes' as slot_end_utc,
            cast(slots.slot_start_utc as date) as coverage_date
        from tmp_qg_usage_segments s
        cross join unnest(
            generate_series(
                date_trunc('hour', s.segment_start_utc)
                    + cast(floor(date_part('minute', s.segment_start_utc) / 15) as bigint)
                      * interval '15 minutes',
                s.segment_end_utc - interval '1 microsecond',
                interval '15 minutes'
            )
        ) as slots(slot_start_utc)
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_movement_slots as
        select
            c.loco_no,
            c.source_table,
            c.source_row_id,
            slots.slot_start_utc,
            cast(slots.slot_start_utc as date) as coverage_date
        from core_loco_timeline c
        cross join unnest(
            generate_series(
                date_trunc('hour', c.period_start_utc)
                    + cast(floor(date_part('minute', c.period_start_utc) / 15) as bigint)
                      * interval '15 minutes',
                c.period_end_utc - interval '1 microsecond',
                interval '15 minutes'
            )
        ) as slots(slot_start_utc)
        where c.row_type = 'MOVEMENT'
          and c.report_scope = 'IN_REPORT'
          and nullif(trim(c.loco_no), '') is not null
          and c.period_start_utc is not null
          and c.period_end_utc is not null
          and c.period_end_utc > c.period_start_utc
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_gap_slots as
        select
            c.loco_no,
            c.source_table,
            c.source_row_id,
            slots.slot_start_utc,
            cast(slots.slot_start_utc as date) as coverage_date
        from core_loco_timeline c
        cross join unnest(
            generate_series(
                date_trunc('hour', c.period_start_utc)
                    + cast(floor(date_part('minute', c.period_start_utc) / 15) as bigint)
                      * interval '15 minutes',
                c.period_end_utc - interval '1 microsecond',
                interval '15 minutes'
            )
        ) as slots(slot_start_utc)
        where c.row_type = 'GAP'
          and coalesce(c.gap_relevant_de, false) = true
          and nullif(trim(c.loco_no), '') is not null
          and c.period_start_utc is not null
          and c.period_end_utc is not null
          and c.period_end_utc > c.period_start_utc
        """
    )

    # ------------------------------------------------------------------
    # 3. Tagesaggregate bilden.
    # ------------------------------------------------------------------
    con.execute(
        """
        create or replace temp table tmp_qg_day_assignment as
        select
            loco_no,
            coverage_date,
            count(distinct slot_start_utc) as assignment_slot_count,
            count(distinct nullif(trim(performing_ru), '')) as performing_ru_count,
            string_agg(
                distinct nullif(trim(performing_ru), ''),
                ' | '
            ) filter (where nullif(trim(performing_ru), '') is not null)
                as performing_rus
        from tmp_qg_assignment_slots
        group by loco_no, coverage_date
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_day_gap as
        select
            s.loco_no,
            s.coverage_date,
            count(distinct s.slot_start_utc) as relevant_gap_slot_count,
            count(distinct c.source_table || ':' || cast(c.source_row_id as varchar))
                as relevant_gap_rows,
            count(distinct case
                when coalesce(c.gap_duration_minutes, 0) > 480
                    then c.source_table || ':' || cast(c.source_row_id as varchar)
                else null
            end) as long_gap_rows,
            max(coalesce(c.gap_duration_minutes, 0)) as max_gap_minutes
        from tmp_qg_gap_slots s
        join core_loco_timeline c
          on c.row_type = 'GAP'
         and c.source_table is not distinct from s.source_table
         and c.source_row_id is not distinct from s.source_row_id
        group by s.loco_no, s.coverage_date
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_day_overlap as
        with duplicate_slots as (
            select
                loco_no,
                coverage_date,
                slot_start_utc
            from tmp_qg_movement_slots
            group by loco_no, coverage_date, slot_start_utc
            having count(distinct source_table || ':' || cast(source_row_id as varchar)) > 1
        )
        select
            loco_no,
            coverage_date,
            count(*) as overlap_slot_count
        from duplicate_slots
        group by loco_no, coverage_date
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_day_findings as
        select
            loco_no,
            cast(coalesce(period_start_utc, period_end_utc) as date) as coverage_date,
            count(*) filter (where severity = 'ERROR') as error_findings,
            count(*) filter (where severity = 'MANUAL_REVIEW') as manual_review_findings,
            count(*) filter (where severity = 'WARNING') as warning_findings,
            count(*) filter (where severity = 'INFO') as info_findings,
            string_agg(distinct rule_id, ', ') as finding_rule_ids
        from dq_findings
        where nullif(trim(loco_no), '') is not null
          and coalesce(period_start_utc, period_end_utc) is not null
        group by
            loco_no,
            cast(coalesce(period_start_utc, period_end_utc) as date)
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_day_movement as
        select
            loco_no,
            cast(
                coalesce(
                    actual_departure_ts,
                    period_start_utc,
                    sequence_ts,
                    actual_arrival_ts,
                    period_end_utc
                ) as date
            ) as coverage_date,
            count(*) as in_report_movement_rows,
            count(*) filter (where coalesce(export_ready, false) = true)
                as export_ready_movement_rows,
            count(*) filter (where coalesce(export_ready, false) = false)
                as not_export_ready_movement_rows
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and nullif(trim(loco_no), '') is not null
          and coalesce(
                actual_departure_ts,
                period_start_utc,
                sequence_ts,
                actual_arrival_ts,
                period_end_utc
              ) is not null
        group by
            loco_no,
            cast(
                coalesce(
                    actual_departure_ts,
                    period_start_utc,
                    sequence_ts,
                    actual_arrival_ts,
                    period_end_utc
                ) as date
            )
        """
    )

    con.execute(
        """
        create or replace temp table tmp_qg_loco_days as
        select loco_no, coverage_date from tmp_qg_day_assignment
        union
        select loco_no, coverage_date from tmp_qg_day_gap
        union
        select loco_no, coverage_date from tmp_qg_day_overlap
        union
        select loco_no, coverage_date from tmp_qg_day_findings
        union
        select loco_no, coverage_date from tmp_qg_day_movement
        """
    )

    con.execute(
        """
        create or replace table core_loco_day_coverage as
        select
            ?::varchar as run_id,
            d.loco_no,
            d.coverage_date,
            coalesce(a.performing_rus, '') as performing_rus,
            coalesce(a.performing_ru_count, 0) as performing_ru_count,
            coalesce(m.in_report_movement_rows, 0) as in_report_movement_rows,
            coalesce(a.assignment_slot_count, 0) as assignment_slot_count,
            coalesce(a.assignment_slot_count, 0) * 15 as assigned_minutes,
            coalesce(g.relevant_gap_slot_count, 0) as relevant_gap_slot_count,
            coalesce(g.relevant_gap_slot_count, 0) * 15 as unresolved_gap_minutes,
            coalesce(o.overlap_slot_count, 0) as overlap_slot_count,
            coalesce(o.overlap_slot_count, 0) * 15 as overlap_minutes,
            coalesce(a.assignment_slot_count, 0)
                + coalesce(g.relevant_gap_slot_count, 0)
                as expected_scope_slot_count,
            case
                when coalesce(a.assignment_slot_count, 0)
                   + coalesce(g.relevant_gap_slot_count, 0) = 0
                    then 0::double
                else round(
                    100.0 * coalesce(a.assignment_slot_count, 0)
                    / (
                        coalesce(a.assignment_slot_count, 0)
                        + coalesce(g.relevant_gap_slot_count, 0)
                    ),
                    2
                )
            end as coverage_pct,
            coalesce(g.relevant_gap_rows, 0) as relevant_gap_rows,
            coalesce(g.long_gap_rows, 0) as long_gap_rows,
            coalesce(g.max_gap_minutes, 0) as max_gap_minutes,
            coalesce(f.error_findings, 0) as error_findings,
            coalesce(f.manual_review_findings, 0) as manual_review_findings,
            coalesce(f.warning_findings, 0) as warning_findings,
            coalesce(f.info_findings, 0) as info_findings,
            coalesce(f.finding_rule_ids, '') as finding_rule_ids,
            coalesce(m.export_ready_movement_rows, 0) as export_ready_movement_rows,
            coalesce(m.not_export_ready_movement_rows, 0) as not_export_ready_movement_rows,
            case
                when coalesce(f.error_findings, 0) > 0
                  or coalesce(f.manual_review_findings, 0) > 0
                  or coalesce(o.overlap_slot_count, 0) > 0
                  or coalesce(g.long_gap_rows, 0) > 0
                  or coalesce(m.not_export_ready_movement_rows, 0) > 0
                  or (
                        coalesce(a.assignment_slot_count, 0) = 0
                    and coalesce(g.relevant_gap_slot_count, 0) > 0
                  )
                    then 'BLOCKED'
                when coalesce(g.relevant_gap_slot_count, 0) > 0
                  or coalesce(f.warning_findings, 0) > 0
                  or coalesce(f.info_findings, 0) > 0
                    then 'WARNING'
                else 'READY'
            end as gate_status,
            concat_ws(
                ' | ',
                case when coalesce(f.error_findings, 0) > 0
                    then 'ERROR-Findings=' || cast(f.error_findings as varchar) end,
                case when coalesce(f.manual_review_findings, 0) > 0
                    then 'Manual Reviews=' || cast(f.manual_review_findings as varchar) end,
                case when coalesce(o.overlap_slot_count, 0) > 0
                    then 'Overlap-Minuten=' || cast(o.overlap_slot_count * 15 as varchar) end,
                case when coalesce(g.long_gap_rows, 0) > 0
                    then 'GAPs über 8h=' || cast(g.long_gap_rows as varchar) end,
                case when coalesce(m.not_export_ready_movement_rows, 0) > 0
                    then 'Nicht exportfähige Movements=' || cast(m.not_export_ready_movement_rows as varchar) end,
                case when coalesce(g.relevant_gap_slot_count, 0) > 0
                    then 'Ungeklärte GAP-Minuten=' || cast(g.relevant_gap_slot_count * 15 as varchar) end,
                case when coalesce(f.info_findings, 0) > 0
                    then 'INFO-Findings=' || cast(f.info_findings as varchar) end
            ) as gate_reason
        from tmp_qg_loco_days d
        left join tmp_qg_day_assignment a
          on a.loco_no = d.loco_no
         and a.coverage_date = d.coverage_date
        left join tmp_qg_day_gap g
          on g.loco_no = d.loco_no
         and g.coverage_date = d.coverage_date
        left join tmp_qg_day_overlap o
          on o.loco_no = d.loco_no
         and o.coverage_date = d.coverage_date
        left join tmp_qg_day_findings f
          on f.loco_no = d.loco_no
         and f.coverage_date = d.coverage_date
        left join tmp_qg_day_movement m
          on m.loco_no = d.loco_no
         and m.coverage_date = d.coverage_date
        order by d.coverage_date desc, d.loco_no asc
        """,
        [run_id_text],
    )

    # ------------------------------------------------------------------
    # 4. Export-Gates je Lok/Tag sowie je Lok/Tag/RU.
    # ------------------------------------------------------------------
    con.execute(
        """
        create or replace table dq_export_gate as
        select
            run_id,
            loco_no,
            coverage_date,
            performing_rus,
            performing_ru_count,
            coverage_pct,
            assigned_minutes,
            unresolved_gap_minutes,
            overlap_minutes,
            relevant_gap_rows,
            long_gap_rows,
            error_findings,
            manual_review_findings,
            warning_findings,
            info_findings,
            export_ready_movement_rows,
            not_export_ready_movement_rows,
            gate_status,
            gate_reason
        from core_loco_day_coverage
        order by coverage_date desc, loco_no asc
        """
    )

    con.execute(
        """
        create or replace table dq_export_gate_ru as
        with ru_days as (
            select distinct
                loco_no,
                trim(performing_ru) as performing_ru,
                coverage_date
            from tmp_qg_assignment_slots
            where nullif(trim(loco_no), '') is not null
              and nullif(trim(performing_ru), '') is not null
        )
        select
            g.run_id,
            g.loco_no,
            r.performing_ru,
            g.coverage_date,
            g.coverage_pct,
            g.assigned_minutes,
            g.unresolved_gap_minutes,
            g.overlap_minutes,
            g.error_findings,
            g.manual_review_findings,
            g.gate_status,
            g.gate_reason
        from dq_export_gate g
        join ru_days r
          on r.loco_no = g.loco_no
         and r.coverage_date = g.coverage_date
        order by g.coverage_date desc, r.performing_ru asc, g.loco_no asc
        """
    )

    con.execute(
        """
        create or replace table dq_global_export_blockers as
        select
            ?::varchar as run_id,
            cast(coalesce(period_start_utc, period_end_utc, current_timestamp) as date)
                as blocker_date,
            rule_id,
            severity,
            row_type,
            transport_number,
            performing_ru,
            message,
            'BLOCKED'::varchar as gate_status
        from dq_findings
        where severity in ('ERROR', 'MANUAL_REVIEW')
          and (
                rule_id = 'R012'
             or nullif(trim(loco_no), '') is null
          )
        order by blocker_date desc, rule_id asc, transport_number asc
        """,
        [run_id_text],
    )

    # ------------------------------------------------------------------
    # 5. Aus Exporten ausgeschlossene Movement-Zeilen auditierbar speichern.
    # ------------------------------------------------------------------
    con.execute(
        """
        create or replace table export_excluded_rows as
        with movement_base as (
            select
                c.*,
                cast(
                    coalesce(
                        c.actual_departure_ts,
                        c.period_start_utc,
                        c.sequence_ts,
                        c.actual_arrival_ts,
                        c.period_end_utc
                    ) as date
                ) as coverage_date
            from core_loco_timeline c
            where c.row_type = 'MOVEMENT'
              and c.report_scope = 'IN_REPORT'
        )
        select
            m.run_id,
            m.loco_no,
            m.transport_number,
            m.train_no,
            m.performing_ru,
            m.holder_name,
            m.period_start_utc,
            m.period_end_utc,
            m.coverage_date,
            coalesce(g.gate_status, '') as gate_status,
            concat_ws(
                ' | ',
                case when coalesce(m.export_ready, false) = false
                    then 'Movement export_ready=false' end,
                nullif(g.gate_reason, ''),
                case when exists (
                    select 1
                    from dq_global_export_blockers b
                    where b.blocker_date = m.coverage_date
                      and b.gate_status = 'BLOCKED'
                ) then 'Globaler Export-Blocker am Tag vorhanden' end
            ) as exclusion_reason,
            m.source_table,
            m.source_row_id
        from movement_base m
        left join dq_export_gate_ru g
          on g.loco_no = m.loco_no
         and g.coverage_date = m.coverage_date
         and g.performing_ru is not distinct from m.performing_ru
        where coalesce(m.export_ready, false) = false
           or coalesce(g.gate_status, '') = 'BLOCKED'
           or exists (
                select 1
                from dq_global_export_blockers b
                where b.blocker_date = m.coverage_date
                  and b.gate_status = 'BLOCKED'
           )
        order by m.coverage_date desc, m.loco_no asc, m.period_start_utc asc
        """
    )

    refresh_reconciliation_table(con, run_id_text)


def refresh_reconciliation_table(con, run_id: str) -> None:
    """Reconciliation und Betriebsampel nach Aufbau der Exporte aktualisieren."""
    _require_tables(
        con,
        [
            "core_loco_day_coverage",
            "dq_export_gate",
            "dq_export_gate_ru",
            "dq_global_export_blockers",
            "export_excluded_rows",
        ],
    )

    snapshot_at_utc = None
    error_cutoff_utc = None

    if table_exists(con, "dq_run_metadata"):
        row = con.execute(
            """
            select source_snapshot_at_utc, error_cutoff_utc
            from dq_run_metadata
            limit 1
            """
        ).fetchone()

        if row:
            snapshot_at_utc, error_cutoff_utc = row

    metrics = {
        "raw_locomotive_movement_rows": _count(con, "raw_locomotivemovement"),
        "raw_transport_detail_rows": _count(con, "raw_transportdetail"),
        "raw_locomotive_master_rows": _count(con, "raw_locomotive"),
        "staging_event_rows": _count(con, "stg_loco_events"),
        "skipped_event_rows": _count(con, "stg_loco_events_skipped"),
        "timeline_movement_rows": _count(con, "core_loco_timeline", "row_type = 'MOVEMENT'"),
        "timeline_gap_rows": _count(con, "core_loco_timeline", "row_type = 'GAP'"),
        "de_movement_rows": _count(
            con,
            "core_loco_timeline",
            "row_type = 'MOVEMENT' and report_scope = 'IN_REPORT'",
        ),
        "findings_error": _count(con, "dq_findings", "severity = 'ERROR'"),
        "findings_manual_review": _count(con, "dq_findings", "severity = 'MANUAL_REVIEW'"),
        "findings_warning": _count(con, "dq_findings", "severity = 'WARNING'"),
        "findings_info": _count(con, "dq_findings", "severity = 'INFO'"),
        "loco_days_ready": _count(con, "dq_export_gate", "gate_status = 'READY'"),
        "loco_days_warning": _count(con, "dq_export_gate", "gate_status = 'WARNING'"),
        "loco_days_blocked": _count(con, "dq_export_gate", "gate_status = 'BLOCKED'"),
        "global_export_blockers": _count(con, "dq_global_export_blockers"),
        "excluded_export_rows": _count(con, "export_excluded_rows"),
        "export_zuordnungen_rows": _count(con, "export_zuordnungen"),
        "export_nutzungsmeldung_rows": _count(con, "export_nutzungsmeldung"),
        "unresolved_performing_ru": _count(
            con,
            "dq_unresolved_performing_ru_market_partner_alias",
        ),
        "market_partner_mapping_conflicts": _count(
            con,
            "cfg_market_partner_mapping_conflicts",
        ),
        "market_partner_role_conflicts": _count(
            con,
            "cfg_market_partner_role_conflicts",
        ),
    }

    coverage_row = con.execute(
        """
        select
            coalesce(sum(assigned_minutes), 0),
            coalesce(sum(unresolved_gap_minutes), 0),
            coalesce(sum(overlap_minutes), 0),
            case
                when coalesce(sum(assigned_minutes), 0)
                   + coalesce(sum(unresolved_gap_minutes), 0) = 0
                    then 0::double
                else round(
                    100.0 * coalesce(sum(assigned_minutes), 0)
                    / (
                        coalesce(sum(assigned_minutes), 0)
                        + coalesce(sum(unresolved_gap_minutes), 0)
                    ),
                    2
                )
            end as total_coverage_pct
        from core_loco_day_coverage
        """
    ).fetchone()

    metrics["assigned_minutes"] = int(coverage_row[0] or 0)
    metrics["unresolved_gap_minutes"] = int(coverage_row[1] or 0)
    metrics["overlap_minutes"] = int(coverage_row[2] or 0)
    metrics["total_coverage_pct"] = float(coverage_row[3] or 0.0)

    con.execute(
        """
        create or replace table dq_reconciliation (
            run_id varchar,
            calculated_at_utc timestamp,
            source_snapshot_at_utc timestamp,
            error_cutoff_utc timestamp,
            raw_locomotive_movement_rows bigint,
            raw_transport_detail_rows bigint,
            raw_locomotive_master_rows bigint,
            staging_event_rows bigint,
            skipped_event_rows bigint,
            timeline_movement_rows bigint,
            timeline_gap_rows bigint,
            de_movement_rows bigint,
            findings_error bigint,
            findings_manual_review bigint,
            findings_warning bigint,
            findings_info bigint,
            loco_days_ready bigint,
            loco_days_warning bigint,
            loco_days_blocked bigint,
            global_export_blockers bigint,
            excluded_export_rows bigint,
            export_zuordnungen_rows bigint,
            export_nutzungsmeldung_rows bigint,
            unresolved_performing_ru bigint,
            market_partner_mapping_conflicts bigint,
            market_partner_role_conflicts bigint,
            assigned_minutes bigint,
            unresolved_gap_minutes bigint,
            overlap_minutes bigint,
            total_coverage_pct double
        )
        """
    )

    con.execute(
        """
        insert into dq_reconciliation values (
            ?, current_timestamp, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        [
            str(run_id),
            snapshot_at_utc,
            error_cutoff_utc,
            metrics["raw_locomotive_movement_rows"],
            metrics["raw_transport_detail_rows"],
            metrics["raw_locomotive_master_rows"],
            metrics["staging_event_rows"],
            metrics["skipped_event_rows"],
            metrics["timeline_movement_rows"],
            metrics["timeline_gap_rows"],
            metrics["de_movement_rows"],
            metrics["findings_error"],
            metrics["findings_manual_review"],
            metrics["findings_warning"],
            metrics["findings_info"],
            metrics["loco_days_ready"],
            metrics["loco_days_warning"],
            metrics["loco_days_blocked"],
            metrics["global_export_blockers"],
            metrics["excluded_export_rows"],
            metrics["export_zuordnungen_rows"],
            metrics["export_nutzungsmeldung_rows"],
            metrics["unresolved_performing_ru"],
            metrics["market_partner_mapping_conflicts"],
            metrics["market_partner_role_conflicts"],
            metrics["assigned_minutes"],
            metrics["unresolved_gap_minutes"],
            metrics["overlap_minutes"],
            metrics["total_coverage_pct"],
        ],
    )

    snapshot_age_hours = None

    if snapshot_at_utc is not None:
        snapshot_age_hours = con.execute(
            """
            select round(
                date_diff('second', try_cast(? as timestamp), current_timestamp) / 3600.0,
                2
            )
            """,
            [str(snapshot_at_utc)],
        ).fetchone()[0]

    kpi_rows = [
        (
            "IMPORT",
            "SNAPSHOT_AGE_HOURS",
            "Alter des letzten vollständigen Rohdaten-Snapshots in Stunden",
            snapshot_age_hours,
            "< 24",
            "GREEN" if snapshot_age_hours is not None and snapshot_age_hours < 24 else "RED",
            "Snapshot-Zeitpunkt aus raw_import_manifest.json / dq_run_metadata",
        ),
        (
            "IMPORT",
            "RAW_REQUIRED_FILES",
            "Erfolgreich importierte Pflichtdateien",
            3,
            "3",
            "GREEN",
            "LocomotiveMovement.csv, TransportDetail.csv und Locomotive.csv",
        ),
        (
            "QUALITY",
            "BLOCKING_FINDINGS",
            "Blockierende Findings",
            metrics["findings_error"] + metrics["findings_manual_review"],
            "0",
            "GREEN" if metrics["findings_error"] + metrics["findings_manual_review"] == 0 else "RED",
            "ERROR und MANUAL_REVIEW",
        ),
        (
            "QUALITY",
            "LOCO_DAYS_BLOCKED",
            "Blockierte Lok-Tage",
            metrics["loco_days_blocked"],
            "0",
            "GREEN" if metrics["loco_days_blocked"] == 0 else "RED",
            "Export-Gate je Lok und Kalendertag",
        ),
        (
            "QUALITY",
            "LOCO_DAYS_WARNING",
            "Lok-Tage mit Warnung",
            metrics["loco_days_warning"],
            "beobachten",
            "GREEN" if metrics["loco_days_warning"] == 0 else "YELLOW",
            "Kurze GAPs oder nicht blockierende Hinweise",
        ),
        (
            "QUALITY",
            "COVERAGE_PCT",
            "Rechnerische Deckungsquote in Prozent",
            metrics["total_coverage_pct"],
            "100",
            "GREEN" if metrics["total_coverage_pct"] == 100 else "YELLOW",
            "Zugeordnete Minuten / (zugeordnete Minuten + relevante GAP-Minuten)",
        ),
        (
            "QUALITY",
            "UNRESOLVED_GAP_MINUTES",
            "Ungeklärte GAP-Minuten",
            metrics["unresolved_gap_minutes"],
            "0",
            "GREEN" if metrics["unresolved_gap_minutes"] == 0 else "YELLOW",
            "15-minutenscharf aggregierte relevante GAP-Zeit",
        ),
        (
            "QUALITY",
            "OVERLAP_MINUTES",
            "Überschneidungsminuten",
            metrics["overlap_minutes"],
            "0",
            "GREEN" if metrics["overlap_minutes"] == 0 else "RED",
            "15-minutenscharf aggregierte Mehrfachbelegung",
        ),
        (
            "MAPPING",
            "UNRESOLVED_PERFORMING_RU",
            "Ungeklärte PerformingRU-Schreibweisen",
            metrics["unresolved_performing_ru"],
            "0",
            "GREEN" if metrics["unresolved_performing_ru"] == 0 else "RED",
            "Fehlende ANU_VENS-Zuordnung",
        ),
        (
            "MAPPING",
            "MAPPING_CONFLICTS",
            "Konflikte in Marktpartner-Mappings und Rollen",
            metrics["market_partner_mapping_conflicts"] + metrics["market_partner_role_conflicts"],
            "0",
            "GREEN" if metrics["market_partner_mapping_conflicts"] + metrics["market_partner_role_conflicts"] == 0 else "RED",
            "Mehrdeutige Referenzdaten müssen vor Export geklärt werden",
        ),
        (
            "EXPORT",
            "GLOBAL_EXPORT_BLOCKERS",
            "Globale Export-Blocker",
            metrics["global_export_blockers"],
            "0",
            "GREEN" if metrics["global_export_blockers"] == 0 else "RED",
            "Insbesondere R012 ohne eindeutig zuordenbare Lok",
        ),
        (
            "EXPORT",
            "EXCLUDED_EXPORT_ROWS",
            "Bewusst vom Export ausgeschlossene Bewegungen",
            metrics["excluded_export_rows"],
            "0 vor Freigabe",
            "GREEN" if metrics["excluded_export_rows"] == 0 else "YELLOW",
            "Audit-Tabelle export_excluded_rows",
        ),
    ]

    con.execute(
        """
        create or replace table dq_operational_kpis (
            kpi_group varchar,
            kpi_code varchar,
            kpi_label varchar,
            kpi_value double,
            target_value varchar,
            traffic_light varchar,
            details varchar
        )
        """
    )

    con.executemany(
        "insert into dq_operational_kpis values (?, ?, ?, ?, ?, ?, ?)",
        kpi_rows,
    )

    print(
        "Quality Gate aktualisiert: "
        f"READY={metrics['loco_days_ready']} | "
        f"WARNING={metrics['loco_days_warning']} | "
        f"BLOCKED={metrics['loco_days_blocked']} | "
        f"Globale Blocker={metrics['global_export_blockers']} | "
        f"Deckungsquote={metrics['total_coverage_pct']}%"
    )
