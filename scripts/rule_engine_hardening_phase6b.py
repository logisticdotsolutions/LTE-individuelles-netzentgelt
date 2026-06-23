from __future__ import annotations

"""
Netzentgelt MVP - Rule Engine Hardening Phase 6B
================================================

Konsolidierte Korrekturschicht fuer bestaetigte P0-Fehler der Regelengine.

Die Schicht wird innerhalb des temporaeren DuckDB-Neuaufbaus ausgefuehrt. Die
Original-CSVs bleiben unveraendert. Sie korrigiert insbesondere:

- ANE-tEns/Halter-Aufloesung anhand des Halters statt anhand der PerformingRU,
- fachlich erlaubte Fallbacks fuer Nutzer-vEns und Halter-Marktpartner-ID,
- sichtbare blockierende Findings statt unsichtbarer export_ready-Sperren,
- einheitliche R011-Ermittlung anhand echter Intervallschnittmengen,
- 24h-Toleranz bei der blockierenden Wirkung nicht exportfaehiger Bewegungen.
"""

from datetime import datetime, timezone

from error_rules import qident, table_exists  # noqa: F401 (re-exported for phase6c)

PHASE_ID = "NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6B_V1_20260608"


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


def _cutoff_utc(con):
    if not table_exists(con, "dq_run_metadata"):
        return None
    row = con.execute(
        "select max(error_cutoff_utc) from dq_run_metadata"
    ).fetchone()
    return row[0] if row else None


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create table if not exists dq_rule_engine_hardening_audit (
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
        insert into dq_rule_engine_hardening_audit values (
            ?, ?, ?, ?, current_timestamp, ?
        )
        """,
        [PHASE_ID, str(run_id), str(metric), int(value or 0), str(comment)],
    )


def apply_core_assignment_fallbacks(con, run_id: str) -> None:
    """
    Korrigiert die Marktpartner-Ableitung im Core vor der Finding-Berechnung.

    Fachliche MVP-Fallbacks gemaess abgestimmter Exportregel:
    - Nutzer-vEns: PerformingRU, solange kein passendes Mapping existiert.
    - Halter-Marktpartner-ID: Haltername, solange kein passendes Mapping existiert.
    """
    if not table_exists(con, "core_loco_timeline"):
        raise RuntimeError("core_loco_timeline fehlt. Phase 6B kann nicht ausgefuehrt werden.")

    con.execute(
        """
        create or replace temp table tmp_phase6b_holder_resolution as
        select
            c.source_table,
            c.source_row_id,
            c.loco_no,
            c.period_start_utc,
            c.period_end_utc,
            coalesce(
                holder_mapping.market_partner_id,
                holder_direct.market_partner_id,
                nullif(trim(c.holder_name), '')
            ) as resolved_holder_market_partner_id,
            case
                when holder_mapping.market_partner_id is not null
                    then 'MAPPING_IMPORT'
                when holder_direct.market_partner_id is not null
                    then 'OFFICIAL_NAME_EXACT'
                when nullif(trim(c.holder_name), '') is not null
                    then 'FALLBACK_HOLDER_NAME'
                else 'UNRESOLVED'
            end as resolved_holder_market_partner_id_source
        from core_loco_timeline c
        left join cfg_market_partner_mapping_effective holder_mapping
          on holder_mapping.role_code = 'ANE_TENS'
         and holder_mapping.source_value_normalized = normalize_company_name(c.holder_name)
        left join cfg_market_partner_role_effective holder_direct
          on holder_direct.role_code = 'ANE_TENS'
         and holder_direct.company_name_normalized = normalize_company_name(c.holder_name)
        where c.row_type = 'MOVEMENT'
        """
    )

    wrong_before = int(
        con.execute(
            """
            select count(*)
            from core_loco_timeline c
            join tmp_phase6b_holder_resolution r
              on r.source_table is not distinct from c.source_table
             and r.source_row_id is not distinct from c.source_row_id
             and r.loco_no is not distinct from c.loco_no
             and r.period_start_utc is not distinct from c.period_start_utc
             and r.period_end_utc is not distinct from c.period_end_utc
            where c.row_type = 'MOVEMENT'
              and c.holder_market_partner_id is distinct from r.resolved_holder_market_partner_id
            """
        ).fetchone()[0]
    )

    con.execute(
        """
        update core_loco_timeline as c
        set
            holder_market_partner_id = r.resolved_holder_market_partner_id,
            holder_market_partner_id_source = r.resolved_holder_market_partner_id_source,
            user_vens = coalesce(
                nullif(trim(c.user_vens), ''),
                nullif(trim(c.performing_ru), '')
            )
        from tmp_phase6b_holder_resolution r
        where c.row_type = 'MOVEMENT'
          and r.source_table is not distinct from c.source_table
          and r.source_row_id is not distinct from c.source_row_id
          and r.loco_no is not distinct from c.loco_no
          and r.period_start_utc is not distinct from c.period_start_utc
          and r.period_end_utc is not distinct from c.period_end_utc
        """
    )

    fallback_user_vens = int(
        con.execute(
            """
            select count(*)
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and nullif(trim(user_vens), '') is not null
              and nullif(trim(performing_ru), '') is not null
              and trim(user_vens) = trim(performing_ru)
            """
        ).fetchone()[0]
    )
    holder_fallbacks = int(
        con.execute(
            """
            select count(*)
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and holder_market_partner_id_source = 'FALLBACK_HOLDER_NAME'
            """
        ).fetchone()[0]
    )

    _audit(
        con,
        run_id,
        "corrected_holder_market_partner_rows",
        wrong_before,
        "Halter-Aufloesung wurde anhand holder_name statt performing_ru aktualisiert.",
    )
    _audit(
        con,
        run_id,
        "fallback_user_vens_rows",
        fallback_user_vens,
        "Nutzer-vEns verwendet PerformingRU als abgestimmten MVP-Fallback.",
    )
    _audit(
        con,
        run_id,
        "fallback_holder_name_rows",
        holder_fallbacks,
        "Halter-Marktpartner-ID verwendet Haltername als abgestimmten MVP-Fallback.",
    )


def _refresh_core_quality_flags(con) -> None:
    """Findings zeilenbezogen erneut in die Timeline zurueckspielen."""
    con.execute(
        """
        create or replace temp table tmp_phase6b_dq_row_summary as
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
            string_agg(
                rule_id || ': ' || message,
                ' | '
                order by rule_id, message
            ) as dq_message,
            count(*) filter (where severity in ('ERROR', 'MANUAL_REVIEW')) > 0
                as needs_manual_review
        from dq_findings
        group by
            row_type,
            loco_no,
            transport_number,
            performing_ru,
            period_start_utc,
            period_end_utc,
            source_table,
            source_row_id
        """
    )

    con.execute(
        """
        update core_loco_timeline
        set
            needs_manual_review = false,
            dq_severity = case when report_scope = 'NOT_IN_REPORT' then 'INFO' else '' end,
            dq_message = case
                when report_scope = 'NOT_IN_REPORT' then 'Außerhalb DE; Not in the Report.'
                else ''
            end
        """
    )

    con.execute(
        """
        update core_loco_timeline as c
        set
            needs_manual_review = s.needs_manual_review,
            dq_severity = s.dq_severity,
            dq_message = s.dq_message
        from tmp_phase6b_dq_row_summary s
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


def harden_findings_and_export_policy(
    con,
    run_id: str,
    loco_filter: "frozenset[str] | None" = None,
) -> None:
    """Konsolidiert R011, sichtbare Sperrgruende und die 24h-Toleranz.

    loco_filter: None → Vollneubau. frozenset → nur betroffene Loks.
    """
    if loco_filter is not None and len(loco_filter) == 0:
        return

    if not table_exists(con, "dq_findings"):
        raise RuntimeError("dq_findings fehlt. Phase 6B kann nicht ausgefuehrt werden.")

    cutoff = _cutoff_utc(con)
    if cutoff is None:
        raise RuntimeError("dq_run_metadata.error_cutoff_utc fehlt. Phase 6B bricht sicher ab.")

    _is_partial = loco_filter is not None
    _loco_list = list(loco_filter) if _is_partial else None
    _lf = "and loco_no = ANY(?)" if _is_partial else ""
    _lf_params = [_loco_list] if _is_partial else []

    # R011: alte LAG-basierte Ergebnisse entfernen und anhand echter
    # Intervallschnittmengen neu aufbauen. Jede spaetere betroffene Bewegung
    # erhaelt genau ein atomisches Finding mit allen Referenztransporten.
    old_r011 = int(
        con.execute(f"select count(*) from dq_findings where rule_id = 'R011' {_lf}", _lf_params).fetchone()[0]
    )
    con.execute(f"delete from dq_findings where rule_id = 'R011' {_lf}", _lf_params)
    _ensure_column(con, "dq_findings", "overlap_with_transport_number", "varchar")

    con.execute(
        f"""
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        with eligible as (
            select *
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and period_start_utc is not null
              and period_end_utc is not null
              and period_end_utc > period_start_utc
              and period_start_utc <= ?
              {_lf}
        ), actual_overlap as (
            select
                b.source_table,
                b.source_row_id,
                b.loco_no,
                b.transport_number,
                b.performing_ru,
                b.row_type,
                b.movement_sequence_no,
                b.period_start_utc,
                b.period_end_utc,
                string_agg(
                    distinct coalesce(a.transport_number, '-'),
                    ' | '
                    order by coalesce(a.transport_number, '-')
                ) as overlap_with_transport_number
            from eligible b
            join eligible a
              on a.loco_no = b.loco_no
             and (
                    a.period_start_utc < b.period_start_utc
                 or (
                        a.period_start_utc = b.period_start_utc
                    and coalesce(a.source_row_id, -1) < coalesce(b.source_row_id, -1)
                 )
             )
             and a.period_start_utc < b.period_end_utc
             and b.period_start_utc < a.period_end_utc
            group by
                b.source_table,
                b.source_row_id,
                b.loco_no,
                b.transport_number,
                b.performing_ru,
                b.row_type,
                b.movement_sequence_no,
                b.period_start_utc,
                b.period_end_utc
        )
        select
            ?,
            'ERROR',
            'R011',
            'TIMELINE',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'Zeitliche Überschneidung mit vorheriger Bewegung erkannt. Referenztransport(e): '
                || overlap_with_transport_number || '.',
            'Tatsächliche Intervallschnittmenge prüfen und fehlerhafte Bewegung korrigieren.',
            'open',
            source_table,
            source_row_id,
            overlap_with_transport_number
        from actual_overlap
        """,
        [cutoff] + _lf_params + [str(run_id)],
    )

    new_r011 = int(
        con.execute("select count(*) from dq_findings where rule_id = 'R011'").fetchone()[0]
    )

    # R002/R003 sind innerhalb der 24h-Toleranz nur INFO. Nach Ablauf der
    # Toleranz werden fehlende Zeitgrenzen zu bearbeitbaren MANUAL_REVIEW-Faellen.
    con.execute(
        f"""
        update dq_findings
        set
            severity = 'MANUAL_REVIEW',
            status = 'open',
            suggested_action = 'Zeitwert in RailCube prüfen und ergänzen. Danach lokale Prüfung neu ausführen.'
        where rule_id in ('R002', 'R003')
          and coalesce(period_start_utc, period_end_utc) is not null
          and coalesce(period_start_utc, period_end_utc) <= ?
          {_lf}
        """,
        [cutoff] + _lf_params,
    )

    # R013: fehlender Halter war bisher eine unsichtbare Exportsperre.
    con.execute(
        f"""
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        select
            ?,
            'MANUAL_REVIEW',
            'R013',
            'ASSIGNMENT',
            c.loco_no,
            c.transport_number,
            c.performing_ru,
            c.row_type,
            c.movement_sequence_no,
            c.period_start_utc,
            c.period_end_utc,
            'Halter der Lok fehlt. Marktpartner-ID für Nutzungsüberlassung kann nicht abgeleitet werden.',
            'Halter in RailCube prüfen und ergänzen.',
            'open',
            c.source_table,
            c.source_row_id,
            null::varchar
        from core_loco_timeline c
        where c.row_type = 'MOVEMENT'
          and c.report_scope = 'IN_REPORT'
          and nullif(trim(c.holder_name), '') is null
          and coalesce(c.period_start_utc, c.period_end_utc) is not null
          and coalesce(c.period_start_utc, c.period_end_utc) <= ?
          {_lf}
          and not exists (
                select 1 from dq_findings f
                where f.rule_id = 'R013'
                  and f.source_table is not distinct from c.source_table
                  and f.source_row_id is not distinct from c.source_row_id
          )
        """,
        [str(run_id), cutoff] + _lf_params,
    )

    # R014: technische Dummy-Lok muss auch zeilenbezogen sichtbar sein.
    con.execute(
        f"""
        insert into dq_findings (
            run_id, severity, rule_id, rule_group, loco_no, transport_number,
            performing_ru, row_type, movement_sequence_no, period_start_utc,
            period_end_utc, message, suggested_action, status, source_table,
            source_row_id, overlap_with_transport_number
        )
        select
            ?,
            'ERROR',
            'R014',
            'NO_LOCO_RAW',
            c.loco_no,
            c.transport_number,
            c.performing_ru,
            c.row_type,
            c.movement_sequence_no,
            c.period_start_utc,
            c.period_end_utc,
            'Technische Dummy-Loknummer 00000000000-0 erkannt.',
            'Echte Loknummer in RailCube prüfen und ergänzen.',
            'open',
            c.source_table,
            c.source_row_id,
            null::varchar
        from core_loco_timeline c
        where c.row_type = 'MOVEMENT'
          and c.report_scope = 'IN_REPORT'
          and trim(coalesce(c.loco_no, '')) = '00000000000-0'
          and coalesce(c.period_start_utc, c.period_end_utc) is not null
          and coalesce(c.period_start_utc, c.period_end_utc) <= ?
          {_lf}
          and not exists (
                select 1 from dq_findings f
                where f.rule_id = 'R014'
                  and f.source_table is not distinct from c.source_table
                  and f.source_row_id is not distinct from c.source_row_id
          )
        """,
        [str(run_id), cutoff] + _lf_params,
    )

    # Dokumentation der neuen sichtbaren Regeln.
    con.execute(
        """
        delete from cfg_dq_rule_catalog where rule_id in ('R013', 'R014')
        """
    )
    con.execute(
        """
        insert into cfg_dq_rule_catalog values
            ('R013', 'ASSIGNMENT', 'MANUAL_REVIEW',
             'Halter der Lok fehlt. Marktpartner-ID für Nutzungsüberlassung kann nicht abgeleitet werden.', true),
            ('R014', 'NO_LOCO_RAW', 'ERROR',
             'Technische Dummy-Loknummer 00000000000-0 ist in der Lok-Zeitachse sichtbar.', true)
        """
    )
    con.execute(
        """
        update cfg_dq_rule_catalog
        set severity_policy = 'INFO innerhalb 24h / MANUAL_REVIEW danach'
        where rule_id in ('R002', 'R003')
        """
    )

    _refresh_core_quality_flags(con)

    _ensure_column(con, "core_loco_timeline", "export_blocking", "boolean")

    # Fachlich abgestimmte MVP-Exportregel:
    # - vEns darf auf PerformingRU zurueckfallen.
    # - Halter-MP-ID darf auf Haltername zurueckfallen.
    # - offene ERROR/MANUAL_REVIEW-Faelle verhindern die Exportfaehigkeit.
    con.execute(
        f"""
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
        {"where loco_no = ANY(?)" if _is_partial else ""}
        """,
        _lf_params,
    )

    # Nicht exportfaehige frische Bewegungen innerhalb der 24h-Toleranz bleiben
    # sichtbar, sperren aber den Lok-Tag noch nicht voreilig.
    con.execute(
        f"""
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
        {"where loco_no = ANY(?)" if _is_partial else ""}
        """,
        [cutoff] + _lf_params,
    )

    con.execute(
        """
        create or replace table dq_rule_engine_hardening_blockers as
        select
            run_id,
            loco_no,
            transport_number,
            performing_ru,
            period_start_utc,
            period_end_utc,
            export_ready,
            export_blocking,
            dq_severity,
            dq_message,
            concat_ws(
                ' | ',
                case when nullif(trim(loco_no), '') is null then 'Loknummer fehlt' end,
                case when trim(coalesce(loco_no, '')) = '00000000000-0' then 'Technische Dummy-Loknummer' end,
                case when sequence_ts is null then 'Sequence-Zeitanker fehlt' end,
                case when period_start_utc is null then 'ActualDeparture fehlt' end,
                case when period_end_utc is null then 'ActualArrival fehlt' end,
                case when period_start_utc > period_end_utc then 'Zeitintervall unplausibel' end,
                case when nullif(trim(performing_ru), '') is null then 'Nutzendes EVU fehlt' end,
                case when nullif(trim(holder_market_partner_id), '') is null then 'Halter fehlt' end,
                case when coalesce(needs_manual_review, false) then 'Offener Prüffall' end
            ) as blocker_reason,
            source_table,
            source_row_id
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and coalesce(export_blocking, false) = true
        order by period_start_utc, loco_no, transport_number
        """
    )

    blocking_rows = int(
        con.execute(
            "select count(*) from dq_rule_engine_hardening_blockers"
        ).fetchone()[0]
    )
    pending_rows = int(
        con.execute(
            """
            select count(*)
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and coalesce(export_ready, false) = false
              and coalesce(export_blocking, false) = false
            """
        ).fetchone()[0]
    )

    _audit(con, run_id, "old_r011_findings", old_r011, "Vor Phase-6B-Neuberechnung vorhandene R011-Findings.")
    _audit(con, run_id, "new_r011_findings", new_r011, "R011 anhand echter Intervallschnittmengen neu erzeugt.")
    _audit(con, run_id, "hard_blocking_movement_rows", blocking_rows, "Sichtbare blockierende Movements nach Phase 6B.")
    _audit(con, run_id, "pending_24h_tolerance_rows", pending_rows, "Nicht exportfaehige, aber innerhalb der Toleranz noch nicht blockierende Movements.")

    print(
        "Rule Engine Hardening Phase 6B angewandt: "
        f"R011 alt={old_r011}, neu={new_r011} | "
        f"blockierende Movements={blocking_rows} | "
        f"24h-Toleranz={pending_rows}."
    )
