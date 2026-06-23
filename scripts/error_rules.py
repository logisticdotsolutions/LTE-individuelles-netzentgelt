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
- R005 bleibt als ältere separate UI-Prüfung erhalten.
- R012 übernimmt fehlende oder technische Loknummern zentral in dq_findings.
  Dafür wird pro Quelle und TransportNumber nur ein verdichteter Prüffall erzeugt.
- Fehlende vEns-/tEns-Zuordnungen bleiben für Exporttests sichtbar, erzeugen im
  MVP aber bewusst keine Findings.
- R008 entfällt: TfzE, tEns und LocomotiveNo werden im MVP als dieselbe
  fachliche Identifikation behandelt.
"""


def sql_lit(value: str) -> str:
    """SQL-Textliteral sicher quoten."""
    return "'" + str(value).replace("'", "''") + "'"


def qident(name: str) -> str:
    """SQL-Identifier sicher quoten."""
    return '"' + str(name).replace('"', '""') + '"'


def _table_exists(con, table_name: str) -> bool:
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


table_exists = _table_exists


def _columns(con, table_name: str) -> list[str]:
    """Spalten einer DuckDB-Tabelle auslesen."""
    return [
        row[0]
        for row in con.execute(
            f"describe {qident(table_name)}"
        ).fetchall()
    ]


def _pick_column(
    available_columns: list[str],
    candidates: list[str],
) -> str | None:
    """Erste tatsächlich vorhandene Spalte aus einer Kandidatenliste wählen."""
    by_lower = {
        column.lower(): column
        for column in available_columns
    }

    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]

    return None


def _text_expr(column_name: str | None) -> str:
    """Bereinigten SQL-Textausdruck für eine optionale Spalte liefern."""
    if column_name is None:
        return "NULL"

    return (
        "nullif(trim(cast("
        + qident(column_name)
        + " as varchar)), '')"
    )


def _de_relevance_expr(
    available_columns: list[str],
) -> str:
    """
    DE-Relevanz strikt über OriginCountryISO oder DestinationCountryISO bilden.

    Country wird ausschließlich als technischer Fallback verwendet, wenn in
    der jeweiligen Rohdatei weder ein Origin- noch ein Destination-Länderfeld
    vorhanden ist. Dadurch erzeugen reine Auslandsbewegungen keine Findings.
    """
    origin_column = _pick_column(
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

    destination_column = _pick_column(
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

    if origin_column is None and destination_column is None:
        country_column = _pick_column(
            available_columns,
            ["Country"],
        )
        country_expr = _text_expr(country_column)
        return (
            "(upper(coalesce("
            + country_expr
            + ", '')) = 'DE')"
        )

    origin_expr = _text_expr(origin_column)
    destination_expr = _text_expr(destination_column)

    return (
        "(upper(coalesce("
        + origin_expr
        + ", '')) = 'DE' "
        + "or upper(coalesce("
        + destination_expr
        + ", '')) = 'DE')"
    )


def _get_error_cutoff_utc(con, run_id: str) -> tuple[str, str]:
    """
    Stabilen Snapshot-Zeitpunkt und fachlichen 24h-Cutoff liefern.

    source_snapshot_at_utc stammt aus dem nach vollständigem Azure-Download
    geschriebenen Manifest. Für ältere Datenbankstände bleibt imported_at_utc
    als defensiver Fallback erhalten.
    NETZENTGELT_HARDENING_V1_20260607
    """
    raw_import_columns = {
        column.lower()
        for column in _columns(con, "raw_import_run")
    }

    if "source_snapshot_at_utc" in raw_import_columns:
        snapshot_expression = (
            "coalesce("
            "try_cast(source_snapshot_at_utc as timestamp), "
            "try_cast(imported_at_utc as timestamp)"
            ")"
        )
    else:
        snapshot_expression = "try_cast(imported_at_utc as timestamp)"

    source_snapshot_at_utc = con.execute(
        f"""
        select max({snapshot_expression})
        from raw_import_run
        where run_id = ?
          and status = 'imported'
        """,
        [run_id],
    ).fetchone()[0]

    if source_snapshot_at_utc is None:
        source_snapshot_at_utc = con.execute(
            "select current_timestamp"
        ).fetchone()[0]

    error_cutoff_utc = con.execute(
        "select try_cast(? as timestamp) - interval '1 day'",
        [str(source_snapshot_at_utc)],
    ).fetchone()[0]

    return str(source_snapshot_at_utc), str(error_cutoff_utc)


def build_r012_raw_findings(
    con,
    run_id: str,
    error_cutoff_utc: str,
) -> None:
    """
    R012 direkt aus den Rohdaten bilden.

    NETZENTGELT_CANCELLED_HOTFIX_V2_20260607: zentral stornierte
    Transporte werden vor der Verdichtung vollständig ausgeschlossen.

    Fehlende oder technische Loknummern werden bewusst vor dem Core-Aggregat
    geprüft. Die Fehlerqueue erhält dabei pro Quelle und TransportNumber
    nur einen verdichteten Prüffall. Mehrere betroffene Rohdatenzeilen
    desselben Transports werden im Meldungstext ausgewiesen, aber nicht als
    separate Queue-Einträge vervielfacht.
    """
    error_cutoff = sql_lit(error_cutoff_utc)

    con.execute("""
        create or replace temp table tmp_r012_findings (
            run_id varchar,
            severity varchar,
            rule_id varchar,
            rule_group varchar,
            loco_no varchar,
            transport_number varchar,
            performing_ru varchar,
            row_type varchar,
            movement_sequence_no bigint,
            period_start_utc timestamp,
            period_end_utc timestamp,
            message varchar,
            suggested_action varchar,
            status varchar,
            source_table varchar,
            source_row_id bigint
        )
    """)

    # --------------------------------------------------
    # TransportDetail.csv
    # --------------------------------------------------
    td_table = "raw_transportdetail"

    if _table_exists(con, td_table):
        td_columns = _columns(con, td_table)

        td_actual_departure = _text_expr(
            _pick_column(td_columns, ["ActualDeparture"])
        )
        td_first_loco = _text_expr(
            _pick_column(td_columns, ["FirstLocomotiveNo"])
        )
        td_movement_type = _text_expr(
            _pick_column(td_columns, ["MovementType"])
        )
        td_transport_number = _text_expr(
            _pick_column(
                td_columns,
                ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
            )
        )
        td_de_relevant = _de_relevance_expr(td_columns)

        if (
            td_actual_departure != "NULL"
            and td_first_loco != "NULL"
            and td_movement_type != "NULL"
        ):
            con.execute(
                f"""
                insert into tmp_r012_findings
                with raw_rows as (
                    select
                        row_number() over () as source_row_id,
                        {td_transport_number} as transport_number,
                        try_cast({td_actual_departure} as timestamp) as period_start_utc,
                        {td_de_relevant} as is_de_relevant,
                        {td_movement_type} as movement_type,
                        {td_first_loco} as first_loco_no
                    from {qident(td_table)}
                    where not exists (
                        select 1
                        from cfg_excluded_cancelled_transports excluded
                        where excluded.transport_number = {td_transport_number}
                    )
                ),
                raw_matches as (
                    select *
                    from raw_rows
                    where is_de_relevant
                      and lower(coalesce(movement_type, '')) = 'train movement'
                      and period_start_utc is not null
                      and period_start_utc <= try_cast({error_cutoff} as timestamp)
                      and first_loco_no is null
                ),
                grouped as (
                    select
                        transport_number,
                        min(period_start_utc) as period_start_utc,
                        min(source_row_id) as source_row_id,
                        count(*) as affected_raw_rows
                    from raw_matches
                    group by
                        transport_number,
                        case
                            when transport_number is null then source_row_id
                            else null
                        end
                )
                select
                    {sql_lit(run_id)} as run_id,
                    'ERROR' as severity,
                    'R012' as rule_id,
                    'NO_LOCO_RAW' as rule_group,
                    null::varchar as loco_no,
                    transport_number,
                    null::varchar as performing_ru,
                    'RAW_TRANSPORT_DETAIL' as row_type,
                    null::bigint as movement_sequence_no,
                    period_start_utc,
                    null::timestamp as period_end_utc,
                    'Loknummer fehlt: DE-relevanter Train movement ohne FirstLocomotiveNo. Betroffene Rohdatenzeilen: '
                        || cast(affected_raw_rows as varchar) || '.' as message,
                    'Transportplanung prüfen und FirstLocomotiveNo ergänzen.' as suggested_action,
                    'open' as status,
                    {sql_lit(td_table)} as source_table,
                    source_row_id
                from grouped
                """
            )

    # --------------------------------------------------
    # LocomotiveMovement.csv
    # --------------------------------------------------
    lm_table = "raw_locomotivemovement"

    if _table_exists(con, lm_table):
        lm_columns = _columns(con, lm_table)

        lm_loco_no = _text_expr(
            _pick_column(lm_columns, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"])
        )
        lm_locomotive_type = _text_expr(
            _pick_column(lm_columns, ["LocomotiveType"])
        )
        lm_transport_number = _text_expr(
            _pick_column(
                lm_columns,
                ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
            )
        )
        lm_performing_ru = _text_expr(
            _pick_column(
                lm_columns,
                [
                    "CurrentContractant",
                    "CALPerformingRU",
                    "PerformingRU",
                    "PerformingRailwayUndertaking",
                    "RailwayUndertaking",
                    "Carrier",
                    "ProductionCompany",
                ],
            )
        )
        lm_actual_departure = _text_expr(
            _pick_column(lm_columns, ["ActualDeparture", "LocomotiveActualDeparture"])
        )
        lm_actual_arrival = _text_expr(
            _pick_column(lm_columns, ["ActualArrival", "LocomotiveActualArrival"])
        )
        lm_de_relevant = _de_relevance_expr(lm_columns)

        if lm_loco_no != "NULL":
            con.execute(
                f"""
                insert into tmp_r012_findings
                with raw_rows as (
                    select
                        row_number() over () as source_row_id,
                        {lm_loco_no} as loco_no,
                        {lm_transport_number} as transport_number,
                        {lm_performing_ru} as performing_ru,
                        try_cast({lm_actual_departure} as timestamp) as period_start_utc,
                        try_cast({lm_actual_arrival} as timestamp) as period_end_utc,
                        {lm_de_relevant} as is_de_relevant,
                        case when {lm_loco_no} is null then true else false end as has_missing_loco,
                        case when {lm_loco_no} = '00000000000-0' then true else false end as has_technical_loco,
                        case
                            when upper(coalesce({lm_locomotive_type}, '')) like '%DUMMY%'
                                then true
                            else false
                        end as has_dummy_type
                    from {qident(lm_table)}
                    where not exists (
                        select 1
                        from cfg_excluded_cancelled_transports excluded
                        where excluded.transport_number = {lm_transport_number}
                    )
                ),
                raw_matches as (
                    select *
                    from raw_rows
                    where is_de_relevant
                      and coalesce(period_start_utc, period_end_utc) is not null
                      and coalesce(period_start_utc, period_end_utc) <= try_cast({error_cutoff} as timestamp)
                      and (has_missing_loco or has_technical_loco or has_dummy_type)
                ),
                grouped as (
                    select
                        max(loco_no) as loco_no,
                        transport_number,
                        max(performing_ru) as performing_ru,
                        min(period_start_utc) as period_start_utc,
                        max(period_end_utc) as period_end_utc,
                        bool_or(has_missing_loco) as has_missing_loco,
                        bool_or(has_technical_loco) as has_technical_loco,
                        bool_or(has_dummy_type) as has_dummy_type,
                        min(source_row_id) as source_row_id,
                        count(*) as affected_raw_rows
                    from raw_matches
                    group by
                        transport_number,
                        case
                            when transport_number is null then source_row_id
                            else null
                        end
                )
                select
                    {sql_lit(run_id)} as run_id,
                    'ERROR' as severity,
                    'R012' as rule_id,
                    'NO_LOCO_RAW' as rule_group,
                    loco_no,
                    transport_number,
                    performing_ru,
                    'RAW_LOCOMOTIVE_MOVEMENT' as row_type,
                    null::bigint as movement_sequence_no,
                    period_start_utc,
                    period_end_utc,
                    case
                        when has_missing_loco
                            then 'Loknummer fehlt in LocomotiveMovement.csv.'
                        when has_technical_loco
                            then 'Technische Dummy-Loknummer 00000000000-0 erkannt.'
                        else 'LocomotiveType enthält Dummy.'
                    end
                    || ' Betroffene Rohdatenzeilen: '
                    || cast(affected_raw_rows as varchar)
                    || '.' as message,
                    'Loknummer beziehungsweise Dummy-Zuordnung fachlich prüfen und korrigieren.' as suggested_action,
                    'open' as status,
                    {sql_lit(lm_table)} as source_table,
                    source_row_id
                from grouped
                """
            )

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
                ('R006', 'REFERENCE_DATA', 'IGNORED',
                 'Fehlende vEns werden im MVP nicht als Finding bewertet.',
                 false),
                ('R007', 'REFERENCE_DATA', 'IGNORED',
                 'Fehlende ANE_TENS-/Marktpartner-Zuordnungen werden im MVP nicht als Finding bewertet.',
                 false),
                ('R008', 'TFZE_IDENT', 'REMOVED',
                 'Entfällt: TfzE, tEns und LocomotiveNo gelten im MVP als dieselbe Identifikation.',
                 false),
                ('R009', 'ASSIGNMENT', 'MANUAL_REVIEW',
                 'DE-relevanter Abschnitt ohne PerformingRU.',
                 true),
                ('R010', 'TIMELINE', 'ERROR',
                 'DE-relevante Ortskette endet oder ist unterbrochen. Unterbrechung über 8 Stunden.',
                 true),
                ('R010.5', 'TIMELINE', 'INFO',
                 'DE-relevante Ortskette endet oder ist unterbrochen. Unterbrechung bis einschließlich 8 Stunden.',
                 true),
                ('R011', 'TIMELINE', 'ERROR',
                 'Zeitliche Überschneidung zur vorherigen Bewegung gleicher Lok.',
                 true),
                ('R012', 'NO_LOCO_RAW', 'ERROR',
                 'Fehlende Loknummer, technische Dummy-Loknummer oder LocomotiveType enthält Dummy.',
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


    # Exportfähigkeit nach der zentralen Finding-Berechnung neu ableiten.
    # Dadurch blockieren offene ERROR- und MANUAL_REVIEW-Findings auch Exporte.
    con.execute("""
        update core_loco_timeline
        set export_ready = case
            when row_type = 'MOVEMENT'
             and report_scope = 'IN_REPORT'
             and coalesce(needs_manual_review, false) = false
             and sequence_ts is not null
             and period_start_utc is not null
             and period_end_utc is not null
             and period_start_utc <= period_end_utc
             and loco_no is not null
             and loco_no <> ''
             and user_vens is not null
             and user_vens <> ''
             and performing_ru_marktpartner_id is not null
             and performing_ru_marktpartner_id <> ''
                then true
            else false
        end
    """)


def build_findings(
    con,
    run_id: str,
    home_country_iso: str = "DE",
    loco_filter: "frozenset[str] | None" = None,
) -> None:
    """
    Erzeugt dq_findings und synchronisiert danach die Timeline-Flags.

    Die Tabelle enthält atomare Regelverletzungen. Deshalb kann dieselbe
    TransportNumber mehrfach vorkommen, wenn mehrere Regeln greifen.

    loco_filter: None → Vollneubau (bisheriges Verhalten).
                 frozenset → DELETE+INSERT nur für diese Loknummern.
                 frozenset() (leer) → keine Änderung.
    """
    if loco_filter is not None and len(loco_filter) == 0:
        return

    run = sql_lit(run_id)
    source_snapshot_at_utc, error_cutoff_utc = _get_error_cutoff_utc(
        con,
        run_id,
    )
    error_cutoff = sql_lit(error_cutoff_utc)

    print(f"DQ Snapshot UTC: {source_snapshot_at_utc}")
    print(f"DQ 24h-Cutoff UTC: {error_cutoff_utc}")

    con.execute("""
        create or replace table dq_run_metadata as
        select
            ?::varchar as run_id,
            try_cast(? as timestamp) as source_snapshot_at_utc,
            try_cast(? as timestamp) as error_cutoff_utc,
            current_timestamp as calculated_at_utc
    """, [
        run_id,
        source_snapshot_at_utc,
        error_cutoff_utc,
    ])
    build_rule_catalog(con)

    _is_partial = loco_filter is not None
    _loco_list = list(loco_filter) if _is_partial else None
    _lf = "and loco_no = ANY(?)" if _is_partial else ""
    _lf_params = [_loco_list] if _is_partial else []

    _FINDINGS_BASE_COLS = (
        "run_id, severity, rule_id, rule_group, loco_no, transport_number,"
        " performing_ru, row_type, movement_sequence_no, period_start_utc,"
        " period_end_utc, message, suggested_action, status, source_table, source_row_id"
    )

    if _is_partial:
        con.execute("delete from dq_findings where loco_no = ANY(?)", [_loco_list])
        _findings_preamble = f"insert into dq_findings ({_FINDINGS_BASE_COLS})"
    else:
        _findings_preamble = "create or replace table dq_findings as"

    con.execute(f"""
        {_findings_preamble}
        with movement_base as (
            select *
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              {_lf}
        ),
        movement_error_base as (
            select *
            from movement_base
            where coalesce(period_start_utc, period_end_utc) is not null
              and coalesce(period_start_utc, period_end_utc) <= try_cast({error_cutoff} as timestamp)
        ),
        gap_error_base as (
            select *
            from core_loco_timeline
            where row_type = 'GAP'
              and coalesce(gap_relevant_de, false) = true
              and coalesce(period_end_utc, period_start_utc) is not null
              and coalesce(period_end_utc, period_start_utc) <= try_cast({error_cutoff} as timestamp)
              {_lf}
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
            from movement_error_base b
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
        from movement_error_base
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
        from movement_error_base
        where report_scope = 'IN_REPORT'
          and period_start_utc is not null
          and period_end_utc is not null
          and period_start_utc > period_end_utc

        -- R005 entfällt hier bewusst:
        -- Die Keine-Loks-Prüfung greift direkt auf die Rohdaten zu.


        -- R006 und R007 entfallen im MVP vollständig:
        -- Fehlende vEns-/tEns-Zuordnungen werden nicht als Findings bewertet.

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
        from movement_error_base
        where report_scope = 'IN_REPORT'
          and (performing_ru is null or performing_ru = '')

        union all

        -- R010: DE-relevante Unterbrechung über 8 Stunden = ERROR.
        select
            {run},
            'ERROR',
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
            'Ortskette mit Unterbrechung über 8 Stunden fachlich prüfen.',
            'open',
            source_table,
            source_row_id
        from gap_error_base
        where coalesce(gap_duration_minutes, 0) > 480

        union all

        -- R010.5: DE-relevante Unterbrechung bis einschließlich 8 Stunden = INFO.
        select
            {run},
            'INFO',
            'R010.5',
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
          and coalesce(gap_relevant_de, false) = true
          and coalesce(gap_duration_minutes, 0) <= 480
          {_lf}

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
    """, _lf_params * 3)

    # R012 wird direkt aus den Rohdaten ergänzt, weil fehlende Loknummern
    # keiner Lok-Zeitachse zugeordnet werden können.
    build_r012_raw_findings(
        con=con,
        run_id=run_id,
        error_cutoff_utc=error_cutoff_utc,
    )
    if _is_partial:
        con.execute(
            f"insert into dq_findings ({_FINDINGS_BASE_COLS})"
            " select * from tmp_r012_findings where loco_no = ANY(?)",
            [_loco_list],
        )
    else:
        con.execute("insert into dq_findings select * from tmp_r012_findings")

    # Defensive Nachbereinigung für GAP-Findings:
    # Nur explizit als DE-relevant klassifizierte Lücken dürfen in der
    # Fehlerqueue und in den KPI-Zählern verbleiben. Dadurch bleiben auch
    # ältere oder zukünftig ergänzte GAP-Regeln sicher auf die fachlich
    # freigegebenen Kombinationen begrenzt.
    _gap_loco_clause = "and f.loco_no = ANY(?)" if _is_partial else ""
    con.execute(f"""
        delete from dq_findings as f
        where f.row_type = 'GAP'
          {_gap_loco_clause}
          and not exists (
                select 1
                from core_loco_timeline as c
                where c.row_type = 'GAP'
                  and coalesce(c.gap_relevant_de, false) = true
                  and c.loco_no is not distinct from f.loco_no
                  and c.transport_number is not distinct from f.transport_number
                  and c.movement_sequence_no is not distinct from f.movement_sequence_no
                  and c.period_start_utc is not distinct from f.period_start_utc
                  and c.period_end_utc is not distinct from f.period_end_utc
                  and c.source_table is not distinct from f.source_table
                  and c.source_row_id is not distinct from f.source_row_id
          )
    """, _lf_params)

    # R011: Referenztransport ergänzen.
    # Bei partial rebuild existiert die Spalte bereits — nur hinzufügen wenn nötig.
    _existing_cols = {r[0].lower() for r in con.execute("describe dq_findings").fetchall()}
    if "overlap_with_transport_number" not in _existing_cols:
        con.execute("alter table dq_findings add column overlap_with_transport_number varchar")

    _r011_loco_clause = "and f.loco_no = ANY(?)" if _is_partial else ""
    con.execute(f"""
        update dq_findings as f
        set overlap_with_transport_number = o.prev_transport_number
        from (
            select
                source_table,
                source_row_id,
                lag(period_end_utc) over (
                    partition by loco_no
                    order by
                        coalesce(
                            sequence_ts,
                            period_start_utc,
                            period_end_utc
                        ) asc nulls last,
                        source_row_id asc
                ) as prev_end,
                lag(transport_number) over (
                    partition by loco_no
                    order by
                        coalesce(
                            sequence_ts,
                            period_start_utc,
                            period_end_utc
                        ) asc nulls last,
                        source_row_id asc
                ) as prev_transport_number
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
        ) as o
        where f.rule_id = 'R011'
          {_r011_loco_clause}
          and f.source_table is not distinct from o.source_table
          and f.source_row_id is not distinct from o.source_row_id
          and o.prev_end is not null
    """, _lf_params)

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
