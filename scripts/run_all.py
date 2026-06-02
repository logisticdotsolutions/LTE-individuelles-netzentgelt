r"""
Netzentgelt MVP - täglicher Neuaufbau der DuckDB-Datenbasis
===========================================================

Zweck
-----
Dieses Skript importiert die CSV-Dateien aus data/00_raw, berechnet alle
Staging-, Core-, Finding- und Exporttabellen vollständig neu und ersetzt erst
nach einem erfolgreichen Gesamtlauf die produktive DuckDB-Datei.

Wichtige Ordner
---------------
data/00_raw      : Eingangsdaten als CSV
data/01_mapping  : fachliche Mapping-Dateien
data/02_duckdb   : produktive und temporäre DuckDB-Datei
data/03_exports  : neu erzeugte CSV-Ausgaben
data/04_logs     : Laufprotokolle

Sicherheitsprinzip
-----------------
netzentgelt.duckdb bleibt während der Berechnung unangetastet.
Der Neuaufbau erfolgt in netzentgelt_build.duckdb.
Nur ein vollständig erfolgreicher Lauf ersetzt den produktiven Tagesstand.

Normaler Start
--------------
Im Projektstamm ausführen:
    .venv\Scripts\python.exe scripts\run_all.py
"""

from pathlib import Path
import os
import duckdb
import hashlib
import re
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "00_raw"
MAP_DIR = ROOT / "data" / "01_mapping"
DB_DIR = ROOT / "data" / "02_duckdb"
EXP_DIR = ROOT / "data" / "03_exports"
LOG_DIR = ROOT / "data" / "04_logs"
# Produktive DuckDB-Datei:
# Diese Datei enthält immer den letzten erfolgreich berechneten Tagesstand.
DB_PATH = DB_DIR / "netzentgelt.duckdb"

# Temporäre DuckDB-Datei:
# Jeder neue Lauf wird zuerst vollständig in dieser Datei aufgebaut.
# Erst wenn der gesamte Lauf erfolgreich war, ersetzt sie DB_PATH.
# Dadurch bleibt bei einem Fehler die letzte funktionierende Datenbank erhalten.
DB_BUILD_PATH = DB_DIR / "netzentgelt_build.duckdb"

# Fachliche Konfiguration:
# - Es werden nur Loks berücksichtigt, die innerhalb des Lookback-Zeitraums
#   mindestens einmal einen DE-Bezug haben.
# - GAP-Zeilen werden erst bei einer Lücke von mehr als 15 Minuten erzeugt.
LOOKBACK_MONTHS = 6
HOME_COUNTRY_ISO = "DE"
GAP_THRESHOLD_MINUTES = 15

for d in [RAW_DIR, MAP_DIR, DB_DIR, EXP_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def ts():
    """Aktuellen UTC-Zeitstempel für Logs und Importprotokolle erzeugen."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def remove_if_exists(path: Path):
    """
    Datei nur dann löschen, wenn sie tatsächlich existiert.

    Diese Hilfsfunktion wird ausschließlich für temporäre Build-Dateien verwendet.
    Die produktive DB_PATH wird niemals vor Beginn des Neuaufbaus gelöscht.
    """
    if path.exists():
        path.unlink()


def sha256(path):
    """SHA-256-Prüfsumme einer Quelldatei für das Import-Audit berechnen."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_name(name):
    """Aus einem CSV-Dateinamen einen sicheren DuckDB-Tabellennamen bilden."""
    n = Path(name).stem.lower()
    n = re.sub(r"[^a-z0-9_]+", "_", n)
    return "raw_" + n.strip("_")

def qident(name):
    """SQL-Identifier sicher quoten, z. B. Tabellen- oder Spaltennamen."""
    return '"' + name.replace('"', '""') + '"'

def table_exists(con, table):
    """Prüfen, ob eine DuckDB-Tabelle bereits existiert."""
    return con.execute(
        "select count(*) from information_schema.tables where table_name = ?",
        [table.lower()]
    ).fetchone()[0] > 0

def columns(con, table):
    """Alle Spaltennamen einer DuckDB-Tabelle auslesen."""
    rows = con.execute(f"describe {qident(table)}").fetchall()
    return [r[0] for r in rows]

def pick(cols, candidates, fallback="NULL"):
    """
    Erste vorhandene Spalte aus einer Kandidatenliste auswählen.
    Der Vergleich erfolgt unabhängig von Groß-/Kleinschreibung.
    """
    by_lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in by_lower:
            return qident(by_lower[cand.lower()])
    return fallback

def pick_text(cols, candidates, fallback="NULL"):
    """Wie pick(), aber zusätzlich als bereinigten Textwert zurückgeben."""
    expr = pick(cols, candidates, fallback)
    return expr if expr == "NULL" else f"NULLIF(TRIM(CAST({expr} AS VARCHAR)), '')"

def coalesce(cols, candidates):
    """
    Mehrere mögliche Quellspalten priorisiert zusammenführen.
    Der erste nicht-leere Wert wird verwendet.
    """
    exprs = [pick_text(cols, [c]) for c in candidates]
    exprs = [e for e in exprs if e != "NULL"]
    return "COALESCE(" + ", ".join(exprs) + ")" if exprs else "NULL"

def import_csvs(con):
    """
    Alle CSV-Dateien aus data/00_raw frisch nach DuckDB importieren.

    Da der gesamte Tageslauf in DB_BUILD_PATH neu aufgebaut wird,
    enthält die temporäre Datenbank ausschließlich den aktuellen Importstand.
    """
    con.execute("""
        create table if not exists raw_import_run (
            run_id varchar,
            imported_at_utc varchar,
            source_file varchar,
            target_table varchar,
            source_hash varchar,
            row_count bigint,
            status varchar,
            error_message varchar
        )
    """)
    run_id = datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S")
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        print("Keine CSVs in data/00_raw gefunden. Lege dort die DataLake-CSV-Dateien ab und starte erneut.")
        return run_id, []
    imported = []
    for file in files:
        target = safe_name(file.name)
        try:
            con.execute(f"""
                create or replace table {qident(target)} as
                select * from read_csv_auto(?, union_by_name=true, all_varchar=true, filename=true, ignore_errors=true)
            """, [str(file)])
            rc = con.execute(f"select count(*) from {qident(target)}").fetchone()[0]
            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?)",
                        [run_id, ts(), file.name, target, sha256(file), rc, "imported", None])
            imported.append(target)
            print(f"Importiert: {file.name} -> {target} ({rc} Zeilen)")
        except Exception as e:
            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?)",
                        [run_id, ts(), file.name, target, sha256(file), 0, "failed", str(e)])
            print(f"FEHLER Import {file.name}: {e}")
    return run_id, imported

def import_mapping(con):
    """
    Lok-Mapping laden.

    Existiert keine Mapping-Datei, wird eine leere Tabelle mit dem erwarteten
    Schema angelegt. Dadurch kann die Pipeline weiterlaufen und Findings erzeugen.
    """
    mapping = MAP_DIR / "loco_mapping.csv"
    if mapping.exists():
        con.execute("""
            create or replace table cfg_loco_mapping as
            select * from read_csv_auto(?, delim=';', header=true, all_varchar=true, ignore_errors=true)
        """, [str(mapping)])
    else:
        con.execute("""
            create or replace table cfg_loco_mapping (
                loco_no varchar, tfze_or_tens varchar, halter_name varchar, halter_marktpartner_id varchar,
                default_vens varchar, valid_from_utc varchar, valid_to_utc varchar, priority varchar,
                source varchar, comment varchar, active_flag varchar
            )
        """)

def build_loco_events(con):
    """
    Bewegungsdaten der Loks aufbereiten.

    Diese Funktion:
    - identifiziert die Bewegungsquelle,
    - bildet die vollständige Lok-Zeitachse,
    - leitet Clean-/Faulty-Richtung und Sequence-Zeitanker ab,
    - kennzeichnet IN_REPORT und NOT_IN_REPORT,
    - protokolliert nicht aufgenommene Zeilen.
    """
    candidates = [t[0] for t in con.execute(
        "select table_name from information_schema.tables where table_name like 'raw_%'"
    ).fetchall()]

    source = None
    for c in candidates:
        if "locomotivemovement" in c:
            source = c
            break

    if source is None:
        for c in candidates:
            if "locomotiveusage" in c:
                source = c
                break

    if source is None:
        print("Keine LocomotiveMovement.csv oder LocomotiveUsage.csv gefunden. Staging wird leer angelegt.")
        con.execute("""
            create or replace table stg_loco_events (
                loco_no varchar,
                holder_raw varchar,
                performing_ru varchar,
                traction_type varchar,
                country varchar,
                origin_country_iso varchar,
                destination_country_iso varchar,
                actual_departure_ts timestamp,
                actual_arrival_ts timestamp,
                period_start_utc timestamp,
                period_end_utc timestamp,
                sequence_ts timestamp,
                sequence_ts_source varchar,
                sequence_ts_reason varchar,
                clean_dir varchar,
                faulty_dir varchar,
                report_scope varchar,
                de_event_label varchar,
                transport_number varchar,
                train_no varchar,
                distance varchar,
                origin_name varchar,
                destination_name varchar,
                source_table varchar,
                source_row_id bigint
            )
        """)
        con.execute("""
            create or replace table stg_loco_events_skipped (
                source_table varchar,
                source_row_id bigint,
                skip_reason varchar
            )
        """)
        return

    cols = columns(con, source)

    loco_no = pick_text(cols, ["LocomotiveNo", "FirstLocomotiveNo", "Alias"])

    actual_departure = coalesce(cols, [
        "ActualDeparture",
        "LocomotiveActualDeparture"
    ])

    actual_arrival = coalesce(cols, [
        "ActualArrival",
        "LocomotiveActualArrival"
    ])

    origin_country = pick_text(cols, [
        "OriginCountryISO",
        "OriginCountryIso",
        "OriginCountry",
        "FromCountryISO",
        "FromCountry",
        "DepartureCountryISO",
        "DepartureCountry",
        "Country"
    ])

    destination_country = pick_text(cols, [
        "DestinationCountryISO",
        "DestinationCountryIso",
        "DestinationCountry",
        "ToCountryISO",
        "ToCountry",
        "ArrivalCountryISO",
        "ArrivalCountry",
        "Country"
    ])

    origin_name = pick_text(cols, [
        "LocomotiveOriginLocationName",
        "OriginLocationName",
        "OriginName",
        "FromLocationName",
        "DepartureLocationName"
    ])

    destination_name = pick_text(cols, [
        "LocomotiveDestinationLocationName",
        "DestinationLocationName",
        "DestinationName",
        "ToLocationName",
        "ArrivalLocationName"
    ])

    clean_dir_raw = pick_text(cols, [
        "CleanDir",
        "CALCleanDir",
        "CleanDirection"
    ])

    faulty_dir_raw = pick_text(cols, [
        "FaultyDir",
        "CALFaultyDir",
        "FaultyDirection"
    ])

    holder_raw = pick_text(cols, [
        "LocomotiveHolder",
        "LocomotiveOwner",
        "Holder"
    ])

    performing_ru = pick_text(cols, [
        "CurrentContractant",
        "CALPerformingRU",
        "PerformingRU",
        "PerformingRailwayUndertaking",
        "RailwayUndertaking",
        "Carrier",
        "ProductionCompany"
    ])

    traction_type = pick_text(cols, [
        "TractionType",
        "Traction"
    ])

    transport_number = pick_text(cols, [
        "TransportNumber",
        "TransportNo",
        "TransportId",
        "TransportID"
    ])

    train_no = pick_text(cols, [
        "TrainNo",
        "OriginTrainNo",
        "DestinationTrainNo"
    ])

    distance = pick_text(cols, [
        "Distance",
        "Km",
        "RealKm"
    ])

    home = sql_lit(HOME_COUNTRY_ISO.upper())

    con.execute(f"""
        create or replace table stg_loco_events as
        with base as (
            select
                row_number() over () as source_row_id,
                {loco_no} as loco_no,
                {holder_raw} as holder_raw,
                {performing_ru} as performing_ru,
                {traction_type} as traction_type,
                upper({origin_country}) as origin_country_iso,
                upper({destination_country}) as destination_country_iso,
                try_cast({actual_departure} as timestamp) as actual_departure_ts,
                try_cast({actual_arrival} as timestamp) as actual_arrival_ts,
                {origin_name} as origin_name,
                {destination_name} as destination_name,
                upper({clean_dir_raw}) as clean_dir_raw,
                upper({faulty_dir_raw}) as faulty_dir_raw,
                {transport_number} as transport_number,
                {train_no} as train_no,
                {distance} as distance
            from {qident(source)}
        ),
        prepared as (
            select
                *,
                case
                    when origin_country_iso = {home}
                      or destination_country_iso = {home}
                    then true else false
                end as row_has_home
            from base
        ),
        anchor as (
            select max(coalesce(actual_departure_ts, actual_arrival_ts)) as anchor_ts
            from prepared
        ),
        relevant_loco as (
            select distinct p.loco_no
            from prepared p
            cross join anchor a
            where p.loco_no is not null
              and p.loco_no <> ''
              and p.row_has_home = true
              and a.anchor_ts is not null
              and coalesce(p.actual_departure_ts, p.actual_arrival_ts) >= a.anchor_ts - interval '{LOOKBACK_MONTHS} months'
        ),
        flags as (
            select
                p.*,

                lag(row_has_home) over (
                    partition by loco_no
                    order by coalesce(actual_departure_ts, actual_arrival_ts) asc nulls last, source_row_id
                ) as previous_has_home,

                lead(row_has_home) over (
                    partition by loco_no
                    order by coalesce(actual_departure_ts, actual_arrival_ts) asc nulls last, source_row_id
                ) as next_has_home,

                lag(loco_no) over (
                    partition by loco_no
                    order by coalesce(actual_departure_ts, actual_arrival_ts) asc nulls last, source_row_id
                ) as previous_loco_no,

                lead(loco_no) over (
                    partition by loco_no
                    order by coalesce(actual_departure_ts, actual_arrival_ts) asc nulls last, source_row_id
                ) as next_loco_no
            from prepared p
            where exists (
                select 1
                from relevant_loco rl
                where rl.loco_no = p.loco_no
            )
        ),
        directions as (
            select
                *,

                case
                    when origin_country_iso <> {home}
                     and destination_country_iso = {home}
                        then 'E'

                    when origin_country_iso = {home}
                     and destination_country_iso <> {home}
                        then 'A'

                    else null
                end as derived_faulty_dir,

                case
                    when origin_country_iso = {home}
                     and destination_country_iso = {home}
                     and previous_loco_no is not null
                     and next_loco_no is not null
                     and coalesce(previous_has_home, false) = false
                     and coalesce(next_has_home, false) = false
                        then 'E/A'

                    when origin_country_iso = {home}
                     and destination_country_iso = {home}
                     and previous_loco_no is not null
                     and coalesce(previous_has_home, false) = false
                        then 'E'

                    when origin_country_iso = {home}
                     and destination_country_iso = {home}
                     and next_loco_no is not null
                     and coalesce(next_has_home, false) = false
                        then 'A'

                    when origin_country_iso = {home}
                     and destination_country_iso = {home}
                        then 'IN'

                    else null
                end as derived_clean_dir
            from flags
        ),
        normalized as (
            select
                *,
                coalesce(faulty_dir_raw, derived_faulty_dir) as faulty_dir,
                coalesce(clean_dir_raw, derived_clean_dir) as clean_dir
            from directions
        ),
        sequenced as (
            select
                *,
                case
                    -- FAULTY-LOGIK: Ländersprung in derselben Zeile
                    when faulty_dir = 'E'
                        then actual_arrival_ts

                    when faulty_dir = 'A'
                        then actual_departure_ts

                    -- CLEAN-LOGIK: Länder sauber je Zeile
                    when clean_dir = 'E'
                        then actual_departure_ts

                    when clean_dir = 'A'
                        then actual_arrival_ts

                    when clean_dir = 'E/A'
                        then actual_departure_ts

                    -- normale Nicht-DE- oder In-DE-Bewegung
                    else actual_departure_ts
                end as sequence_ts,

                case
                    when faulty_dir = 'E'
                        then 'ActualArrival'

                    when faulty_dir = 'A'
                        then 'ActualDeparture'

                    when clean_dir = 'E'
                        then 'ActualDeparture'

                    when clean_dir = 'A'
                        then 'ActualArrival'

                    when clean_dir = 'E/A'
                        then 'ActualDeparture'

                    else 'ActualDeparture'
                end as sequence_ts_source,

                case
                    when faulty_dir = 'E'
                        then 'FaultyDir=E -> Ländersprung in einer Zeile, Einfahrt bei ActualArrival.'

                    when faulty_dir = 'A'
                        then 'FaultyDir=A -> Ländersprung in einer Zeile, Ausfahrt bei ActualDeparture.'

                    when clean_dir = 'E'
                        then 'CleanDir=E -> Einfahrt in sauberer Länderlogik, Zeitanker ActualDeparture.'

                    when clean_dir = 'A'
                        then 'CleanDir=A -> Ausfahrt in sauberer Länderlogik, Zeitanker ActualArrival.'

                    when clean_dir = 'E/A'
                        then 'CleanDir=E/A -> Einfahrt und Ausfahrt in sauberer Länderlogik, Zeitanker ActualDeparture.'

                    else 'Keine Clean-/Faulty-Grenzlogik; Zeitanker ActualDeparture.'
                end as sequence_ts_reason,

                case
                    when row_has_home = true then 'IN_REPORT'
                    else 'NOT_IN_REPORT'
                end as report_scope,

                case
                    when faulty_dir = 'E' then 'Einfahrt'
                    when faulty_dir = 'A' then 'Ausfahrt'
                    when clean_dir = 'E/A' then 'Einfahrt + Ausfahrt'
                    when clean_dir = 'E' then 'Einfahrt'
                    when clean_dir = 'A' then 'Ausfahrt'
                    when row_has_home = true then 'In DE'
                    else 'Not in the Report'
                end as de_event_label
            from normalized
        )
        select
            loco_no,
            holder_raw,
            performing_ru,
            traction_type,

            case
                when origin_country_iso is null and destination_country_iso is null then null
                when origin_country_iso = destination_country_iso then origin_country_iso
                else coalesce(origin_country_iso, '?') || '>' || coalesce(destination_country_iso, '?')
            end as country,

            origin_country_iso,
            destination_country_iso,

            actual_departure_ts,
            actual_arrival_ts,

            actual_departure_ts as period_start_utc,
            actual_arrival_ts as period_end_utc,

            sequence_ts,
            sequence_ts_source,
            sequence_ts_reason,

            clean_dir,
            faulty_dir,
            report_scope,
            de_event_label,

            transport_number,
            train_no,
            distance,
            origin_name,
            destination_name,

            '{source}' as source_table,
            source_row_id
        from sequenced
    """)

    con.execute(f"""
        create or replace table stg_loco_events_skipped as
        with base as (
            select
                row_number() over () as source_row_id,
                {loco_no} as loco_no,
                upper({origin_country}) as origin_country_iso,
                upper({destination_country}) as destination_country_iso,
                try_cast({actual_departure} as timestamp) as actual_departure_ts,
                try_cast({actual_arrival} as timestamp) as actual_arrival_ts
            from {qident(source)}
        ),
        prepared as (
            select
                *,
                case
                    when origin_country_iso = {home}
                      or destination_country_iso = {home}
                    then true else false
                end as row_has_home
            from base
        ),
        anchor as (
            select max(coalesce(actual_departure_ts, actual_arrival_ts)) as anchor_ts
            from prepared
        ),
        relevant_loco as (
            select distinct p.loco_no
            from prepared p
            cross join anchor a
            where p.loco_no is not null
              and p.loco_no <> ''
              and p.row_has_home = true
              and a.anchor_ts is not null
              and coalesce(p.actual_departure_ts, p.actual_arrival_ts) >= a.anchor_ts - interval '{LOOKBACK_MONTHS} months'
        )
        select
            '{source}' as source_table,
            p.source_row_id,
            case
                when p.loco_no is null or p.loco_no = ''
                    then 'Loknummer fehlt; Datensatz kann keiner Lok-Zeitachse zugeordnet werden.'

                when not exists (
                    select 1 from relevant_loco rl where rl.loco_no = p.loco_no
                )
                    then 'Lok im Lookback-Zeitraum ohne DE-Bezug in OriginCountry/DestinationCountry; nicht in diese Auswertung aufgenommen.'

                else 'Nicht verarbeitet.'
            end as skip_reason
        from prepared p
        where p.loco_no is null
           or p.loco_no = ''
           or not exists (
                select 1 from relevant_loco rl where rl.loco_no = p.loco_no
           )
    """)

    skipped = con.execute("select count(*) from stg_loco_events_skipped").fetchone()[0]
    loaded = con.execute("select count(*) from stg_loco_events").fetchone()[0]

    print(
        f"Staging erstellt: {loaded} Zeilen verarbeitet, {skipped} Zeilen nicht aufgenommen. "
        f"Logik: relevante Loks mit DE-Bezug im letzten {LOOKBACK_MONTHS}-Monatsfenster, danach komplette Lok-Historie."
    )

def sql_lit(value):
    """SQL-Textliteral sicher quoten."""
    return "'" + str(value).replace("'", "''") + "'"

def build_transport_routes(con, home_country=HOME_COUNTRY_ISO):
    """
    TransportDetail-Segmente auswerten und die DE-Routenklassifikation bilden.
    """
    candidates = [
        t[0]
        for t in con.execute(
            "select table_name from information_schema.tables where table_name like 'raw_%'"
        ).fetchall()
    ]

    source = None
    for c in candidates:
        if "transportdetail" in c:
            source = c
            break

    if source is None:
        print("Keine TransportDetail.csv gefunden. Transport-Routenklassifikation wird leer angelegt.")
        con.execute("""
            create or replace table stg_transport_details_enriched (
                transport_number varchar,
                cal_seqnum bigint,
                origin_country_iso varchar,
                destination_country_iso varchar,
                cal_border_event_home varchar,
                source_table varchar,
                source_row_id bigint
            )
        """)
        con.execute("""
            create or replace table core_transport_route (
                transport_number varchar,
                cal_start_country varchar,
                cal_end_country varchar,
                cal_entry_count_home bigint,
                cal_exit_count_home bigint,
                cal_route_type_home varchar
            )
        """)
        return

    cols = columns(con, source)

    transport_number = pick_text(cols, [
        "TransportNumber",
        "TransportNo",
        "TransportId",
        "TransportID"
    ])

    sequence = pick(cols, [
        "SequenceID",
        "SequenceId",
        "Sequence",
        "Seq",
        "SeqNo"
    ])

    origin_country = pick_text(cols, [
        "OriginCountryISO",
        "OriginCountryIso",
        "OriginCountry",
        "FromCountryISO",
        "FromCountry",
        "DepartureCountryISO",
        "DepartureCountry"
    ])

    destination_country = pick_text(cols, [
        "DestinationCountryISO",
        "DestinationCountryIso",
        "DestinationCountry",
        "ToCountryISO",
        "ToCountry",
        "ArrivalCountryISO",
        "ArrivalCountry"
    ])

    origin_name = pick_text(cols, [
        "OriginLocationName",
        "OriginName",
        "FromLocationName",
        "DepartureLocationName"
])

    destination_name = pick_text(cols, [
        "DestinationLocationName",
        "DestinationName",
        "ToLocationName",
        "ArrivalLocationName"
])

    departure_time = coalesce(cols, [
        "ActualDeparture",
        "RevisedDeparture",
        "PlannedDeparture"
])

    arrival_time = coalesce(cols, [
        "ActualArrival",
        "RevisedArrival",
        "PlannedArrival"
])

    missing = []
    if transport_number == "NULL":
        missing.append("TransportNumber")
    if origin_country == "NULL":
        missing.append("OriginCountryISO")
    if destination_country == "NULL":
        missing.append("DestinationCountryISO")

    if missing:
        print(
            "WARNUNG: Transport-Routenklassifikation nicht möglich. "
            f"Fehlende Spalten/Mapping: {', '.join(missing)}"
        )
        con.execute("""
            create or replace table stg_transport_details_enriched (
                transport_number varchar,
                cal_seqnum bigint,
                origin_country_iso varchar,
                destination_country_iso varchar,
                cal_border_event_home varchar,
                source_table varchar,
                source_row_id bigint
            )
        """)
        con.execute("""
            create or replace table core_transport_route (
                transport_number varchar,
                cal_start_country varchar,
                cal_end_country varchar,
                cal_entry_count_home bigint,
                cal_exit_count_home bigint,
                cal_route_type_home varchar
            )
        """)
        return

    home = sql_lit(home_country.upper())

    if sequence == "NULL":
        seq_expr = "row_number() over (partition by " + transport_number + " order by filename)"
        print("WARNUNG: Keine SequenceID gefunden. Reihenfolge wird ersatzweise technisch gebildet.")
    else:
        seq_expr = f"try_cast({sequence} as bigint)"

    con.execute(f"""
        create or replace table stg_transport_details_enriched as
        select
            {transport_number} as transport_number,
            {seq_expr} as cal_seqnum,
            upper({origin_country}) as origin_country_iso,
            upper({destination_country}) as destination_country_iso,

            case
                when upper({origin_country}) <> {home}
                 and upper({destination_country}) = {home}
                    then 'Einfahrt'

                when upper({origin_country}) = {home}
                 and upper({destination_country}) <> {home}
                    then 'Ausfahrt'

                when upper({origin_country}) = {home}
                 and upper({destination_country}) = {home}
                    then 'Inland'

                when {origin_country} is null
                  or {destination_country} is null
                    then 'Unklar'

                else 'Ausland'
            end as cal_border_event_home,

            '{source}' as source_table,
            row_number() over () as source_row_id
        from {qident(source)}
        where {transport_number} is not null
          and {transport_number} <> ''
    """)

    con.execute(f"""
        create or replace table core_transport_route as
        with ordered as (
            select
                transport_number,
                cal_seqnum,
                origin_country_iso,
                destination_country_iso,
                cal_border_event_home,

                row_number() over (
                    partition by transport_number
                    order by cal_seqnum asc nulls last
                ) as rn_start,

                row_number() over (
                    partition by transport_number
                    order by cal_seqnum desc nulls last
                ) as rn_end
            from stg_transport_details_enriched
        ),
        agg as (
            select
                transport_number,

                max(case when rn_start = 1 then origin_country_iso end) as cal_start_country,
                max(case when rn_end = 1 then destination_country_iso end) as cal_end_country,

                sum(case when cal_border_event_home = 'Einfahrt' then 1 else 0 end) as cal_entry_count_home,
                sum(case when cal_border_event_home = 'Ausfahrt' then 1 else 0 end) as cal_exit_count_home,

                count(*) as segment_count
            from ordered
            group by transport_number
        )
        select
            transport_number,
            cal_start_country,
            cal_end_country,
            cal_entry_count_home,
            cal_exit_count_home,

            case
                when cal_start_country is null
                  or cal_end_country is null
                    then 'Unklar'

                when cal_start_country = {home}
                 and cal_end_country = {home}
                 and cal_entry_count_home = 0
                 and cal_exit_count_home = 0
                    then 'Inland'

                when cal_start_country <> {home}
                 and cal_end_country = {home}
                 and cal_entry_count_home > 0
                    then 'Einfahrt'

                when cal_start_country = {home}
                 and cal_end_country <> {home}
                 and cal_exit_count_home > 0
                    then 'Ausfahrt'

                when cal_start_country <> {home}
                 and cal_end_country <> {home}
                 and cal_entry_count_home > 0
                 and cal_exit_count_home > 0
                    then 'Passiert (Transit)'

                when cal_entry_count_home > 0
                  or cal_exit_count_home > 0
                    then 'Komplex (mehrfach/Schleife)'

                else 'Kein Bezug'
            end as cal_route_type_home

        from agg
    """)

    detail_rows = con.execute("select count(*) from stg_transport_details_enriched").fetchone()[0]
    route_rows = con.execute("select count(*) from core_transport_route").fetchone()[0]

    print(
        f"Transport-Routenklassifikation erstellt: "
        f"{detail_rows} Segmente, {route_rows} Transporte, Home={home_country.upper()}"
    )

def build_core(con, run_id):
    """
    Finale Lok-Zeitachse bilden.

    Zusätzlich zu den Bewegungszeilen werden künstliche GAP-Zeilen erzeugt,
    wenn die Ortskette unterbrochen ist und die Lücke größer als
    GAP_THRESHOLD_MINUTES ist.
    """
    con.execute(f"""
        create or replace table core_loco_timeline as
        with mapped as (
            select
                '{run_id}' as run_id,
                'MOVEMENT' as row_type,

                e.loco_no,
                coalesce(nullif(m.tfze_or_tens,''), e.loco_no) as tfze_or_tens,

                e.period_start_utc,
                e.period_end_utc,
                e.sequence_ts,
                e.sequence_ts_source,
                e.sequence_ts_reason,

                e.actual_departure_ts,
                e.actual_arrival_ts,

                coalesce(nullif(m.halter_name,''), e.holder_raw) as holder_name,
                e.performing_ru,

                r.cal_start_country,
                r.cal_end_country,
                r.cal_entry_count_home,
                r.cal_exit_count_home,
                r.cal_route_type_home,

                m.halter_marktpartner_id,
                m.default_vens as user_vens,

                e.country,
                e.origin_country_iso,
                e.destination_country_iso,

                e.clean_dir,
                e.faulty_dir,
                e.report_scope,
                e.de_event_label,

                e.traction_type,
                e.transport_number,
                e.train_no,
                e.distance,
                e.origin_name,
                e.destination_name,

                case
                    when m.default_vens is not null
                     and m.default_vens <> ''
                     and m.halter_marktpartner_id is not null
                     and m.halter_marktpartner_id <> ''
                     and m.tfze_or_tens is not null
                     and m.tfze_or_tens <> ''
                        then 'HIGH'

                    when m.default_vens is not null
                      or m.halter_marktpartner_id is not null
                      or m.tfze_or_tens is not null
                        then 'MEDIUM'

                    else 'LOW'
                end as confidence,

                case
                    when m.loco_no is null
                        then 'Keine passende Mapping-Zeile für Lok gefunden.'

                    when m.default_vens is null or m.default_vens = ''
                        then 'Mapping vorhanden, aber vEns fehlt. Wird als WARNING behandelt.'

                    when m.halter_marktpartner_id is null or m.halter_marktpartner_id = ''
                        then 'Mapping vorhanden, aber Marktpartner-ID fehlt.'

                    else 'Mapping über Loknummer und Gültigkeitszeitraum angewendet.'
                end as decision_reason,

                e.source_table,
                e.source_row_id
            from stg_loco_events e
            left join cfg_loco_mapping m
              on e.loco_no = m.loco_no
             and coalesce(upper(m.active_flag),'Y') <> 'N'
             and (
                    m.valid_from_utc is null
                 or m.valid_from_utc = ''
                 or e.period_start_utc >= try_cast(replace(m.valid_from_utc,'Z','') as timestamp)
             )
             and (
                    m.valid_to_utc is null
                 or m.valid_to_utc = ''
                 or e.period_start_utc < try_cast(replace(m.valid_to_utc,'Z','') as timestamp)
             )
            left join core_transport_route r
              on e.transport_number = r.transport_number
        ),
        ordered_movements as (
            select
                *,

                row_number() over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as movement_sequence_no,

                lead(sequence_ts) over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as next_sequence_ts,

                lead(period_start_utc) over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as next_period_start_utc,

                lead(origin_name) over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as next_origin_name,

                lead(origin_country_iso) over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as next_origin_country_iso
            from mapped
        ),
        movement_rows as (
            select
                run_id,
                row_type,
                loco_no,
                tfze_or_tens,

                cast(movement_sequence_no as double) as sort_sequence,
                movement_sequence_no,

                period_start_utc,
                period_end_utc,
                sequence_ts,
                sequence_ts_source,
                sequence_ts_reason,

                actual_departure_ts,
                actual_arrival_ts,

                holder_name,
                performing_ru,

                cal_start_country,
                cal_end_country,
                cal_entry_count_home,
                cal_exit_count_home,
                cal_route_type_home,

                halter_marktpartner_id,
                user_vens,

                country,
                origin_country_iso,
                destination_country_iso,

                clean_dir,
                faulty_dir,
                report_scope,
                de_event_label,

                traction_type,
                transport_number,
                train_no,
                distance,
                origin_name,
                destination_name,

                next_origin_name,
                next_origin_country_iso,

                null::timestamp as gap_from_utc,
                null::timestamp as gap_to_utc,
                null::bigint as gap_duration_minutes,
                null::varchar as gap_duration_text,
                null::varchar as gap_message,

                confidence,
                decision_reason,

                case
                    when sequence_ts is null
                      or period_start_utc is null
                      or period_end_utc is null
                      or period_start_utc > period_end_utc
                      or loco_no is null
                      or loco_no = ''
                        then true

                    when report_scope = 'IN_REPORT'
                     and (performing_ru is null or performing_ru = '')
                        then true

                    else false
                end as needs_manual_review,

                case
                    when row_type = 'MOVEMENT'
                     and report_scope = 'IN_REPORT'
                     and sequence_ts is not null
                     and period_start_utc is not null
                     and period_end_utc is not null
                     and period_start_utc <= period_end_utc
                     and loco_no is not null
                     and loco_no <> ''
                     and user_vens is not null
                     and user_vens <> ''
                     and halter_marktpartner_id is not null
                     and halter_marktpartner_id <> ''
                        then true
                    else false
                end as export_ready,

                case
                    when sequence_ts is null
                      or period_start_utc is null
                      or period_end_utc is null
                      or period_start_utc > period_end_utc
                      or loco_no is null
                      or loco_no = ''
                        then 'ERROR'

                    when report_scope = 'IN_REPORT'
                     and (performing_ru is null or performing_ru = '')
                        then 'MANUAL_REVIEW'

                    when report_scope = 'IN_REPORT'
                     and (user_vens is null or user_vens = '')
                        then 'WARNING'

                    when report_scope = 'NOT_IN_REPORT'
                        then 'INFO'

                    else ''
                end as dq_severity,

                case
                    when sequence_ts is null
                        then 'Kein gültiger Sequence-Zeitanker ableitbar. CleanDir/FaultyDir sowie ActualDeparture/ActualArrival prüfen.'

                    when period_start_utc is null
                        then 'ActualDeparture fehlt oder ist nicht als Timestamp interpretierbar.'

                    when period_end_utc is null
                        then 'ActualArrival fehlt oder ist nicht als Timestamp interpretierbar.'

                    when period_start_utc > period_end_utc
                        then 'ActualDeparture liegt nach ActualArrival.'

                    when loco_no is null or loco_no = ''
                        then 'Loknummer fehlt.'

                    when report_scope = 'IN_REPORT'
                     and (performing_ru is null or performing_ru = '')
                        then 'DE-relevanter Abschnitt ohne PerformingRU; manuelle Prüfung erforderlich.'

                    when report_scope = 'IN_REPORT'
                     and (user_vens is null or user_vens = '')
                        then 'vEns/VENS fehlt; wird als Warnung behandelt und blockiert die Zeitachsenlogik nicht.'

                    when report_scope = 'NOT_IN_REPORT'
                        then 'Außerhalb DE; Not in the Report.'

                    else ''
                end as dq_message,

                case
                    when report_scope = 'IN_REPORT'
                        then 'DE-Bezug über OriginCountry/DestinationCountry erkannt. Ereignis: ' || de_event_label || '. Zeitanker: ' || sequence_ts_reason

                    when report_scope = 'NOT_IN_REPORT'
                        then 'Kein DE-Bezug in OriginCountry/DestinationCountry. Zeile bleibt für die durchgehende Lok-Zeitachse sichtbar.'

                    else ''
                end as assignment_reason,

                source_table,
                source_row_id
            from ordered_movements
        ),
        gap_pre as (
            select
                *,
                coalesce(period_end_utc, sequence_ts) as gap_from,
                coalesce(next_period_start_utc, next_sequence_ts) as gap_to
            from ordered_movements
            where next_origin_name is not null
              and destination_name is not null
              and lower(trim(destination_name)) <> lower(trim(next_origin_name))
        ),
    gap_calc as (
    select
        *,
        case
            when gap_from is not null and gap_to is not null
                then date_diff('minute', gap_from, gap_to)
            else null
        end as gap_minutes,

        case
            when gap_from is not null and gap_to is not null
             and date_diff('minute', gap_from, gap_to) >= 0
            then
                trim(
                    concat(
                        case
                            when cast(floor(date_diff('minute', gap_from, gap_to) / 1440) as bigint) = 1
                                then '1 Tag '
                            when cast(floor(date_diff('minute', gap_from, gap_to) / 1440) as bigint) > 1
                                then cast(cast(floor(date_diff('minute', gap_from, gap_to) / 1440) as bigint) as varchar) || ' Tage '
                            else ''
                        end,
                        case
                            when cast(floor((date_diff('minute', gap_from, gap_to) % 1440) / 60) as bigint) = 1
                                then '1 Stunde '
                            when cast(floor((date_diff('minute', gap_from, gap_to) % 1440) / 60) as bigint) > 1
                                then cast(cast(floor((date_diff('minute', gap_from, gap_to) % 1440) / 60) as bigint) as varchar) || ' Stunden '
                            else ''
                        end,
                        case
                            when cast(date_diff('minute', gap_from, gap_to) % 60 as bigint) = 1
                                then '1 Minute'
                            else cast(cast(date_diff('minute', gap_from, gap_to) % 60 as bigint) as varchar) || ' Minuten'
                        end
                    )
                )
            else null
        end as gap_duration_text
    from gap_pre
),
        gap_rows as (
            select
                run_id,
                'GAP' as row_type,
                loco_no,
                tfze_or_tens,

                cast(movement_sequence_no as double) + 0.5 as sort_sequence,
                movement_sequence_no,

                gap_from as period_start_utc,
                gap_to as period_end_utc,
                null::timestamp as sequence_ts,
                'GAP' as sequence_ts_source,
                'Künstlich eingefügte Lückenzeile zwischen zwei Bewegungen.' as sequence_ts_reason,

                null::timestamp as actual_departure_ts,
                null::timestamp as actual_arrival_ts,

                holder_name,
                null as performing_ru,

                cal_start_country,
                cal_end_country,
                cal_entry_count_home,
                cal_exit_count_home,
                cal_route_type_home,

                halter_marktpartner_id,
                user_vens,

                null as country,
                destination_country_iso as origin_country_iso,
                next_origin_country_iso as destination_country_iso,

                null as clean_dir,
                null as faulty_dir,
                'GAP' as report_scope,
                'Lücke' as de_event_label,

                traction_type,
                transport_number,
                train_no,
                distance,
                destination_name as origin_name,
                next_origin_name as destination_name,

                next_origin_name,
                next_origin_country_iso,

                gap_from as gap_from_utc,
                gap_to as gap_to_utc,
                gap_minutes as gap_duration_minutes,
                gap_duration_text as gap_duration_text,

                case
                    when gap_from is not null
                    and gap_to is not null
                    and gap_minutes >= 0
                    then
                        'Keine Nutzung im Zeitraum von '
                        || strftime(gap_from, '%d.%m.%Y %H:%M:%S')
                        || ' bis '
                        || strftime(gap_to, '%d.%m.%Y %H:%M:%S')
                        || '. Das entspricht '
                        || coalesce(gap_duration_text, 'einer nicht berechenbaren Dauer')
                        || '.'

                    else
                        'Keine Nutzung im Zeitraum von unbekannt bis unbekannt. Dauer nicht berechenbar.'
                end as gap_message,

                null as confidence,
                'Künstliche GAP-Zeile wegen gebrochener Ortskette zwischen vorheriger Destination und nächstem Origin.' as decision_reason,

                true as needs_manual_review,
                false as export_ready,
                'WARNING' as dq_severity,

               case
                    when gap_from is not null
                    and gap_to is not null
                    and gap_minutes >= 0
                    then
                        'Keine Nutzung im Zeitraum von '
                        || strftime(gap_from, '%d.%m.%Y %H:%M:%S')
                        || ' bis '
                        || strftime(gap_to, '%d.%m.%Y %H:%M:%S')
                        || '. Das entspricht '
                        || coalesce(gap_duration_text, 'einer nicht berechenbaren Dauer')
                        || '. Vorherige Destination: '
                        || coalesce(destination_name, '?')
                        || '. Nächster Origin: '
                        || coalesce(next_origin_name, '?')
                        || '.'

                    else
                        'Keine Nutzung zwischen Bewegung davor und Bewegung danach. Zeitraum oder Dauer nicht berechenbar. Vorherige Destination: '
                        || coalesce(destination_name, '?')
                        || '. Nächster Origin: '
                        || coalesce(next_origin_name, '?')
                        || '.'
                end as dq_message,

                'Zwischen Movement-Sequence '
                || cast(movement_sequence_no as varchar)
                || ' und der nächsten Bewegung ist die Ortskette nicht geschlossen.'
                as assignment_reason,

                source_table,
                source_row_id
            from gap_calc
            where gap_minutes > {GAP_THRESHOLD_MINUTES}
        ),
        all_rows as (
            select * from movement_rows
            union all
            select * from gap_rows
        )
        select
            *,
            row_number() over (
                partition by loco_no
                order by sort_sequence asc, case when row_type = 'MOVEMENT' then 0 else 1 end
            ) as display_sequence_no
        from all_rows
    """)

def build_findings(con, run_id):
    """Fehler, Warnungen und manuelle Prüffälle regelbasiert erzeugen."""
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
                    order by period_start_utc, period_end_utc
                ) as prev_end
            from movement_base b
        )
        select '{run_id}' run_id, 'ERROR' severity, 'R001' rule_id, loco_no, period_start_utc, period_end_utc,
               'Sequence-Zeitanker fehlt.' message,
               'CleanDir/FaultyDir sowie ActualDeparture/ActualArrival prüfen.' suggested_action,
               'open' status
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and sequence_ts is null

        union all
        select '{run_id}', 'ERROR', 'R002', loco_no, period_start_utc, period_end_utc,
               'ActualDeparture fehlt oder ist ungültig.',
               'Quelle prüfen oder ActualDeparture manuell ergänzen.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and period_start_utc is null

        union all
        select '{run_id}', 'ERROR', 'R003', loco_no, period_start_utc, period_end_utc,
               'ActualArrival fehlt oder ist ungültig.',
               'Quelle prüfen oder ActualArrival manuell ergänzen.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and period_end_utc is null

        union all
        select '{run_id}', 'ERROR', 'R004', loco_no, period_start_utc, period_end_utc,
               'ActualDeparture liegt nach ActualArrival.',
               'Zeitintervall fachlich korrigieren.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and period_start_utc is not null
          and period_end_utc is not null
          and period_start_utc > period_end_utc

        union all
        select '{run_id}', 'ERROR', 'R005', loco_no, period_start_utc, period_end_utc,
               'Loknummer fehlt.',
               'Quelle prüfen; ohne Loknummer keine Zuordnung möglich.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and (loco_no is null or loco_no = '')

        union all
        select '{run_id}', 'WARNING', 'R006', loco_no, period_start_utc, period_end_utc,
               'vEns fehlt.',
               'vEns im Mapping ergänzen. Für die Zeitachsenlogik ist dies nur eine Warnung.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and (user_vens is null or user_vens = '')

        union all
        select '{run_id}', 'ERROR', 'R007', loco_no, period_start_utc, period_end_utc,
               'Marktpartner-ID fehlt.',
               'loco_mapping.csv ergänzen.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and (halter_marktpartner_id is null or halter_marktpartner_id = '')

        union all
        select '{run_id}', 'ERROR', 'R008', loco_no, period_start_utc, period_end_utc,
               'TfzE/tEns fehlt oder nur Loknummer als Fallback gesetzt.',
               'tEns/TfzE im Mapping ergänzen.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and (tfze_or_tens is null or tfze_or_tens = '' or tfze_or_tens = loco_no)

        union all
        select '{run_id}', 'MANUAL_REVIEW', 'R009', loco_no, period_start_utc, period_end_utc,
               'DE-relevanter Abschnitt ohne PerformingRU.',
               'PerformingRU fachlich prüfen und ergänzen.',
               'open'
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and (performing_ru is null or performing_ru = '')

        union all
        select '{run_id}', 'WARNING', 'R010', loco_no, period_start_utc, period_end_utc,
               dq_message,
               'Ortskette prüfen; fehlende Bewegung oder falsche Location-Zuordnung klären.',
               'open'
        from core_loco_timeline
        where row_type = 'GAP'

        union all
        select '{run_id}', 'ERROR', 'R011', loco_no, period_start_utc, period_end_utc,
               'Zeitliche Überschneidung zur vorherigen Bewegung gleicher Lok erkannt.',
               'Überlappung prüfen; Priorität oder manuelle Entscheidung setzen.',
               'open'
        from overlap
        where prev_end is not null
          and period_start_utc < prev_end
    """)

def build_exports(con):
    """Fachliche CSV-Exporttabellen für fehlerfreie IN_REPORT-Bewegungen bilden."""
    con.execute("""
        create or replace table export_zuordnungen as
        select
            tfze_or_tens as "TfzE oder tEns*",
            period_start_utc as "Beginn der Zuordnung*",
            period_end_utc as "Ende der Zuordnung",
            user_vens as "Nutzer-vEns*",
            halter_marktpartner_id as "Marktpartner ID für Nutzungsüberlassung"
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and export_ready = true
    """)

    con.execute("""
        create or replace table export_nutzungsmeldung as
        select
            tfze_or_tens as "TfzE oder tEns*",
            period_start_utc as "Beginn der Nutzung*",
            period_end_utc as "Ende der Nutzung",
            user_vens as "Nutzer-vEns*",
            halter_marktpartner_id as "Marktpartner ID für Nutzungsüberlassung*",
            'Übergabemeldung' as "Übernahmeanfrage oder Übergabemeldung?"
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and export_ready = true
    """)

def export_table(con, table, file_name):
    """Eine DuckDB-Tabelle als CSV-Datei nach data/03_exports schreiben."""
    path = EXP_DIR / file_name
    con.execute(f"copy {qident(table)} to ? (header true, delimiter ';')", [str(path)])
    print(f"Export: {path}")

def main():
    """
    Vollständigen Tageslauf ausführen.

    WICHTIG:
    Die produktive Datei data/02_duckdb/netzentgelt.duckdb wird nicht direkt
    beschrieben. Stattdessen wird zuerst eine komplett neue temporäre Datenbank
    aufgebaut. Nur wenn ALLE Schritte erfolgreich waren, ersetzt diese temporäre
    Datei den letzten produktiven Stand.

    Vorteil:
    Scheitert ein Import, eine Berechnung oder ein Export, bleibt die letzte
    funktionierende Tages-Datenbank unverändert erhalten.
    """

    # Eventuell übrig gebliebene Build-Dateien eines abgebrochenen älteren Laufs
    # entfernen. Die produktive DB_PATH wird hier bewusst NICHT gelöscht.
    remove_if_exists(DB_BUILD_PATH)
    remove_if_exists(Path(str(DB_BUILD_PATH) + ".wal"))

    con = None

    try:
        print("")
        print("=" * 80)
        print("Starte vollständigen Neuaufbau der Tages-Datenbank")
        print(f"Temporäre Build-Datenbank: {DB_BUILD_PATH}")
        print(f"Produktive Tages-Datenbank: {DB_PATH}")
        print("=" * 80)

        # Neue leere DuckDB-Datei öffnen.
        # DuckDB erstellt DB_BUILD_PATH automatisch neu.
        con = duckdb.connect(str(DB_BUILD_PATH))

        # 1. Rohdaten frisch importieren.
        run_id, imported = import_csvs(con)

        # 2. Lok-Mapping einlesen.
        import_mapping(con)

        # 3. Bewegungsdaten und Transport-Routen neu berechnen.
        # Die Reihenfolge ist relevant:
        # build_core() benötigt core_transport_route bereits für seinen Join.
        build_loco_events(con)
        build_transport_routes(con)
        build_core(con, run_id)

        # 4. Findings und fachliche Exporttabellen neu berechnen.
        build_findings(con, run_id)
        build_exports(con)

        # 5. Sämtliche CSV-Ausgaben neu schreiben.
        # Bestehende Dateien gleichen Namens werden dabei überschrieben.
        for table, name in [
            ("raw_import_run", "raw_import_run.csv"),
            ("stg_loco_events", "stg_loco_events.csv"),
            ("core_loco_timeline", "core_loco_timeline.csv"),
            ("dq_findings", "dq_findings.csv"),
            ("export_zuordnungen", "export_zuordnungen.csv"),
            ("export_nutzungsmeldung", "export_nutzungsmeldung.csv"),
            ("stg_loco_events_skipped", "stg_loco_events_skipped.csv"),
            ("stg_transport_details_enriched", "stg_transport_details_enriched.csv"),
            ("core_transport_route", "core_transport_route.csv"),
        ]:
            export_table(con, table, name)

        # 6. Kennzahlen des erfolgreich berechneten Laufs ermitteln.
        summary = con.execute("""
            select
                (select count(*) from stg_loco_events) as stg_events,
                (select count(*) from core_loco_timeline) as core_rows,
                (select count(*) from dq_findings where severity='ERROR') as errors,
                (select count(*) from dq_findings where severity='WARNING') as warnings,
                (select count(*) from dq_findings where severity='MANUAL_REVIEW') as manual_reviews,
                (select count(*) from export_zuordnungen) as exportable_rows
        """).fetchone()

        print("")
        print("MVP-Lauf abgeschlossen:", run_id)
        print(
            f"Events: {summary[0]} | "
            f"Core: {summary[1]} | "
            f"Errors: {summary[2]} | "
            f"Warnings: {summary[3]} | "
            f"Manual Reviews: {summary[4]} | "
            f"Exportfähig: {summary[5]}"
        )

        # 7. Tageslauf zusätzlich als einfache Textdatei protokollieren.
        # Die Logdateien werden historisch behalten.
        (LOG_DIR / f"{run_id}_summary.txt").write_text(
            (
                f"run_id={run_id}\n"
                f"events={summary[0]}\n"
                f"core_rows={summary[1]}\n"
                f"errors={summary[2]}\n"
                f"warnings={summary[3]}\n"
                f"manual_reviews={summary[4]}\n"
                f"exportable_rows={summary[5]}\n"
            ),
            encoding="utf-8"
        )

        # 8. Verbindung sauber schließen, damit DuckDB alle Daten vollständig
        # auf die Build-Datei schreibt und keine Dateisperre bestehen bleibt.
        con.close()
        con = None

        # 9. Erst jetzt den letzten produktiven Stand ersetzen.
        # os.replace() überschreibt DB_PATH atomar, soweit dies vom Dateisystem
        # unterstützt wird. Falls das Ersetzen fehlschlägt, bleibt DB_PATH
        # unverändert bestehen und die Exception wird unten sichtbar ausgegeben.
        os.replace(DB_BUILD_PATH, DB_PATH)

        # DuckDB kann in Sonderfällen eine WAL-Datei hinterlassen.
        # Nach erfolgreichem Close sollte sie nicht mehr benötigt werden.
        remove_if_exists(Path(str(DB_BUILD_PATH) + ".wal"))

        print("")
        print(f"Tages-Datenbank erfolgreich ersetzt: {DB_PATH}")

    except Exception:
        # Bei einem Fehler:
        # - offene Verbindung schließen,
        # - temporäre Build-Dateien entfernen,
        # - produktive Tages-Datenbank unverändert behalten,
        # - ursprünglichen Fehler erneut auslösen, damit er im Terminal sichtbar ist.
        print("")
        print("FEHLER: Tages-Datenbank konnte nicht vollständig neu aufgebaut werden.")
        print("Die letzte funktionierende netzentgelt.duckdb bleibt erhalten.")

        if con is not None:
            con.close()

        remove_if_exists(DB_BUILD_PATH)
        remove_if_exists(Path(str(DB_BUILD_PATH) + ".wal"))

        raise

if __name__ == "__main__":
    main()
