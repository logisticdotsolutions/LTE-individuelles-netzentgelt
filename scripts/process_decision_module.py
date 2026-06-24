from __future__ import annotations

"""
Netzentgelt MVP - fachliche Prozessentscheidung
================================================

Diese Schicht ordnet die bereits berechneten DE-Nutzungssegmente fachlich den
UKL-/LTE-Prozessarten zu:

- Zuordnung
- Uebergabe / Uebernahmeanfrage
- Ereignis
- keine LTE-Aktion
- manuelle Pruefung

Die bestehende Segmenttabelle wird bewusst nicht strukturell veraendert. Das ist
wichtig, weil der partielle Rebuild vorhandene Tabellen aus der Produktiv-DuckDB
kopiert und anschliessend per INSERT aktualisiert. Zusätzliche Spalten in
core_usage_assignment_segments wuerden diesen schnellen Pfad unnoetig riskieren.
"""

PROCESS_DECISION_MARKER = "NETZENTGELT_PROCESS_DECISION_LAYER_PHASE14A_V1_20260624"


def qident(name: str) -> str:
    """DuckDB-Identifier sicher quoten."""
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
    """Pruefen, ob eine DuckDB-Tabelle existiert."""
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


def _ensure_company_normalization_macro(con) -> None:
    """Konservative Firmennamen-Normalisierung als SQL-Makro bereitstellen."""
    con.execute(
        """
        create or replace macro normalize_company_name(value) as
            regexp_replace(
                lower(
                    replace(
                        replace(
                            replace(
                                replace(
                                    coalesce(cast(value as varchar), ''),
                                    'ä', 'ae'
                                ),
                                'ö', 'oe'
                            ),
                            'ü', 'ue'
                        ),
                        'ß', 'ss'
                    )
                ),
                '[^a-z0-9]+',
                '',
                'g'
            )
        """
    )


def _gate_filter(alias: str = "s") -> str:
    """Gate-Filter analog Exportmodul aufbauen."""
    prefix = f"{alias}." if alias else ""
    return f"""
          and coalesce({prefix}export_blocking_movement_rows, 0) = 0
          and not exists (
                select 1 from dq_export_gate_ru g
                where g.loco_no = {prefix}loco_no
                  and g.performing_ru is not distinct from {prefix}performing_ru
                  and g.coverage_date >= cast({prefix}segment_start_utc as date)
                  and g.coverage_date <= cast({prefix}segment_end_utc as date)
                  and g.gate_status = 'BLOCKED'
          )
          and not exists (
                select 1 from dq_global_export_blockers b
                where b.blocker_date >= cast({prefix}segment_start_utc as date)
                  and b.blocker_date <= cast({prefix}segment_end_utc as date)
                  and b.gate_status = 'BLOCKED'
          )
    """


def _require_tables(con, table_names: list[str]) -> None:
    missing = [name for name in table_names if not table_exists(con, name)]
    if missing:
        raise RuntimeError(
            "Prozessentscheidung kann nicht aufgebaut werden. Fehlende Tabellen: "
            + ", ".join(sorted(missing))
        )


def build_process_decision_layer(con, run_id: str | None = None) -> None:
    """
    Fachliche Prozessentscheidungen und prozessangereicherte Exporte erzeugen.

    Der Aufruf ist idempotent und darf nach build_export_tables() erfolgen.
    """
    _require_tables(
        con,
        [
            "core_usage_assignment_segments",
            "dq_export_gate_ru",
            "dq_global_export_blockers",
        ],
    )
    _ensure_company_normalization_macro(con)
    _build_segment_process_decisions(con, run_id)
    _build_event_process_decisions(con, run_id)
    _rebuild_process_enriched_exports(con)

    segment_count = con.execute("select count(*) from core_process_decisions").fetchone()[0]
    event_count = con.execute("select count(*) from core_event_process_decisions").fetchone()[0]
    print(
        "Prozessentscheidung aktiv: "
        f"Segmente={segment_count}, Ereignisse={event_count}, Marker={PROCESS_DECISION_MARKER}"
    )


def _build_segment_process_decisions(con, run_id: str | None) -> None:
    con.execute(
        """
        create or replace table core_process_decisions as
        with base as (
            select
                s.*,
                normalize_company_name(s.holder_name) as holder_norm,
                normalize_company_name(s.performing_ru) as user_norm,
                case
                    when s.segment_start_utc is null
                      or s.segment_end_utc is null
                      or s.segment_start_utc >= s.segment_end_utc
                      or nullif(trim(s.tfze_or_tens), '') is null
                      or nullif(trim(s.performing_ru), '') is null
                      or coalesce(s.export_blocking_movement_rows, 0) > 0
                        then true
                    else false
                end as requires_manual_review
            from core_usage_assignment_segments s
        ), classified as (
            select
                b.*,
                case
                    when holder_norm like '%ltenetherlands%'
                      or holder_norm like '%ltenl%'
                        then 'LTE_NL'
                    when holder_norm like '%ltegermany%'
                      or holder_norm like '%ltede%'
                      or holder_norm like '%ltege%'
                        then 'LTE_GE'
                    when holder_norm like '%lteholding%'
                      or holder_norm like '%ltegroup%'
                      or holder_norm like '%lte%'
                        then 'LTE_HOLDING'
                    when nullif(holder_norm, '') is not null
                        then 'ANDERE_EVU'
                    else 'UNGEKLAERT'
                end as holder_process_bucket,
                case
                    when user_norm like '%ltenetherlands%'
                      or user_norm like '%ltenl%'
                        then 'LTE_NL'
                    when user_norm like '%ltegermany%'
                      or user_norm like '%ltede%'
                      or user_norm like '%ltege%'
                        then 'LTE_GE'
                    when user_norm like '%lteholding%'
                      or user_norm like '%ltegroup%'
                      or user_norm like '%lte%'
                        then 'LTE_HOLDING'
                    when nullif(user_norm, '') is not null
                        then 'ANDERE_EVU'
                    else 'UNGEKLAERT'
                end as user_process_bucket
            from base b
        ), decision_case as (
            select
                c.*,
                case
                    when requires_manual_review then 'MANUELLE_PRUEFUNG'
                    when holder_process_bucket = 'LTE_NL' and user_process_bucket = 'LTE_NL'
                        then 'UEBERGABE_2_LTE_NL_SELF'
                    when holder_process_bucket = 'LTE_NL' and user_process_bucket = 'LTE_GE'
                        then 'UEBERGABE_2_LTE_NL_AN_LTE_GE'
                    when holder_process_bucket = 'LTE_NL'
                        then 'UEBERGABE_2_LTE_NL_AN_DRITTE'
                    when holder_process_bucket = 'LTE_GE' and user_process_bucket = 'LTE_GE'
                        then 'UEBERGABE_3_LTE_GE_SELF'
                    when holder_process_bucket = 'LTE_GE' and user_process_bucket = 'LTE_NL'
                        then 'UEBERGABE_3_LTE_GE_AN_LTE_NL'
                    when holder_process_bucket = 'LTE_GE'
                        then 'UEBERGABE_3_LTE_GE_AN_DRITTE'
                    when holder_process_bucket = 'LTE_HOLDING' and user_process_bucket = 'LTE_NL'
                        then 'UEBERGABE_4_LTE_HOLDING_AN_LTE_NL'
                    when holder_process_bucket = 'LTE_HOLDING' and user_process_bucket = 'LTE_GE'
                        then 'UEBERGABE_4_LTE_HOLDING_AN_LTE_GE'
                    when holder_process_bucket = 'LTE_HOLDING'
                        then 'UEBERGABE_4_LTE_HOLDING_VERBLEIB'
                    when holder_process_bucket = 'ANDERE_EVU' and user_process_bucket = 'LTE_NL'
                        then 'UEBERGABE_Z_ANDERE_EVU_AN_LTE_NL'
                    when holder_process_bucket = 'ANDERE_EVU' and user_process_bucket = 'LTE_GE'
                        then 'UEBERGABE_Z_ANDERE_EVU_AN_LTE_GE'
                    when holder_process_bucket = 'ANDERE_EVU'
                        then 'ZUORDNUNG_Y_DRITTE_KEINE_LTE_AKTION'
                    else 'MANUELLE_PRUEFUNG'
                end as process_case
            from classified c
        ), decision_flags as (
            select
                d.*,
                case
                    when process_case = 'MANUELLE_PRUEFUNG'
                        then 'MANUELLE_PRUEFUNG'
                    when process_case in (
                        'UEBERGABE_2_LTE_NL_SELF',
                        'UEBERGABE_3_LTE_GE_SELF',
                        'UEBERGABE_4_LTE_HOLDING_VERBLEIB'
                    )
                        then 'ZUORDNUNG'
                    when process_case = 'ZUORDNUNG_Y_DRITTE_KEINE_LTE_AKTION'
                        then 'KEINE_AKTION'
                    else 'UEBERGABE'
                end as process_category,
                case
                    when process_case = 'MANUELLE_PRUEFUNG'
                        then 'Manuell prüfen'
                    when process_case in (
                        'UEBERGABE_2_LTE_NL_SELF',
                        'UEBERGABE_3_LTE_GE_SELF',
                        'UEBERGABE_4_LTE_HOLDING_VERBLEIB'
                    )
                        then 'Keine Aktion'
                    when process_case = 'ZUORDNUNG_Y_DRITTE_KEINE_LTE_AKTION'
                        then 'Keine LTE-Aktion'
                    else 'Meldung erzeugen'
                end as process_action,
                case
                    when process_case = 'MANUELLE_PRUEFUNG'
                        then 'Manuelle Prüfung'
                    when holder_process_bucket = 'LTE_NL'
                        then 'LTE Netherlands'
                    when holder_process_bucket = 'LTE_GE'
                        then 'LTE Germany'
                    when holder_process_bucket = 'LTE_HOLDING'
                        then 'LTE Holding'
                    when holder_process_bucket = 'ANDERE_EVU' and user_process_bucket = 'LTE_NL'
                        then 'LTE Netherlands'
                    when holder_process_bucket = 'ANDERE_EVU' and user_process_bucket = 'LTE_GE'
                        then 'LTE Germany'
                    when holder_process_bucket = 'ANDERE_EVU'
                        then 'Andere EVU'
                    else 'Manuelle Prüfung'
                end as process_owner,
                case
                    when process_case = 'MANUELLE_PRUEFUNG'
                        then 'Manuelle Prüfung'
                    when holder_process_bucket = 'ANDERE_EVU'
                     and user_process_bucket in ('LTE_NL', 'LTE_GE')
                        then 'Übernahmeanfrage'
                    when process_case in (
                        'UEBERGABE_2_LTE_NL_SELF',
                        'UEBERGABE_3_LTE_GE_SELF',
                        'UEBERGABE_4_LTE_HOLDING_VERBLEIB',
                        'ZUORDNUNG_Y_DRITTE_KEINE_LTE_AKTION'
                    )
                        then 'Keine Aktion'
                    else 'Übergabemeldung'
                end as process_message_type
            from decision_case d
        )
        select
            coalesce(?::varchar, run_id) as run_id,
            usage_segment_id,
            loco_no,
            usage_segment_no,
            tfze_or_tens,
            performing_ru,
            holder_name,
            holder_market_partner_id,
            user_vens,
            segment_start_utc,
            segment_end_utc,
            movement_count,
            export_ready_movement_rows,
            export_blocking_movement_rows,
            holder_process_bucket,
            user_process_bucket,
            process_category,
            process_case,
            process_action,
            process_owner,
            process_message_type,
            concat_ws(
                ' | ',
                'Halter-Bucket=' || coalesce(holder_process_bucket, 'UNGEKLAERT'),
                'Nutzer-Bucket=' || coalesce(user_process_bucket, 'UNGEKLAERT'),
                'Fall=' || coalesce(process_case, 'UNGEKLAERT'),
                case when requires_manual_review
                    then 'Unvollständige, blockierte oder zeitlich unplausible Segmentdaten; manuelle Prüfung erforderlich.'
                end,
                case when process_message_type = 'Übergabemeldung'
                    then 'Übergebender ist aus Halter-/Bestandslogik ableitbar; Nutzung erfolgt durch abweichenden Nutzer.'
                end,
                case when process_message_type = 'Übernahmeanfrage'
                    then 'LTE ist Nutzer, Halter liegt außerhalb LTE; Übernahmeprozess durch LTE fachlich naheliegend.'
                end,
                case when process_message_type = 'Keine Aktion'
                    then 'Keine abweichende LTE-Nutzung erkannt; keine Übergabeaktion erforderlich.'
                end
            ) as process_decision_reason,
            current_timestamp as calculated_at_utc,
            '""" || PROCESS_DECISION_MARKER || """'::varchar as phase_marker
        from decision_flags
        order by loco_no, segment_start_utc, usage_segment_no
        """,
        [str(run_id) if run_id is not None else None],
    )


def _build_event_process_decisions(con, run_id: str | None) -> None:
    if not table_exists(con, "core_loco_timeline"):
        con.execute(
            """
            create or replace table core_event_process_decisions (
                run_id varchar,
                loco_no varchar,
                performing_ru varchar,
                event_ts timestamp,
                event_type varchar,
                event_process_case varchar,
                event_process_owner varchar,
                event_decision_reason varchar,
                calculated_at_utc timestamp,
                phase_marker varchar
            )
            """
        )
        return

    con.execute(
        """
        create or replace table core_event_process_decisions as
        with base as (
            select
                c.*,
                normalize_company_name(c.performing_ru) as user_norm,
                case
                    when c.faulty_dir = 'E' then 'einfahrend'
                    when c.faulty_dir = 'A' then 'ausfahrend'
                    when c.clean_dir in ('E', 'E/A') then 'einfahrend'
                    when c.clean_dir = 'A' then 'ausfahrend'
                    when c.report_scope = 'IN_REPORT' then 'netzintern'
                    else 'netzextern'
                end as event_type,
                case
                    when c.faulty_dir = 'E' then c.actual_arrival_ts
                    when c.faulty_dir = 'A' then c.actual_departure_ts
                    when c.clean_dir in ('E', 'E/A') then c.actual_departure_ts
                    when c.clean_dir = 'A' then c.actual_arrival_ts
                    else coalesce(c.sequence_ts, c.actual_departure_ts, c.actual_arrival_ts)
                end as event_ts
            from core_loco_timeline c
            where c.row_type = 'MOVEMENT'
              and nullif(trim(c.loco_no), '') is not null
        ), classified as (
            select
                b.*,
                case
                    when user_norm like '%ltenetherlands%'
                      or user_norm like '%ltenl%'
                        then 'LTE_NL'
                    when user_norm like '%ltegermany%'
                      or user_norm like '%ltede%'
                      or user_norm like '%ltege%'
                        then 'LTE_GE'
                    else 'LTE_HOLDING'
                end as event_owner_bucket
            from base b
        )
        select
            coalesce(?::varchar, run_id) as run_id,
            loco_no,
            performing_ru,
            event_ts,
            event_type,
            case
                when event_owner_bucket = 'LTE_NL' then 'EREIGNIS_5_LTE_NL'
                when event_owner_bucket = 'LTE_GE' then 'EREIGNIS_6_LTE_GE'
                else 'EREIGNIS_7_LTE_HOLDING'
            end as event_process_case,
            case
                when event_owner_bucket = 'LTE_NL' then 'LTE Netherlands'
                when event_owner_bucket = 'LTE_GE' then 'LTE Germany'
                else 'LTE Holding'
            end as event_process_owner,
            'Ereignisprozess aus PerformingRU und Netzstatus abgeleitet: ' || event_type as event_decision_reason,
            current_timestamp as calculated_at_utc,
            '""" || PROCESS_DECISION_MARKER || """'::varchar as phase_marker
        from classified
        where event_ts is not null
        order by loco_no, event_ts
        """,
        [str(run_id) if run_id is not None else None],
    )


def _rebuild_process_enriched_exports(con) -> None:
    gate_filter = _gate_filter("s")

    con.execute(
        f"""
        create or replace table export_zuordnungen as
        select
            s.tfze_or_tens as "TfzE oder tEns*",
            s.segment_start_utc as "Beginn der Zuordnung*",
            s.segment_end_utc as "Ende der Zuordnung",
            coalesce(nullif(s.user_vens, ''), s.performing_ru) as "Nutzer-vEns*",
            coalesce(nullif(s.holder_market_partner_id, ''), s.holder_name) as "Marktpartner ID für Nutzungsüberlassung",
            d.process_category as "Prozesskategorie",
            d.process_case as "Prozessfall",
            d.process_action as "Prozessaktion",
            d.process_owner as "Prozessverantwortung",
            d.process_decision_reason as "Prozessbegründung"
        from core_usage_assignment_segments s
        left join core_process_decisions d
          on d.usage_segment_id is not distinct from s.usage_segment_id
        where s.segment_start_utc is not null
          and s.segment_end_utc is not null
          {gate_filter}
        order by s.loco_no, s.segment_start_utc, s.usage_segment_no
        """
    )

    con.execute(
        f"""
        create or replace table export_nutzungsmeldung as
        select
            s.tfze_or_tens as "TfzE oder tEns*",
            s.segment_start_utc as "Beginn der Nutzung*",
            s.segment_end_utc as "Ende der Nutzung",
            coalesce(nullif(s.user_vens, ''), s.performing_ru) as "Nutzer-vEns*",
            coalesce(nullif(s.holder_market_partner_id, ''), s.holder_name) as "Marktpartner ID für Nutzungsüberlassung*",
            coalesce(d.process_message_type, 'Manuelle Prüfung') as "Übernahmeanfrage oder Übergabemeldung?",
            d.process_category as "Prozesskategorie",
            d.process_case as "Prozessfall",
            d.process_action as "Prozessaktion",
            d.process_owner as "Prozessverantwortung",
            d.process_decision_reason as "Prozessbegründung"
        from core_usage_assignment_segments s
        left join core_process_decisions d
          on d.usage_segment_id is not distinct from s.usage_segment_id
        where s.segment_start_utc is not null
          and s.segment_end_utc is not null
          {gate_filter}
        order by s.loco_no, s.segment_start_utc, s.usage_segment_no
        """
    )
