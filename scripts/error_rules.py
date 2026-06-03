"""
Zentrales Regelwerk für Datenqualitäts-Findings
==============================================

Zweck
-----
Dieses Modul trennt die fachliche Fehlerlogik von Import, Timeline-Bildung
und Export. Dadurch können Regeln unabhängig weiterentwickelt und geprüft
werden.

Grundprinzipien
---------------
- Findings werden ausschließlich für DE-relevante Bewegungen erzeugt.
- Auslandsbewegungen bleiben in core_loco_timeline sichtbar.
- Eine Bewegung kann mehrere atomare Findings erzeugen.
- INFO-Hinweise blockieren weder Bearbeitung noch Export.
- ERROR und MANUAL_REVIEW markieren einen aktiven Prüffall.
- R005 ("Keine Loks") wird bewusst nicht hier erzeugt, weil diese Prüfung
  direkt auf den Rohdaten in app.py erfolgt.
- R008 entfällt: TfzE, tEns und LocomotiveNo werden im MVP als dieselbe
  fachliche Identifikation behandelt.

Referenzdatenauflösung
-----------------------
R007 prüft, ob die PerformingRU-Marktpartner-ID eindeutig aufgelöst werden konnte.
Die Auflösung erfolgt rollenbezogen über:
1. vollständige Mappingtabelle data/01_mapping/market_partner_mapping_import.csv
2. offizielle Marktpartnerliste data/01_mapping/vens liste.csv zur Validierung
3. bestehenden Legacy-Wert aus loco_mapping.csv als temporären Fallback

Nicht eindeutig auflösbare PerformingRU-Schreibweisen werden zusätzlich verdichtet
in dq_unresolved_performing_ru_market_partner_alias.csv ausgegeben.
"""


def sql_lit(value: str) -> str:
    """SQL-Textliteral sicher quoten."""
    return "'" + str(value).replace("'", "''") + "'"


def build_rule_catalog(con) -> None:
    """Dokumentierte Übersicht der aktiven Regeln in DuckDB bereitstellen."""
    con.execute("""
        create or replace table cfg_dq_rule_catalog as
        select * from (
            values
                ('R001', 'TIMELINE', 'INFO/ERROR',
                 'Sequence-Zeitanker fehlt. Erste Bewegung im Zeitfenster ist nur INFO; spätere Fälle bleiben ERROR.',
                 true),
                ('R002', 'TIME_QUALITY', 'INFO',
                 'ActualDeparture fehlt oder ist ungültig.',
                 true),
                ('R003', 'TIME_QUALITY', 'INFO',
                 'ActualArrival fehlt oder ist ungültig.',
                 true),
                ('R004', 'TIME_QUALITY', 'ERROR',
                 'ActualDeparture liegt nach ActualArrival.',
                 true),
                ('R005', 'NO_LOCO_RAW', 'SEPARATE',
                 'Keine-Loks-Logik wird direkt aus den Rohdaten in app.py gebildet.',
                 false),
                ('R006', 'REFERENCE_DATA', 'INFO',
                 'vEns fehlt. PerformingRUs auf der freigegebenen vEns-/tEns-Ausnahmeliste werden nicht gemeldet.',
                 true),
                ('R007', 'REFERENCE_DATA', 'ERROR',
                 'PerformingRU-Marktpartner-ID konnte nicht eindeutig aufgelöst werden. PerformingRUs auf der freigegebenen vEns-/tEns-Ausnahmeliste werden nicht gemeldet.',
                 true),
                ('R008', 'TFZE_IDENT', 'REMOVED',
                 'Entfällt: TfzE, tEns und LocomotiveNo gelten im MVP als dieselbe Identifikation.',
                 false),
                ('R009', 'ASSIGNMENT', 'MANUAL_REVIEW',
                 'DE-relevanter Abschnitt ohne PerformingRU.',
                 true),
                ('R010', 'TIMELINE', 'INFO',
                 'Ortskette endet oder ist unterbrochen. Nachverfolgung endet hier.',
                 true),
                ('R011', 'TIMELINE', 'ERROR',
                 'Zeitliche Überschneidung zur vorherigen Bewegung gleicher Lok.',
                 true)
        ) as rules(
            rule_id,
            rule_group,
            severity_policy,
            description,
            active_flag
        )
    """)


def refresh_core_quality_flags(con) -> None:
    """
    Setzt die Anzeige-Flags der Timeline anhand der zentral erzeugten Findings.

    Dadurch enthält core_loco_timeline keine veraltete Severity-Logik mehr,
    auch wenn die Timeline vor den Findings aufgebaut wird.
    """
    con.execute("""
        create or replace temp table tmp_dq_row_summary as
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
                when sum(case when severity = 'ERROR' then 1 else 0 end) > 0
                    then 'ERROR'
                when sum(case when severity = 'MANUAL_REVIEW' then 1 else 0 end) > 0
                    then 'MANUAL_REVIEW'
                when sum(case when severity = 'WARNING' then 1 else 0 end) > 0
                    then 'WARNING'
                when sum(case when severity = 'INFO' then 1 else 0 end) > 0
                    then 'INFO'
                else ''
            end as dq_severity,

            string_agg(
                rule_id || ': ' || message,
                ' | '
                order by rule_id, message
            ) as dq_message,

            case
                when sum(
                    case
                        when severity in ('ERROR', 'MANUAL_REVIEW')
                            then 1
                        else 0
                    end
                ) > 0
                    then true
                else false
            end as needs_manual_review

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
    """)

    # Zuerst alle zuvor im Core gesetzten Flags neutralisieren.
    con.execute("""
        update core_loco_timeline
        set
            needs_manual_review = false,
            dq_severity = case
                when report_scope = 'NOT_IN_REPORT' then 'INFO'
                else ''
            end,
            dq_message = case
                when report_scope = 'NOT_IN_REPORT'
                    then 'Außerhalb DE; Not in the Report.'
                else ''
            end
    """)

    # Danach die zentral erzeugten Findings zeilenbezogen zurückspielen.
    con.execute("""
        update core_loco_timeline as c
        set
            needs_manual_review = s.needs_manual_review,
            dq_severity = s.dq_severity,
            dq_message = s.dq_message
        from tmp_dq_row_summary as s
        where c.row_type = s.row_type
          and c.loco_no is not distinct from s.loco_no
          and c.transport_number is not distinct from s.transport_number
          and c.performing_ru is not distinct from s.performing_ru
          and c.period_start_utc is not distinct from s.period_start_utc
          and c.period_end_utc is not distinct from s.period_end_utc
          and c.source_table is not distinct from s.source_table
          and c.source_row_id is not distinct from s.source_row_id
    """)


def build_findings(
    con,
    run_id: str,
    home_country_iso: str = "DE",
) -> None:
    """
    Erzeugt dq_findings und synchronisiert danach die Timeline-Flags.

    Die Tabelle enthält atomare Regelverletzungen. Deshalb kann dieselbe
    TransportNumber mehrfach vorkommen, wenn mehrere Regeln greifen.
    """
    home = sql_lit(home_country_iso.upper())
    run = sql_lit(run_id)

    build_rule_catalog(con)

    con.execute(f"""
        create or replace table dq_findings as
        with movement_base as (
            select *
            from core_loco_timeline
            where row_type = 'MOVEMENT'
        ),
        overlap as (
            select
                b.*,
                lag(period_end_utc) over (
                    partition by loco_no
                    order by
                        coalesce(sequence_ts, period_start_utc, period_end_utc) asc nulls last,
                        source_row_id asc
                ) as prev_end
            from movement_base b
        )

        -- R001: Erste Bewegung im geladenen Zeitfenster mit fehlendem
        -- Sequence-Zeitanker nur als INFO behandeln.
        select
            {run} as run_id,
            'INFO' as severity,
            'R001' as rule_id,
            'TIMELINE' as rule_group,
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'First Movement in Timeframe. Sequence-Zeitanker fehlt; Übergang kann aus dem Vortag stammen.' as message,
            'Nur als Zeitfenstergrenze dokumentieren. Keine manuelle Korrektur erforderlich.' as suggested_action,
            'info' as status,
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and movement_sequence_no = 1
          and sequence_ts is null

        union all

        -- R001: Fehlender Sequence-Zeitanker nach der ersten Bewegung
        -- bleibt ein echter Fehler.
        select
            {run},
            'ERROR',
            'R001',
            'TIMELINE',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'Sequence-Zeitanker fehlt.',
            'CleanDir/FaultyDir sowie ActualDeparture/ActualArrival prüfen.',
            'open',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and coalesce(movement_sequence_no, 0) <> 1
          and sequence_ts is null

        union all

        -- R002: Fehlende Abfahrtszeit nur als Hinweis.
        select
            {run},
            'INFO',
            'R002',
            'TIME_QUALITY',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'ActualDeparture fehlt oder ist ungültig.',
            'Nur dokumentieren. Datensatz wird nicht als Fehler gezählt.',
            'info',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and period_start_utc is null

        union all

        -- R003: Fehlende Ankunftszeit nur als Hinweis.
        select
            {run},
            'INFO',
            'R003',
            'TIME_QUALITY',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'ActualArrival fehlt oder ist ungültig.',
            'Nur dokumentieren. Datensatz wird nicht als Fehler gezählt.',
            'info',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and period_end_utc is null

        union all

        -- R004: Fachlich unplausibles Zeitintervall bleibt ERROR.
        select
            {run},
            'ERROR',
            'R004',
            'TIME_QUALITY',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'ActualDeparture liegt nach ActualArrival.',
            'Zeitintervall fachlich korrigieren.',
            'open',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and period_start_utc is not null
          and period_end_utc is not null
          and period_start_utc > period_end_utc

        -- R005 entfällt hier bewusst:
        -- Die Keine-Loks-Prüfung greift direkt auf die Rohdaten zu.

        union all

        -- R006: Fehlende vEns nur als Hinweis.
        select
            {run},
            'INFO',
            'R006',
            'REFERENCE_DATA',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'vEns fehlt.',
            'vEns-Referenzdaten prüfen oder ergänzen.',
            'info',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and (user_vens is null or user_vens = '')
          and coalesce(exempt_vens, false) = false

        union all

        -- R007: Marktpartner-ID ist weiterhin exportrelevant.
        -- Künftig soll sie aus vens_liste.csv aufgelöst werden.
        select
            {run},
            'ERROR',
            'R007',
            'REFERENCE_DATA',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'PerformingRU-Marktpartner-ID konnte nicht eindeutig aufgelöst werden.',
            'market_partner_mapping_import.csv prüfen und Active_Flag nach fachlicher Freigabe auf Y setzen. Details siehe dq_unresolved_performing_ru_market_partner_alias.csv.',
            'open',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and (performing_ru_marktpartner_id is null or performing_ru_marktpartner_id = '')
          and coalesce(vens_tens_exception_flag, false) = false

        -- R008 entfällt vollständig:
        -- tfze_or_tens = loco_no ist fachlich zulässig.

        union all

        -- R009: DE-relevanter Abschnitt ohne PerformingRU.
        select
            {run},
            'MANUAL_REVIEW',
            'R009',
            'ASSIGNMENT',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            'DE-relevanter Abschnitt ohne PerformingRU.',
            'PerformingRU fachlich prüfen und ergänzen.',
            'open',
            source_table,
            source_row_id
        from movement_base
        where report_scope = 'IN_REPORT'
          and (performing_ru is null or performing_ru = '')

        union all

        -- R010: GAP nur als Info. Die Nachverfolgung endet an dieser Stelle.
        select
            {run},
            'INFO',
            'R010',
            'TIMELINE',
            loco_no,
            transport_number,
            performing_ru,
            row_type,
            movement_sequence_no,
            period_start_utc,
            period_end_utc,
            dq_message,
            'Nur als Ende der nachvollziehbaren Ortskette dokumentieren.',
            'info',
            source_table,
            source_row_id
        from core_loco_timeline
        where row_type = 'GAP'
          and (
                upper(coalesce(origin_country_iso, '')) = {home}
             or upper(coalesce(destination_country_iso, '')) = {home}
          )

        union all

        -- R011: Vorläufig unverändert lassen, bis die fachliche
        -- Überschneidungslogik separat präzisiert wird.
        select
            {run},
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
            'Zeitliche Überschneidung zur vorherigen Bewegung gleicher Lok erkannt.',
            'Überlappung prüfen. Fachliche Präzisierung der Regel R011 folgt separat.',
            'open',
            source_table,
            source_row_id
        from overlap
        where report_scope = 'IN_REPORT'
          and prev_end is not null
          and period_start_utc < prev_end
    """)

    refresh_core_quality_flags(con)

    finding_count = con.execute(
        "select count(*) from dq_findings"
    ).fetchone()[0]

    error_count = con.execute(
        "select count(*) from dq_findings where severity = 'ERROR'"
    ).fetchone()[0]

    info_count = con.execute(
        "select count(*) from dq_findings where severity = 'INFO'"
    ).fetchone()[0]

    manual_review_count = con.execute(
        "select count(*) from dq_findings where severity = 'MANUAL_REVIEW'"
    ).fetchone()[0]

    print(
        "DQ-Regelwerk ausgeführt: "
        f"{finding_count} Findings | "
        f"Errors={error_count} | "
        f"Manual Reviews={manual_review_count} | "
        f"Infos={info_count}"
    )
