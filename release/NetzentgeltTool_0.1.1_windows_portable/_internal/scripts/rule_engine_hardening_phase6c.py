from __future__ import annotations

"""
Netzentgelt MVP - Rule Engine Hardening Phase 6C
================================================

Konsolidierte P1-Haertung fuer belastbare DE-Segmente, GAP-Kontext und
symmetrische R012-Dummy-Erkennung.

Die Schicht wird innerhalb des temporaeren DuckDB-Neuaufbaus ausgefuehrt.
Original-CSVs bleiben unveraendert.
"""

from typing import Iterable

from rule_engine_hardening_phase6b import _cutoff_utc, _refresh_core_quality_flags

PHASE_ID = "NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_ADJACENCY_HOTFIX_V1_20260608"


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


def _pick_column(available: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in available}
    for candidate in candidates:
        value = by_lower.get(str(candidate).lower())
        if value:
            return value
    return None


def _text_expr(column_name: str | None) -> str:
    if not column_name:
        return "NULL"
    return f"nullif(trim(cast({qident(column_name)} as varchar)), '')"


def _de_relevance_expr(available_columns: list[str]) -> str:
    origin = _pick_column(
        available_columns,
        [
            "OriginCountryISO",
            "OriginCountryIso",
            "OriginCountry",
            "FromCountryISO",
            "FromCountry",
            "DepartureCountryISO",
            "DepartureCountry",
        ],
    )
    destination = _pick_column(
        available_columns,
        [
            "DestinationCountryISO",
            "DestinationCountryIso",
            "DestinationCountry",
            "ToCountryISO",
            "ToCountry",
            "ArrivalCountryISO",
            "ArrivalCountry",
        ],
    )
    if not origin and not destination:
        country = _pick_column(available_columns, ["Country"])
        return f"upper(coalesce({_text_expr(country)}, '')) = 'DE'"
    return (
        f"(upper(coalesce({_text_expr(origin)}, '')) = 'DE' "
        f"or upper(coalesce({_text_expr(destination)}, '')) = 'DE')"
    )


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create table if not exists dq_rule_engine_hardening_phase6c_audit (
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
        insert into dq_rule_engine_hardening_phase6c_audit values (
            ?, ?, ?, ?, current_timestamp, ?
        )
        """,
        [PHASE_ID, str(run_id), str(metric), int(value or 0), str(comment)],
    )


def _context_class_sql(prefix: str = "a") -> str:
    return f"""
        case
            when {prefix}.report_scope = 'IN_REPORT'
             and {prefix}.next_report_scope = 'IN_REPORT'
             and upper(coalesce({prefix}.de_event_label, '')) in ('IN DE', 'EINFAHRT')
             and upper(coalesce({prefix}.next_de_event_label, '')) in ('IN DE', 'AUSFAHRT')
                then 'DE_CONTINUITY'
            when {prefix}.report_scope = 'IN_REPORT'
             and {prefix}.next_report_scope = 'IN_REPORT'
                then 'DE_BORDER_CONTEXT_REVIEW'
            when {prefix}.report_scope = 'IN_REPORT'
             and {prefix}.next_report_scope <> 'IN_REPORT'
                then 'DE_TO_FOREIGN_CONTEXT_REVIEW'
            when {prefix}.report_scope <> 'IN_REPORT'
             and {prefix}.next_report_scope = 'IN_REPORT'
                then 'FOREIGN_TO_DE_CONTEXT_REVIEW'
            else 'FOREIGN_ONLY'
        end
    """


def prepare_timeline_context_phase6c(con, run_id: str) -> None:
    """Belastbare GAP-Grenzen, Kontexttabellen und STAND-Kandidaten aufbauen."""
    if not table_exists(con, "core_loco_timeline"):
        raise RuntimeError("core_loco_timeline fehlt. Phase 6C kann nicht ausgefuehrt werden.")

    _ensure_column(con, "core_loco_timeline", "gap_time_basis_safe", "boolean")
    _ensure_column(con, "core_loco_timeline", "gap_context_class", "varchar")
    _ensure_column(con, "core_loco_timeline", "de_period_start_utc", "timestamp")
    _ensure_column(con, "core_loco_timeline", "de_period_end_utc", "timestamp")

    con.execute(
        """
        update core_loco_timeline
        set
            de_period_start_utc = case
                when row_type <> 'MOVEMENT' then null
                when faulty_dir = 'E' and sequence_ts is not null then sequence_ts
                else actual_departure_ts
            end,
            de_period_end_utc = case
                when row_type <> 'MOVEMENT' then null
                when faulty_dir = 'A' and sequence_ts is not null then sequence_ts
                else actual_arrival_ts
            end
        """
    )

    con.execute(
        f"""
        create or replace temp table tmp_phase6c_adjacency as
        with movements as (
            select *
            from core_loco_timeline
            where row_type = 'MOVEMENT'
        ), ordered as (
            select
                c.*,
                n.movement_sequence_no as next_movement_sequence_no,
                n.transport_number as next_transport_number,
                n.actual_departure_ts as next_actual_departure_ts,
                n.period_start_utc as next_period_start_utc,
                n.sequence_ts as next_sequence_ts,
                n.origin_name as next_origin_name,
                n.origin_country_iso as next_origin_country_iso,
                n.report_scope as next_report_scope,
                n.de_event_label as next_de_event_label,
                n.source_table as next_source_table,
                n.source_row_id as next_source_row_id
            from movements c
            left join lateral (
                select candidate.*
                from movements candidate
                where candidate.loco_no is not distinct from c.loco_no
                  and candidate.movement_sequence_no > c.movement_sequence_no
                  and (
                        c.actual_arrival_ts is null
                     or candidate.actual_departure_ts is null
                     or candidate.actual_departure_ts >= c.actual_arrival_ts
                  )
                order by
                    case when candidate.actual_departure_ts is null then 1 else 0 end,
                    candidate.actual_departure_ts asc nulls last,
                    candidate.movement_sequence_no asc,
                    candidate.source_row_id asc
                limit 1
            ) n on true
        )
        select
            *,
            {_context_class_sql('ordered')} as derived_gap_context_class,
            case
                when actual_arrival_ts is not null
                 and next_actual_departure_ts is not null
                 and next_actual_departure_ts >= actual_arrival_ts
                    then true
                else false
            end as derived_gap_time_basis_safe,
            case
                when actual_arrival_ts is not null
                 and next_actual_departure_ts is not null
                    then date_diff('minute', actual_arrival_ts, next_actual_departure_ts)
                else null
            end as actual_gap_minutes
        from ordered
        where next_movement_sequence_no is not null
        """
    )

    con.execute(
        """
        create or replace table dq_phase6c_nested_event_skips as
        with ordered as (
            select
                c.*,
                lead(transport_number) over w as skipped_transport_number,
                lead(actual_departure_ts) over w as skipped_actual_departure_ts,
                lead(actual_arrival_ts) over w as skipped_actual_arrival_ts,
                lead(source_table) over w as skipped_source_table,
                lead(source_row_id) over w as skipped_source_row_id
            from core_loco_timeline c
            where row_type = 'MOVEMENT'
            window w as (
                partition by loco_no
                order by movement_sequence_no asc, source_row_id asc
            )
        )
        select
            loco_no,
            transport_number,
            actual_departure_ts,
            actual_arrival_ts,
            skipped_transport_number,
            skipped_actual_departure_ts,
            skipped_actual_arrival_ts,
            'TEMPORAL_NESTING_OR_OVERLAP_SKIPPED_FOR_GAP_ADJACENCY'::varchar as audit_reason,
            source_table,
            source_row_id,
            skipped_source_table,
            skipped_source_row_id
        from ordered
        where actual_arrival_ts is not null
          and skipped_actual_departure_ts is not null
          and skipped_actual_departure_ts < actual_arrival_ts
        order by loco_no, actual_arrival_ts, source_row_id
        """
    )

    # Bestehende GAP-Zeilen auf belastbare Grenzen umstellen. Unsichere Grenzen
    # bleiben sichtbar, duerfen aber weder Dauer noch harte 15-Minuten-Deckung liefern.
    con.execute(
        """
        update core_loco_timeline as g
        set
            gap_time_basis_safe = a.derived_gap_time_basis_safe,
            gap_context_class = a.derived_gap_context_class,
            gap_relevant_de = case when a.derived_gap_context_class = 'DE_CONTINUITY' then true else false end,
            gap_from_utc = case when a.derived_gap_time_basis_safe then a.actual_arrival_ts else null end,
            gap_to_utc = case when a.derived_gap_time_basis_safe then a.next_actual_departure_ts else null end,
            gap_duration_minutes = case when a.derived_gap_time_basis_safe then a.actual_gap_minutes else null end,
            gap_duration_text = case
                when a.derived_gap_time_basis_safe then cast(a.actual_gap_minutes as varchar) || ' Minuten'
                else null
            end,
            gap_message = case
                when a.derived_gap_time_basis_safe then
                    'Keine Nutzung im Zeitraum von '
                    || strftime(a.actual_arrival_ts, '%d.%m.%Y %H:%M:%S')
                    || ' bis '
                    || strftime(a.next_actual_departure_ts, '%d.%m.%Y %H:%M:%S')
                    || '. Das entspricht '
                    || cast(a.actual_gap_minutes as varchar)
                    || ' Minuten.'
                else
                    'Unterbrechung der Ortskette erkannt. Dauer nicht sicher berechenbar, da ActualArrival oder naechstes ActualDeparture fehlt.'
            end
        from tmp_phase6c_adjacency a
        where g.row_type = 'GAP'
          and g.loco_no is not distinct from a.loco_no
          and g.movement_sequence_no is not distinct from a.movement_sequence_no
          and g.source_table is not distinct from a.source_table
          and g.source_row_id is not distinct from a.source_row_id
        """
    )

    con.execute(
        """
        create or replace table dq_phase6c_uncertain_gaps as
        select
            ?::varchar as run_id,
            loco_no,
            transport_number,
            next_transport_number,
            destination_name,
            next_origin_name,
            actual_arrival_ts,
            next_actual_departure_ts,
            coalesce(actual_arrival_ts, period_end_utc, sequence_ts) as approximate_gap_start_utc,
            coalesce(next_actual_departure_ts, next_period_start_utc, next_sequence_ts) as approximate_gap_end_utc,
            derived_gap_context_class as gap_context_class,
            source_table,
            source_row_id
        from tmp_phase6c_adjacency
        where destination_name is not null
          and next_origin_name is not null
          and lower(trim(destination_name)) <> lower(trim(next_origin_name))
          and derived_gap_context_class = 'DE_CONTINUITY'
          and coalesce(derived_gap_time_basis_safe, false) = false
        order by loco_no, approximate_gap_start_utc, source_row_id
        """,
        [str(run_id)],
    )

    con.execute(
        """
        create or replace table dq_phase6c_gap_context_review as
        select
            ?::varchar as run_id,
            loco_no,
            transport_number,
            next_transport_number,
            destination_name,
            next_origin_name,
            de_event_label,
            next_de_event_label,
            report_scope,
            next_report_scope,
            actual_arrival_ts,
            next_actual_departure_ts,
            actual_gap_minutes,
            derived_gap_context_class as gap_context_class,
            source_table,
            source_row_id
        from tmp_phase6c_adjacency
        where destination_name is not null
          and next_origin_name is not null
          and lower(trim(destination_name)) <> lower(trim(next_origin_name))
          and derived_gap_context_class in (
                'DE_BORDER_CONTEXT_REVIEW',
                'DE_TO_FOREIGN_CONTEXT_REVIEW',
                'FOREIGN_TO_DE_CONTEXT_REVIEW'
          )
        order by loco_no, actual_arrival_ts, source_row_id
        """,
        [str(run_id)],
    )

    con.execute(
        """
        create or replace table core_loco_stand_candidates as
        select
            ?::varchar as run_id,
            loco_no,
            transport_number,
            next_transport_number,
            destination_name as location_name,
            actual_arrival_ts as stand_from_utc,
            next_actual_departure_ts as stand_to_utc,
            actual_gap_minutes as stand_duration_minutes,
            performing_ru,
            report_scope,
            next_report_scope,
            'POTENTIAL_COLD_STAND'::varchar as stand_class,
            'Standzeit ueber 8 Stunden am selben Ort. Fachlich als moegliche kalte Abstellung pruefen.'::varchar as suggested_action,
            source_table,
            source_row_id
        from tmp_phase6c_adjacency
        where destination_name is not null
          and next_origin_name is not null
          and lower(trim(destination_name)) = lower(trim(next_origin_name))
          and coalesce(derived_gap_time_basis_safe, false) = true
          and coalesce(actual_gap_minutes, 0) > 480
          and report_scope = 'IN_REPORT'
          and next_report_scope = 'IN_REPORT'
        order by stand_duration_minutes desc, loco_no, stand_from_utc
        """,
        [str(run_id)],
    )

    _audit(
        con,
        run_id,
        "nested_event_skips_for_gap_adjacency",
        int(con.execute("select count(*) from dq_phase6c_nested_event_skips").fetchone()[0]),
        "Zeitlich verschachtelte operative Ereignisse werden fuer die GAP-Nachbarschaft uebersprungen und separat auditiert.",
    )
    _audit(
        con,
        run_id,
        "uncertain_gap_rows",
        int(con.execute("select count(*) from dq_phase6c_uncertain_gaps").fetchone()[0]),
        "Gebrochene DE-Ortsketten ohne belastbare ActualArrival-/ActualDeparture-Grenzen.",
    )
    _audit(
        con,
        run_id,
        "gap_context_review_rows",
        int(con.execute("select count(*) from dq_phase6c_gap_context_review").fetchone()[0]),
        "Grenzkontext-GAPs werden auditierbar klassifiziert, aber nicht automatisch blockierend bewertet.",
    )
    _audit(
        con,
        run_id,
        "potential_cold_stand_rows",
        int(con.execute("select count(*) from core_loco_stand_candidates").fetchone()[0]),
        "Standzeiten ueber 8 Stunden am selben DE-Ort als Pruefkandidaten vorbereitet.",
    )


def _refresh_export_policy(con) -> None:
    cutoff = _cutoff_utc(con)
    if cutoff is None:
        raise RuntimeError("dq_run_metadata.error_cutoff_utc fehlt. Phase 6C bricht sicher ab.")
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
             and nullif(trim(user_vens), '') is not null
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
             and (
                    coalesce(period_start_utc, period_end_utc, sequence_ts) is null
                 or coalesce(period_start_utc, period_end_utc, sequence_ts) <= ?
             )
                then true
            else false
        end
        """,
        [cutoff],
    )


def _insert_r015_uncertain_gap_findings(con, run_id: str) -> None:
    cutoff = _cutoff_utc(con)
    if cutoff is None:
        raise RuntimeError("dq_run_metadata.error_cutoff_utc fehlt. Phase 6C bricht sicher ab.")

    # Alte R010/R010.5-Findings fuer unsichere GAP-Zeilen entfernen.
    con.execute(
        """
        delete from dq_findings as f
        where f.rule_id in ('R010', 'R010.5')
          and exists (
                select 1
                from core_loco_timeline g
                where g.row_type = 'GAP'
                  and coalesce(g.gap_time_basis_safe, false) = false
                  and g.loco_no is not distinct from f.loco_no
                  and g.source_table is not distinct from f.source_table
                  and g.source_row_id is not distinct from f.source_row_id
          )
        """
    )
    con.execute("delete from dq_findings where rule_id = 'R015'")
    con.execute(
        """
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        select
            ?,
            case
                when coalesce(approximate_gap_start_utc, approximate_gap_end_utc) <= ?
                    then 'MANUAL_REVIEW'
                else 'INFO'
            end,
            'R015',
            'TIMELINE',
            loco_no,
            transport_number,
            null::varchar,
            'GAP_UNCERTAIN',
            null::bigint,
            approximate_gap_start_utc,
            approximate_gap_end_utc,
            'Unterbrechung der Ortskette erkannt. Dauer nicht sicher berechenbar, da ActualArrival oder naechstes ActualDeparture fehlt.',
            'Zeitwerte und Ortskette in RailCube pruefen. Keine automatische GAP- oder Kalte-Abstellung-Bewertung.',
            case
                when coalesce(approximate_gap_start_utc, approximate_gap_end_utc) <= ?
                    then 'open'
                else 'info'
            end,
            source_table,
            source_row_id,
            null::varchar
        from dq_phase6c_uncertain_gaps
        """,
        [str(run_id), cutoff, cutoff],
    )


def _insert_r012_transportdetail_dummy_findings(con, run_id: str) -> None:
    table = "raw_transportdetail"
    if not table_exists(con, table):
        return
    cutoff = _cutoff_utc(con)
    if cutoff is None:
        raise RuntimeError("dq_run_metadata.error_cutoff_utc fehlt. Phase 6C bricht sicher ab.")

    available = columns(con, table)
    transport = _text_expr(_pick_column(available, ["TransportNumber", "TransportNo", "TransportId", "TransportID"]))
    loco = _text_expr(_pick_column(available, ["FirstLocomotiveNo", "LocomotiveNo", "Alias"]))
    movement_type = _text_expr(_pick_column(available, ["MovementType"]))
    actual_departure = _text_expr(_pick_column(available, ["ActualDeparture"]))
    de_relevant = _de_relevance_expr(available)
    if "NULL" in (transport, loco, movement_type, actual_departure):
        return

    con.execute(
        f"""
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        with raw_rows as (
            select
                row_number() over () as source_row_id,
                {transport} as transport_number,
                {loco} as first_loco_no,
                {movement_type} as movement_type,
                try_cast({actual_departure} as timestamp) as period_start_utc,
                {de_relevant} as is_de_relevant
            from {qident(table)}
            where not exists (
                select 1
                from cfg_excluded_cancelled_transports excluded
                where excluded.transport_number = {transport}
            )
        ), grouped as (
            select
                transport_number,
                min(period_start_utc) as period_start_utc,
                min(source_row_id) as source_row_id,
                count(*) as affected_raw_rows
            from raw_rows
            where is_de_relevant
              and lower(coalesce(movement_type, '')) = 'train movement'
              and period_start_utc is not null
              and period_start_utc <= ?
              and trim(coalesce(first_loco_no, '')) = '00000000000-0'
            group by transport_number
        )
        select
            ?,
            'ERROR',
            'R012',
            'NO_LOCO_RAW',
            '00000000000-0',
            transport_number,
            null::varchar,
            'RAW_TRANSPORT_DETAIL',
            null::bigint,
            period_start_utc,
            null::timestamp,
            'Technische Dummy-Loknummer 00000000000-0 in TransportDetail erkannt. Betroffene Rohdatenzeilen: '
                || cast(affected_raw_rows as varchar) || '.',
            'Transportplanung pruefen und echte Loknummer in RailCube ergaenzen.',
            'open',
            '{table}',
            source_row_id,
            null::varchar
        from grouped g
        where not exists (
            select 1
            from dq_findings f
            where f.rule_id = 'R012'
              and f.source_table = '{table}'
              and f.transport_number is not distinct from g.transport_number
              and f.message like 'Technische Dummy-Loknummer%'
        )
        """,
        [cutoff, str(run_id)],
    )


def _refresh_rule_catalog(con) -> None:
    con.execute("delete from cfg_dq_rule_catalog where rule_id in ('R015')")
    con.execute(
        """
        insert into cfg_dq_rule_catalog values
            ('R015', 'TIMELINE', 'INFO innerhalb 24h / MANUAL_REVIEW danach',
             'Unterbrechung erkannt, Dauer aber mangels belastbarer Zeitgrenzen nicht sicher berechenbar.', true)
        """
    )


def build_central_de_usage_segments(con, run_id: str) -> None:
    """Eine zentrale, auf den meldefaehigen DE-Zeitraum begrenzte Segmenttabelle erzeugen."""
    if not table_exists(con, "core_loco_timeline"):
        raise RuntimeError("core_loco_timeline fehlt. DE-Segmente koennen nicht aufgebaut werden.")

    con.execute(
        """
        create or replace table core_usage_assignment_segment_movements as
        with movement_base as (
            select
                c.*,
                case
                    when c.faulty_dir = 'E' and c.sequence_ts is not null then c.sequence_ts
                    else c.actual_departure_ts
                end as bounded_de_start_utc,
                case
                    when c.faulty_dir = 'A' and c.sequence_ts is not null then c.sequence_ts
                    else c.actual_arrival_ts
                end as bounded_de_end_utc
            from core_loco_timeline c
            where c.row_type = 'MOVEMENT'
              and c.report_scope = 'IN_REPORT'
              and nullif(trim(c.loco_no), '') is not null
        ), eligible as (
            select *
            from movement_base
            where bounded_de_start_utc is not null
              and bounded_de_end_utc is not null
              and bounded_de_end_utc > bounded_de_start_utc
        ), ordered as (
            select
                e.*,
                lag(movement_sequence_no) over w as prev_movement_sequence_no,
                lag(performing_ru) over w as prev_performing_ru
            from eligible e
            window w as (
                partition by loco_no
                order by movement_sequence_no asc, source_row_id asc
            )
        ), marked as (
            select
                o.*,
                case
                    when prev_movement_sequence_no is null then 1
                    when prev_performing_ru is distinct from performing_ru then 1
                    when movement_sequence_no <> prev_movement_sequence_no + 1 then 1
                    when exists (
                        select 1
                        from core_loco_timeline g
                        where g.row_type = 'GAP'
                          and coalesce(g.gap_relevant_de, false) = true
                          and g.loco_no is not distinct from o.loco_no
                          and g.movement_sequence_no is not distinct from o.prev_movement_sequence_no
                    ) then 1
                    else 0
                end as starts_new_segment
            from ordered o
        ), segmented as (
            select
                *,
                sum(starts_new_segment) over (
                    partition by loco_no
                    order by movement_sequence_no asc, source_row_id asc
                    rows between unbounded preceding and current row
                ) as usage_segment_no
            from marked
        )
        select
            ?::varchar as run_id,
            loco_no,
            usage_segment_no,
            loco_no || ':' || cast(usage_segment_no as varchar) as usage_segment_id,
            tfze_or_tens,
            performing_ru,
            holder_name,
            holder_market_partner_id,
            user_vens,
            bounded_de_start_utc as de_period_start_utc,
            bounded_de_end_utc as de_period_end_utc,
            actual_departure_ts,
            actual_arrival_ts,
            movement_sequence_no,
            transport_number,
            train_no,
            source_table,
            source_row_id,
            export_ready,
            export_blocking
        from segmented
        """,
        [str(run_id)],
    )

    con.execute(
        """
        create or replace table core_usage_assignment_segments as
        select
            run_id,
            loco_no,
            usage_segment_no,
            usage_segment_id,
            first(tfze_or_tens order by de_period_start_utc, source_row_id) as tfze_or_tens,
            performing_ru,
            min(de_period_start_utc) as segment_start_utc,
            max(de_period_end_utc) as segment_end_utc,
            min(actual_departure_ts) as first_actual_departure_utc,
            max(actual_arrival_ts) as last_actual_arrival_utc,
            count(*) as movement_count,
            count(*) filter (where coalesce(export_ready, false) = true) as export_ready_movement_rows,
            count(*) filter (where coalesce(export_blocking, false) = true) as export_blocking_movement_rows,
            first(nullif(trim(user_vens), '') order by de_period_start_utc, source_row_id)
                filter (where nullif(trim(user_vens), '') is not null) as user_vens,
            first(nullif(trim(holder_name), '') order by de_period_start_utc, source_row_id)
                filter (where nullif(trim(holder_name), '') is not null) as holder_name,
            first(nullif(trim(holder_market_partner_id), '') order by de_period_start_utc, source_row_id)
                filter (where nullif(trim(holder_market_partner_id), '') is not null) as holder_market_partner_id
        from core_usage_assignment_segment_movements
        group by run_id, loco_no, usage_segment_no, usage_segment_id, performing_ru
        having max(de_period_end_utc) > min(de_period_start_utc)
        order by loco_no, segment_start_utc, usage_segment_no
        """
    )


def harden_findings_and_segments_phase6c(con, run_id: str) -> None:
    """Phase-6C-Findings, Exportpolicy und zentrale Segmente abschliessend aktualisieren."""
    if not table_exists(con, "dq_findings"):
        raise RuntimeError("dq_findings fehlt. Phase 6C kann nicht ausgefuehrt werden.")
    _insert_r015_uncertain_gap_findings(con, run_id)
    _insert_r012_transportdetail_dummy_findings(con, run_id)
    _refresh_rule_catalog(con)
    _refresh_core_quality_flags(con)
    _refresh_export_policy(con)
    build_central_de_usage_segments(con, run_id)

    _audit(
        con,
        run_id,
        "r015_uncertain_gap_findings",
        int(con.execute("select count(*) from dq_findings where rule_id = 'R015'").fetchone()[0]),
        "Unsichere GAP-Zeitgrenzen werden sichtbar statt mit Ersatzdauer bewertet.",
    )
    _audit(
        con,
        run_id,
        "r012_transportdetail_dummy_findings",
        int(
            con.execute(
                """
                select count(*)
                from dq_findings
                where rule_id = 'R012'
                  and source_table = 'raw_transportdetail'
                  and message like 'Technische Dummy-Loknummer%'
                """
            ).fetchone()[0]
        ),
        "TransportDetail-Dummy-Loks werden symmetrisch als R012 erkannt.",
    )
    _audit(
        con,
        run_id,
        "central_de_usage_segments",
        int(con.execute("select count(*) from core_usage_assignment_segments").fetchone()[0]),
        "Zentrale DE-begrenzte Nutzungssegmente fuer Gate und Export.",
    )

    print(
        "Phase 6C aktiv: belastbare GAPs, symmetrische R012-Dummys, "
        "DE-begrenzte Segmente und Kalte-Abstellung-Kandidaten aufgebaut."
    )
