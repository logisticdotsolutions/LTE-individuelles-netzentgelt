# NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607
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
import csv
import json
import os
import duckdb
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from error_rules import build_findings, qident, sql_lit, table_exists
from export_module import build_export_tables
from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table
from pipeline.quality_gate_incremental import apply_r016_to_quality_gate_tables
from manual_override_module import (
    apply_raw_manual_overrides,
    apply_staging_manual_overrides,
    import_manual_overrides,
)
from rule_engine_hardening_phase6b import (
    apply_core_assignment_fallbacks,
    harden_findings_and_export_policy,
)
# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_V1_20260608
from rule_engine_hardening_phase6c import (
    harden_findings_and_segments_phase6c,
    prepare_timeline_context_phase6c,
)
# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6D_V1_20260608
from rule_engine_hardening_phase6d import (
    finalize_quality_gate_phase6d,
    insert_gap_only_day_findings_phase6d,
)
# NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608
from dummy_locomotive_module import (
    build_dummy_locomotive_catalog,
    consolidate_dummy_locomotive_findings,
    exclude_dummy_locomotives_from_staging,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "00_raw"
MAP_DIR = ROOT / "data" / "01_mapping"
DB_DIR = ROOT / "data" / "02_duckdb"
EXP_DIR = ROOT / "data" / "03_exports"
LOG_DIR = ROOT / "data" / "04_logs"
RAW_IMPORT_MANIFEST_PATH = RAW_DIR / "raw_import_manifest.json"
REQUIRED_RAW_SOURCE_FILES = {
    "locomotivemovement.csv",
    "transportdetail.csv",
    "locomotive.csv",
}
# NETZENTGELT_HARDENING_V1_20260607: stabiler Rohdaten-Snapshot
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



def get_source_snapshot_at_utc() -> str:
    """
    Stabilen Zeitpunkt des letzten vollständig übernommenen Azure-Snapshots lesen.

    Das Manifest wird erst geschrieben, nachdem alle benötigten Rohdaten-Dateien
    validiert und gemeinsam übernommen wurden. Der Fallback über Datei-mtime hält
    bestehende lokale Entwicklungsstände weiterhin lauffähig.
    """
    if RAW_IMPORT_MANIFEST_PATH.exists():
        try:
            payload = json.loads(
                RAW_IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
            )
            value = str(payload.get("snapshot_at_utc", "")).strip()

            if value:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)

                return parsed.astimezone(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    expected_files = [
        RAW_DIR / "LocomotiveMovement.csv",
        RAW_DIR / "TransportDetail.csv",
        RAW_DIR / "Locomotive.csv",
    ]
    existing_files = [path for path in expected_files if path.exists()]

    if existing_files:
        newest_timestamp = max(path.stat().st_mtime for path in existing_files)
        return datetime.fromtimestamp(
            newest_timestamp,
            tz=timezone.utc,
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return ts()


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
            source_snapshot_at_utc varchar,
            source_file varchar,
            target_table varchar,
            source_hash varchar,
            row_count bigint,
            status varchar,
            error_message varchar
        )
    """)
    run_id = datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S")
    source_snapshot_at_utc = get_source_snapshot_at_utc()
    files = sorted(RAW_DIR.glob("*.csv"))
    if not files:
        print("Keine CSVs in data/00_raw gefunden. Lege dort die DataLake-CSV-Dateien ab und starte erneut.")
        return run_id, []
    imported = []
    successful_source_files = []
    import_failures = []

    for file in files:
        target = safe_name(file.name)
        try:
            con.execute(f"""
                create or replace table {qident(target)} as
                select * from read_csv_auto(?, union_by_name=true, all_varchar=true, filename=true, ignore_errors=true)
            """, [str(file)])
            rc = con.execute(f"select count(*) from {qident(target)}").fetchone()[0]
            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [run_id, ts(), source_snapshot_at_utc, file.name, target, sha256(file), rc, "imported", None])
            imported.append(target)
            successful_source_files.append(file.name.lower())
            print(f"Importiert: {file.name} -> {target} ({rc} Zeilen)")
        except Exception as e:
            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [run_id, ts(), source_snapshot_at_utc, file.name, target, sha256(file), 0, "failed", str(e)])
            import_failures.append(f"{file.name}: {e}")
            print(f"FEHLER Import {file.name}: {e}")

    missing_required_files = sorted(
        REQUIRED_RAW_SOURCE_FILES - set(successful_source_files)
    )

    if missing_required_files or import_failures:
        details = []

        if missing_required_files:
            details.append(
                "Fehlende Pflichtimporte: "
                + ", ".join(missing_required_files)
            )

        if import_failures:
            details.append(
                "Fehlgeschlagene CSV-Importe: "
                + " | ".join(import_failures)
            )

        raise RuntimeError(
            "Rohdatenimport unvollständig. Fachliche Berechnung wird abgebrochen. "
            + " ".join(details)
        )

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


def normalize_company_name_py(value):
    """
    Firmennamen für eine konservative technische Gleichheitsprüfung normalisieren.

    Die Normalisierung entfernt ausschließlich Schreibvarianten wie:
    - Groß-/Kleinschreibung
    - Umlaute / Akzente
    - Leerzeichen
    - Satzzeichen und Bindestriche

    Sie führt KEINE unscharfe Zuordnung durch.
    """
    if value is None:
        return ""

    text = str(value).strip().lower()

    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    return re.sub(r"[^a-z0-9]+", "", text)


def create_company_normalization_macro(con):
    """
    SQL-Makro analog zu normalize_company_name_py() bereitstellen.

    Dadurch verwenden Python-Import und DuckDB-Joins dieselbe konservative
    Normalisierung.
    """
    con.execute("""
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
    """)


def find_first_existing_file(directory: Path, candidates):
    """Erste vorhandene Datei aus einer Kandidatenliste zurückgeben."""
    for candidate in candidates:
        path = directory / candidate

        if path.exists():
            return path

    return None


def import_market_partner_reference(con):
    """
    Offizielle Marktpartnerliste der DB Energie einlesen.

    Erwartete Ablage:
        data/01_mapping/vens liste.csv

    Alternativ werden auch vens_liste.csv und vens-liste.csv unterstützt.

    Die Quelldatei enthält mehrere fachliche Bereiche. Jeder Datensatz wird
    rollenbezogen gespeichert, damit ANu-vEns und ANe-tEns nicht vermischt
    werden.
    """
    create_company_normalization_macro(con)

    con.execute("""
        create or replace table cfg_market_partner_role (
            role_code varchar,
            role_label varchar,
            company_name_official varchar,
            company_name_normalized varchar,
            market_partner_id varchar,
            source_file varchar,
            source_line_no bigint
        )
    """)

    reference_path = find_first_existing_file(
        MAP_DIR,
        [
            "vens liste.csv",
            "vens_liste.csv",
            "vens-liste.csv",
        ],
    )

    if reference_path is None:
        print(
            "WARNUNG: Keine offizielle Marktpartnerliste gefunden. "
            "Erwartet: data/01_mapping/vens liste.csv"
        )

    else:
        role_map = {
            "ANu-vEns (Nutzer) im Bahnstromnetz": "ANU_VENS",
            "ANe-tEns (Halter) im Bahnstromnetz": "ANE_TENS",
            "Dienstleister im Bahnstromnetz": "DIENSTLEISTER",
            "Netzbetreiber im Bahnstromnetz": "NETZBETREIBER",
            "Stromlieferanten im Bahnstromnetz": "STROMLIEFERANT",
            "Bilankreisverantwortliche im Bahnstromnetz": "BILANZKREISVERANTWORTLICHER",
            "Übertragungsnetzbetreiber im Bahnstromnetz": "UEBERTRAGUNGSNETZBETREIBER",
            "Einsatzverantwortliche im Bahnstromnetz": "EINSATZVERANTWORTLICHER",
            "Betreiber einer technischen Ressource im Bahnstromnetz": "BETREIBER_TECHNISCHE_RESSOURCE",
            "Messdienstleister im Bahnstromnetz": "MESSDIENSTLEISTER",
        }

        current_role_code = None
        current_role_label = None
        insert_rows = []

        with open(
            reference_path,
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as csv_file:
            reader = csv.reader(
                csv_file,
                delimiter=";",
            )

            for line_no, row in enumerate(reader, start=1):
                if not row:
                    continue

                first_value = row[0].strip() if len(row) >= 1 else ""
                second_value = row[1].strip() if len(row) >= 2 else ""

                if first_value in role_map:
                    current_role_code = role_map[first_value]
                    current_role_label = first_value
                    continue

                if (
                    current_role_code is None
                    or not first_value
                    or first_value == "Unternehmensname"
                    or not second_value
                ):
                    continue

                insert_rows.append(
                    (
                        current_role_code,
                        current_role_label,
                        first_value,
                        normalize_company_name_py(first_value),
                        second_value,
                        reference_path.name,
                        line_no,
                    )
                )

        if insert_rows:
            con.executemany(
                """
                insert into cfg_market_partner_role values (
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                insert_rows,
            )

        print(
            f"Marktpartnerliste importiert: {reference_path.name} "
            f"({len(insert_rows)} rollenbezogene Einträge)"
        )

    # Nur eindeutige offizielle Namen dürfen automatisch verwendet werden.
    con.execute("""
        create or replace table cfg_market_partner_role_effective as
        select
            role_code,
            company_name_normalized,
            max(company_name_official) as company_name_official,
            max(market_partner_id) as market_partner_id
        from cfg_market_partner_role
        where nullif(trim(market_partner_id), '') is not null
        group by
            role_code,
            company_name_normalized
        having count(distinct market_partner_id) = 1
    """)

    con.execute("""
        create or replace table cfg_market_partner_role_conflicts as
        select
            role_code,
            company_name_normalized,
            string_agg(
                distinct company_name_official,
                ' | '
                order by company_name_official
            ) as company_names,
            string_agg(
                distinct market_partner_id,
                ' | '
                order by market_partner_id
            ) as market_partner_ids,
            count(distinct market_partner_id) as distinct_market_partner_ids
        from cfg_market_partner_role
        where nullif(trim(market_partner_id), '') is not null
        group by
            role_code,
            company_name_normalized
        having count(distinct market_partner_id) > 1
    """)


def import_market_partner_mapping(con):
    """
    Vollständige, geprüfte Marktpartner-Mappingtabelle einlesen.

    Erwartete Ablage:
        data/01_mapping/market_partner_mapping_import.csv

    Die Datei wird aus Relations.xlsx und der offiziellen vEns-/MP-ID-Liste
    aufgebaut. Für den produktiven Join werden ausschließlich Zeilen verwendet,
    die:
    - active_flag = Y besitzen,
    - eine DataLake-Quellbezeichnung enthalten,
    - eine MP-ID enthalten,
    - für dieselbe Rolle und normalisierte DataLake-Bezeichnung eindeutig sind,
    - und deren MP-ID in der offiziellen Marktpartnerliste für diese Rolle
      tatsächlich vorhanden ist.

    Dadurch bleibt die Zuordnung nachvollziehbar und auditierbar. Unsichere
    oder widersprüchliche Treffer werden niemals stillschweigend verwendet.
    """
    create_company_normalization_macro(con)

    mapping_path = MAP_DIR / "market_partner_mapping_import.csv"

    if mapping_path.exists():
        con.execute("""
            create or replace table cfg_market_partner_mapping as
            select
                nullif(trim(source_system), '') as source_system,
                nullif(trim(source_field), '') as source_field,
                nullif(trim(source_value), '') as source_value,
                upper(nullif(trim(role_code), '')) as role_code,
                nullif(trim(official_company_name), '') as official_company_name,
                nullif(trim(market_partner_id), '') as market_partner_id,
                upper(coalesce(nullif(trim(active_flag), ''), 'N')) as active_flag,
                nullif(trim(match_method), '') as match_method,
                try_cast(nullif(trim(match_score), '') as double) as match_score,
                upper(coalesce(nullif(trim(manual_review), ''), 'N')) as manual_review,
                nullif(trim(comment), '') as comment,
                normalize_company_name(source_value) as source_value_normalized,
                normalize_company_name(official_company_name) as official_company_name_normalized
            from read_csv_auto(
                ?,
                delim=';',
                header=true,
                all_varchar=true,
                ignore_errors=true
            )
        """, [str(mapping_path)])

        imported_count = con.execute(
            "select count(*) from cfg_market_partner_mapping"
        ).fetchone()[0]

        print(
            f"Marktpartner-Mapping importiert: {mapping_path.name} "
            f"({imported_count} Zeilen)"
        )

    else:
        con.execute("""
            create or replace table cfg_market_partner_mapping (
                source_system varchar,
                source_field varchar,
                source_value varchar,
                role_code varchar,
                official_company_name varchar,
                market_partner_id varchar,
                active_flag varchar,
                match_method varchar,
                match_score double,
                manual_review varchar,
                comment varchar,
                source_value_normalized varchar,
                official_company_name_normalized varchar
            )
        """)

        print(
            "WARNUNG: Vollständige Mappingdatei fehlt. "
            "Erwartet: data/01_mapping/market_partner_mapping_import.csv. "
            "Exakte offizielle Firmennamen werden weiterhin als Fallback erkannt."
        )

    # Aktive Mappingzeilen, deren MP-ID nicht rollenbezogen in der offiziellen
    # Marktpartnerliste existiert, dürfen nicht produktiv verwendet werden.
    con.execute("""
        create or replace table cfg_market_partner_mapping_invalid as
        select
            m.*,
            'MP-ID ist für die angegebene Rolle nicht in der offiziellen Marktpartnerliste vorhanden.' as validation_error
        from cfg_market_partner_mapping m
        left join cfg_market_partner_role r
          on r.role_code = m.role_code
         and r.market_partner_id = m.market_partner_id
        where m.active_flag = 'Y'
          and nullif(trim(m.market_partner_id), '') is not null
          and r.market_partner_id is null
    """)

    # Konflikte: dieselbe normalisierte DataLake-Bezeichnung und Rolle zeigt auf
    # mehrere aktive MP-IDs. Solche Fälle werden bewusst nicht automatisch aufgelöst.
    con.execute("""
        create or replace table cfg_market_partner_mapping_conflicts as
        select
            role_code,
            source_value_normalized,
            string_agg(
                distinct source_value,
                ' | '
                order by source_value
            ) as source_values,
            string_agg(
                distinct official_company_name,
                ' | '
                order by official_company_name
            ) as official_company_names,
            string_agg(
                distinct market_partner_id,
                ' | '
                order by market_partner_id
            ) as market_partner_ids,
            count(distinct market_partner_id) as distinct_market_partner_ids
        from cfg_market_partner_mapping
        where active_flag = 'Y'
          and nullif(trim(source_value_normalized), '') is not null
          and nullif(trim(market_partner_id), '') is not null
        group by
            role_code,
            source_value_normalized
        having count(distinct market_partner_id) > 1
    """)

    # Produktiv verwendbare Mappings: nur aktiv, offiziell validiert und eindeutig.
    con.execute("""
        create or replace table cfg_market_partner_mapping_effective as
        select
            m.role_code,
            m.source_value_normalized,
            max(m.source_value) as source_value,
            max(m.official_company_name) as official_company_name,
            max(m.market_partner_id) as market_partner_id,
            max(m.match_method) as match_method,
            max(m.match_score) as match_score
        from cfg_market_partner_mapping m
        inner join cfg_market_partner_role r
          on r.role_code = m.role_code
         and r.market_partner_id = m.market_partner_id
        where m.active_flag = 'Y'
          and nullif(trim(m.source_value_normalized), '') is not null
          and nullif(trim(m.market_partner_id), '') is not null
        group by
            m.role_code,
            m.source_value_normalized
        having count(distinct m.market_partner_id) = 1
    """)

    effective_count = con.execute(
        "select count(*) from cfg_market_partner_mapping_effective"
    ).fetchone()[0]

    conflict_count = con.execute(
        "select count(*) from cfg_market_partner_mapping_conflicts"
    ).fetchone()[0]

    invalid_count = con.execute(
        "select count(*) from cfg_market_partner_mapping_invalid"
    ).fetchone()[0]

    print(
        "Produktive Marktpartner-Mappings: "
        f"{effective_count} | Konflikte={conflict_count} | Ungültig={invalid_count}"
    )


def import_vens_tens_exception(con):
    """
    Explizite Ausnahmeliste für PerformingRUs einlesen, für die im MVP
    keine vEns-/tEns-Prüfung erforderlich ist.

    Erwartete Ablage:
        data/01_mapping/vens_tens_exception.csv

    Die Liste ist bewusst granular:
    - exempt_vens = Y unterdrückt vEns-bezogene Hinweise.
    - exempt_tens = Y ist für spätere tEns-Regeln vorbereitet.
    - active_flag = Y aktiviert die Ausnahme.

    Andere Regeln, insbesondere PerformingRU-MP-ID (R007), fehlende
    PerformingRU (R009) oder Zeitachsenfehler, bleiben davon unberührt.
    """
    create_company_normalization_macro(con)

    exception_path = MAP_DIR / "vens_tens_exception.csv"

    if exception_path.exists():
        con.execute("""
            create or replace table cfg_vens_tens_exception as
            select
                nullif(trim(source_system), '') as source_system,
                nullif(trim(source_field), '') as source_field,
                nullif(trim(source_value), '') as source_value,
                normalize_company_name(source_value) as source_value_normalized,
                upper(coalesce(nullif(trim(exempt_vens), ''), 'N')) = 'Y' as exempt_vens,
                upper(coalesce(nullif(trim(exempt_tens), ''), 'N')) = 'Y' as exempt_tens,
                upper(coalesce(nullif(trim(active_flag), ''), 'N')) as active_flag,
                nullif(trim(comment), '') as comment
            from read_csv_auto(
                ?,
                delim=';',
                header=true,
                all_varchar=true,
                ignore_errors=true
            )
        """, [str(exception_path)])

        imported_count = con.execute(
            "select count(*) from cfg_vens_tens_exception"
        ).fetchone()[0]

        print(
            f"vEns-/tEns-Ausnahmeliste importiert: {exception_path.name} "
            f"({imported_count} Zeilen)"
        )

    else:
        con.execute("""
            create or replace table cfg_vens_tens_exception (
                source_system varchar,
                source_field varchar,
                source_value varchar,
                source_value_normalized varchar,
                exempt_vens boolean,
                exempt_tens boolean,
                active_flag varchar,
                comment varchar
            )
        """)

        print(
            "HINWEIS: Keine vEns-/tEns-Ausnahmeliste gefunden. "
            "Erwartet: data/01_mapping/vens_tens_exception.csv"
        )

    con.execute("""
        create or replace table cfg_vens_tens_exception_conflicts as
        select
            source_value_normalized,
            string_agg(distinct source_value, ' | ' order by source_value) as source_values,
            count(*) as row_count,
            count(distinct exempt_vens) as distinct_exempt_vens,
            count(distinct exempt_tens) as distinct_exempt_tens
        from cfg_vens_tens_exception
        where active_flag = 'Y'
          and nullif(trim(source_value_normalized), '') is not null
        group by source_value_normalized
        having count(distinct exempt_vens) > 1
            or count(distinct exempt_tens) > 1
    """)

    con.execute("""
        create or replace table cfg_vens_tens_exception_effective as
        select
            source_value_normalized,
            max(source_value) as source_value,
            bool_or(exempt_vens) as exempt_vens,
            bool_or(exempt_tens) as exempt_tens,
            max(comment) as comment
        from cfg_vens_tens_exception
        where active_flag = 'Y'
          and nullif(trim(source_value_normalized), '') is not null
        group by source_value_normalized
        having count(distinct exempt_vens) = 1
           and count(distinct exempt_tens) = 1
    """)

    effective_count = con.execute(
        "select count(*) from cfg_vens_tens_exception_effective"
    ).fetchone()[0]

    conflict_count = con.execute(
        "select count(*) from cfg_vens_tens_exception_conflicts"
    ).fetchone()[0]

    print(
        "Produktive vEns-/tEns-Ausnahmen: "
        f"{effective_count} | Konflikte={conflict_count}"
    )


def build_unresolved_performing_ru_market_partner_alias(con):
    """
    Nicht auflösbare PerformingRU-Schreibweisen für die manuelle Pflege aggregieren.

    Die MP-ID für die Nutzungsüberlassung ist die MP-ID der PerformingRU.
    PerformingRUs auf der expliziten vEns-/tEns-Ausnahmeliste werden bewusst
    nicht in diese Queue aufgenommen.

    Die Tabelle ist verdichtet: Eine unbekannte PerformingRU-Schreibweise
    erscheint nur einmal mit Anzahl, erstem und letztem Auftreten.
    """
    create_company_normalization_macro(con)

    con.execute("""
        create or replace table dq_unresolved_performing_ru_market_partner_alias as
        select
            'ANU_VENS' as role_code,
            'PerformingRU' as source_field,
            performing_ru as source_value,
            normalize_company_name(performing_ru) as source_value_normalized,
            count(*) as affected_movement_rows,
            count(distinct loco_no) as affected_locos,
            count(distinct transport_number) as affected_transports,
            min(period_start_utc) as first_seen_utc,
            max(coalesce(period_end_utc, period_start_utc)) as last_seen_utc,
            'Kein eindeutiger Treffer in market_partner_mapping_import.csv oder offizieller ANU_VENS-Rollenliste.' as reason,
            'market_partner_mapping_import.csv prüfen, DataLake-Bezeichnung ergänzen oder Active_Flag nach fachlicher Freigabe auf Y setzen.' as suggested_action
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and nullif(trim(performing_ru), '') is not null
          and nullif(trim(performing_ru_marktpartner_id), '') is null
          and coalesce(vens_tens_exception_flag, false) = false
        group by
            performing_ru,
            normalize_company_name(performing_ru)
        order by
            affected_movement_rows desc,
            source_value
    """)

    unresolved_count = con.execute(
        "select count(*) from dq_unresolved_performing_ru_market_partner_alias"
    ).fetchone()[0]

    if unresolved_count > 0:
        print(
            "WARNUNG: "
            f"{unresolved_count} ungeklärte PerformingRU-Schreibweisen gefunden. "
            "Siehe Export dq_unresolved_performing_ru_market_partner_alias.csv"
        )




def build_cancelled_transport_exclusions(con):
    """
    Stornierte Transporte zentral und auditierbar ausschließen.

    Fachliche Quelle für den Status ist TransportDetail.csv. Dadurch werden
    auch statuslose Bewegungszeilen aus LocomotiveMovement.csv über ihre
    TransportNumber ausgeschlossen. Die Audit-Tabelle enthält zusätzlich
    TransportLastEditDate und TransportLastEditBy aus LocomotiveMovement.csv,
    sofern die Spalten im DataLake-Export vorhanden sind.

    NETZENTGELT_CANCELLED_HOTFIX_V2_20260607
    """
    con.execute("""
        create or replace table cfg_excluded_cancelled_transports (
            transport_number varchar,
            transport_status varchar
        )
    """)

    con.execute("""
        create or replace table audit_excluded_cancelled_transports (
            source_table varchar,
            transport_number varchar,
            transport_status varchar,
            affected_rows bigint,
            first_seen_utc timestamp,
            last_seen_utc timestamp,
            transport_last_edit_date timestamp,
            transport_last_edit_by varchar
        )
    """)

    transport_detail_table = "raw_transportdetail"

    if not table_exists(con, transport_detail_table):
        print(
            "WARNUNG: Keine raw_transportdetail-Tabelle vorhanden. "
            "Cancelled-Transportausschluss bleibt leer."
        )
        return

    transport_detail_columns = columns(con, transport_detail_table)
    transport_number_expr = pick_text(
        transport_detail_columns,
        ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
    )
    transport_status_expr = pick_text(
        transport_detail_columns,
        ["TransportStatus", "Status"],
    )

    if transport_number_expr == "NULL" or transport_status_expr == "NULL":
        print(
            "WARNUNG: TransportDetail.csv enthält keine auswertbare "
            "TransportNumber- oder TransportStatus-Spalte. "
            "Cancelled-Transportausschluss bleibt leer."
        )
        return

    con.execute(f"""
        create or replace table cfg_excluded_cancelled_transports as
        with source_rows as (
            select
                {transport_number_expr} as transport_number,
                {transport_status_expr} as transport_status
            from {qident(transport_detail_table)}
        )
        select
            transport_number,
            string_agg(
                distinct transport_status,
                ' | '
                order by transport_status
            ) as transport_status
        from source_rows
        where transport_number is not null
          and regexp_replace(
                lower(coalesce(transport_status, '')),
                '[^a-z]+',
                '',
                'g'
          ) in ('cancelled', 'canceled')
        group by transport_number
    """)

    audit_selects = []

    for source_table in ["raw_transportdetail", "raw_locomotivemovement"]:
        if not table_exists(con, source_table):
            continue

        source_columns = columns(con, source_table)
        source_transport_number = pick_text(
            source_columns,
            ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
        )

        if source_transport_number == "NULL":
            continue

        first_seen_source = coalesce(
            source_columns,
            [
                "ActualDeparture",
                "LocomotiveActualDeparture",
                "ActualArrival",
                "LocomotiveActualArrival",
                "TransportLastEditDate",
            ],
        )
        last_seen_source = coalesce(
            source_columns,
            [
                "ActualArrival",
                "LocomotiveActualArrival",
                "ActualDeparture",
                "LocomotiveActualDeparture",
                "TransportLastEditDate",
            ],
        )
        transport_last_edit_date = pick_text(
            source_columns,
            ["TransportLastEditDate"],
        )
        transport_last_edit_by = pick_text(
            source_columns,
            ["TransportLastEditBy"],
        )

        first_seen_sql = (
            "null::timestamp"
            if first_seen_source == "NULL"
            else f"try_cast({first_seen_source} as timestamp)"
        )
        last_seen_sql = (
            "null::timestamp"
            if last_seen_source == "NULL"
            else f"try_cast({last_seen_source} as timestamp)"
        )
        last_edit_date_sql = (
            "null::timestamp"
            if transport_last_edit_date == "NULL"
            else f"max(try_cast({transport_last_edit_date} as timestamp))"
        )
        last_edit_by_sql = (
            "null::varchar"
            if transport_last_edit_by == "NULL"
            else (
                "string_agg("
                f"distinct {transport_last_edit_by}, "
                "' | ' "
                f"order by {transport_last_edit_by}"
                f") filter (where {transport_last_edit_by} is not null)"
            )
        )
        source_table_literal = source_table.replace("'", "''")

        audit_selects.append(f"""
            select
                '{source_table_literal}' as source_table,
                {source_transport_number} as transport_number,
                excluded.transport_status,
                count(*) as affected_rows,
                min({first_seen_sql}) as first_seen_utc,
                max({last_seen_sql}) as last_seen_utc,
                {last_edit_date_sql} as transport_last_edit_date,
                {last_edit_by_sql} as transport_last_edit_by
            from {qident(source_table)} source_rows
            join cfg_excluded_cancelled_transports excluded
              on excluded.transport_number = {source_transport_number}
            group by
                {source_transport_number},
                excluded.transport_status
        """)

    if audit_selects:
        con.execute(
            "create or replace table audit_excluded_cancelled_transports as\n"
            + "\nunion all\n".join(audit_selects)
        )

    excluded_transport_count = con.execute(
        "select count(*) from cfg_excluded_cancelled_transports"
    ).fetchone()[0]
    audit_row_count = con.execute(
        "select count(*) from audit_excluded_cancelled_transports"
    ).fetchone()[0]

    print(
        "Cancelled-Transporte ausgeschlossen: "
        f"{excluded_transport_count} Transporte | "
        f"{audit_row_count} Audit-Zeilen."
    )


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

    # Rohdaten einmalig materialisieren. Dadurch werden der stg_loco_events-Build
    # und stg_loco_events_skipped aus derselben physischen Tabelle bedient –
    # statt 2–3 separater Quell-Scans nur noch einer.
    con.execute(f"""
        create or replace temp table tmp_loco_prepared as
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
            {distance} as distance,
            case
                when upper({origin_country}) = {home}
                  or upper({destination_country}) = {home}
                then true else false
            end as row_has_home
        from {qident(source)}
        where not exists (
            select 1
            from cfg_excluded_cancelled_transports excluded
            where excluded.transport_number = {transport_number}
        )
    """)

    con.execute(f"""
        create or replace table stg_loco_events as
        with anchor as (
            select max(coalesce(actual_departure_ts, actual_arrival_ts)) as anchor_ts
            from tmp_loco_prepared
        ),
        relevant_loco as (
            select distinct p.loco_no
            from tmp_loco_prepared p
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
            from tmp_loco_prepared p
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

    # stg_loco_events_skipped: Zeilen ableiten, die NICHT in stg_loco_events landen.
    # tmp_loco_prepared wurde bereits aus dem Rohdaten-Scan befüllt (kein erneuter Scan).
    # relevant_locos aus stg_loco_events entspricht der relevant_loco-Menge aus dem Build.
    con.execute(f"""
        create or replace table stg_loco_events_skipped as
        with relevant_locos as (
            select distinct loco_no from stg_loco_events
            where loco_no is not null and loco_no <> ''
        )
        select
            '{source}' as source_table,
            p.source_row_id,
            case
                when p.loco_no is null or p.loco_no = ''
                    then 'Loknummer fehlt; Datensatz kann keiner Lok-Zeitachse zugeordnet werden.'
                else
                    'Lok im Lookback-Zeitraum ohne DE-Bezug in OriginCountry/DestinationCountry; nicht in diese Auswertung aufgenommen.'
            end as skip_reason
        from tmp_loco_prepared p
        where p.loco_no is null
           or p.loco_no = ''
           or not exists (
                select 1 from relevant_locos r where r.loco_no = p.loco_no
           )
    """)

    skipped = con.execute("select count(*) from stg_loco_events_skipped").fetchone()[0]
    loaded = con.execute("select count(*) from stg_loco_events").fetchone()[0]

    print(
        f"Staging erstellt: {loaded} Zeilen verarbeitet, {skipped} Zeilen nicht aufgenommen. "
        f"Logik: relevante Loks mit DE-Bezug im letzten {LOOKBACK_MONTHS}-Monatsfenster, danach komplette Lok-Historie."
    )

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
          and not exists (
                select 1
                from cfg_excluded_cancelled_transports excluded
                where excluded.transport_number = {transport_number}
          )
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

def _build_performing_ru_mp_lookup(con):
    """
    MP-ID-Lookup für alle distinct performing_ru-Werte vorberechnen.

    normalize_company_name() wird so nur einmal je distinct Wert berechnet
    statt einmal pro Zeile in stg_loco_events. Bei typischen Datensätzen
    reduziert das den Aufwand von ~100.000 auf ~100 Normalisierungsaufrufe.
    """
    con.execute("""
        create or replace temp table tmp_performing_ru_mp_lookup as
        with distinct_values as (
            select distinct performing_ru
            from stg_loco_events
            where performing_ru is not null
        ),
        normalized as (
            select
                performing_ru,
                normalize_company_name(performing_ru) as performing_ru_normalized
            from distinct_values
        )
        select
            n.performing_ru,
            coalesce(
                mapping_anu.market_partner_id,
                direct_anu.market_partner_id
            ) as performing_ru_marktpartner_id,
            case
                when mapping_anu.market_partner_id is not null then 'MAPPING_IMPORT'
                when direct_anu.market_partner_id is not null then 'OFFICIAL_NAME_EXACT'
                else 'UNRESOLVED'
            end as performing_ru_marktpartner_id_source,
            coalesce(
                mapping_ane.market_partner_id,
                direct_ane.market_partner_id
            ) as holder_market_partner_id,
            case
                when mapping_ane.market_partner_id is not null then 'MAPPING_IMPORT'
                when direct_ane.market_partner_id is not null then 'OFFICIAL_NAME_EXACT'
                else 'UNRESOLVED'
            end as holder_market_partner_id_source,
            exc.exempt_vens,
            exc.exempt_tens,
            exc.source_value_normalized as exc_source_value_normalized,
            exc.comment as vens_tens_exception_comment
        from normalized n
        left join cfg_market_partner_mapping_effective mapping_anu
            on mapping_anu.role_code = 'ANU_VENS'
            and mapping_anu.source_value_normalized = n.performing_ru_normalized
        left join cfg_market_partner_role_effective direct_anu
            on direct_anu.role_code = 'ANU_VENS'
            and direct_anu.company_name_normalized = n.performing_ru_normalized
        left join cfg_market_partner_mapping_effective mapping_ane
            on mapping_ane.role_code = 'ANE_TENS'
            and mapping_ane.source_value_normalized = n.performing_ru_normalized
        left join cfg_market_partner_role_effective direct_ane
            on direct_ane.role_code = 'ANE_TENS'
            and direct_ane.company_name_normalized = n.performing_ru_normalized
        left join cfg_vens_tens_exception_effective exc
            on exc.source_value_normalized = n.performing_ru_normalized
    """)


def _build_core_timeline_sql(con, run_id):
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

                pru.performing_ru_marktpartner_id,
                pru.performing_ru_marktpartner_id_source,
                pru.holder_market_partner_id,
                pru.holder_market_partner_id_source,

                m.default_vens as user_vens,

                coalesce(pru.exempt_vens, false) as exempt_vens,
                coalesce(pru.exempt_tens, false) as exempt_tens,
                case
                    when pru.exc_source_value_normalized is not null
                        then true
                    else false
                end as vens_tens_exception_flag,
                pru.vens_tens_exception_comment,

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
                     and pru.performing_ru_marktpartner_id is not null
                     and coalesce(nullif(m.tfze_or_tens, ''), e.loco_no) is not null
                        then 'HIGH'

                    when m.default_vens is not null
                      or pru.performing_ru_marktpartner_id is not null
                      or coalesce(nullif(m.tfze_or_tens, ''), e.loco_no) is not null
                        then 'MEDIUM'

                    else 'LOW'
                end as confidence,

                case
                    when m.loco_no is null
                        then 'Keine passende Mapping-Zeile für Lok gefunden.'

                    when e.performing_ru is null or e.performing_ru = ''
                        then 'PerformingRU fehlt. Manuelle Prüfung erforderlich.'

                    when pru.performing_ru_marktpartner_id_source = 'MAPPING_IMPORT'
                        then 'PerformingRU-MP-ID über market_partner_mapping_import.csv rollenbezogen und offiziell validiert aufgelöst.'

                    when pru.performing_ru_marktpartner_id_source = 'OFFICIAL_NAME_EXACT'
                        then 'PerformingRU-MP-ID über exakten offiziellen Firmennamen und ANU_VENS-Rollenliste aufgelöst.'

                    else 'PerformingRU-MP-ID nicht eindeutig auflösbar. Mappingtabelle oder offiziellen Firmennamen prüfen.'
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
            left join tmp_performing_ru_mp_lookup pru
              on pru.performing_ru is not distinct from e.performing_ru
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
                ) as next_origin_country_iso,

                lead(de_event_label) over (
                    partition by loco_no
                    order by sequence_ts asc nulls last, source_row_id asc
                ) as next_de_event_label
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

                performing_ru_marktpartner_id,
                performing_ru_marktpartner_id_source,
                holder_market_partner_id,
                holder_market_partner_id_source,
                user_vens,
                exempt_vens,
                exempt_tens,
                vens_tens_exception_flag,
                vens_tens_exception_comment,

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
                false as gap_relevant_de,

                confidence,
                decision_reason,

                case
                    -- Nur DE-relevante Bewegungen dürfen Prüffälle erzeugen.
                    -- Auslandszeilen bleiben für die durchgehende Lok-Zeitachse
                    -- sichtbar, werden aber nicht als Fehler markiert.
                    when report_scope <> 'IN_REPORT'
                        then false

                    when sequence_ts is null
                      or period_start_utc is null
                      or period_end_utc is null
                      or period_start_utc > period_end_utc
                      or loco_no is null
                      or loco_no = ''
                        then true

                    when performing_ru is null or performing_ru = ''
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
                     and performing_ru_marktpartner_id is not null
                     and performing_ru_marktpartner_id <> ''
                        then true
                    else false
                end as export_ready,

                case
                    -- Auslandszeilen zuerst abfangen. Dadurch entstehen
                    -- außerhalb DE keine Errors oder Manual Reviews.
                    when report_scope = 'NOT_IN_REPORT'
                        then 'INFO'

                    when sequence_ts is null
                      or period_start_utc is null
                      or period_end_utc is null
                      or period_start_utc > period_end_utc
                      or loco_no is null
                      or loco_no = ''
                        then 'ERROR'

                    when performing_ru is null or performing_ru = ''
                        then 'MANUAL_REVIEW'

                    else ''
                end as dq_severity,

                case
                    -- Auslandszeilen bleiben sichtbar, werden aber nicht
                    -- als fachliche Prüffälle behandelt.
                    when report_scope = 'NOT_IN_REPORT'
                        then 'Außerhalb DE; Not in the Report.'

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

                    when performing_ru is null or performing_ru = ''
                        then 'DE-relevanter Abschnitt ohne PerformingRU; manuelle Prüfung erforderlich.'

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
                -- NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6B_V1_20260608
                -- Harte GAP-Dauern nur aus belastbaren fachlichen Grenzen bilden.
                -- Fehlende Zeitwerte bleiben ueber R002/R003 sichtbar, erzeugen
                -- aber keine kuenstlich aufgeblasene GAP-Dauer mehr.
                period_end_utc as gap_from,
                next_period_start_utc as gap_to
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
        end as gap_duration_text,

        case
            when upper(coalesce(de_event_label, '')) = 'IN DE'
             and upper(coalesce(next_de_event_label, '')) = 'IN DE'
                then true

            when upper(coalesce(de_event_label, '')) = 'EINFAHRT'
             and upper(coalesce(next_de_event_label, '')) = 'AUSFAHRT'
                then true

            when upper(coalesce(de_event_label, '')) = 'EINFAHRT'
             and upper(coalesce(next_de_event_label, '')) = 'IN DE'
                then true

            when upper(coalesce(de_event_label, '')) = 'IN DE'
             and upper(coalesce(next_de_event_label, '')) = 'AUSFAHRT'
                then true

            else false
        end as gap_relevant_de
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

                performing_ru_marktpartner_id,
                performing_ru_marktpartner_id_source,
                holder_market_partner_id,
                holder_market_partner_id_source,
                user_vens,

                false as exempt_vens,
                false as exempt_tens,
                false as vens_tens_exception_flag,
                null::varchar as vens_tens_exception_comment,

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
                gap_relevant_de,

                null as confidence,
                'Künstliche GAP-Zeile wegen gebrochener Ortskette zwischen vorheriger Destination und nächstem Origin.' as decision_reason,

                case
                    when gap_relevant_de = true
                     and coalesce(gap_minutes, 0) > 480
                        then true
                    else false
                end as needs_manual_review,

                false as export_ready,

                case
                    when gap_relevant_de = true
                     and coalesce(gap_minutes, 0) > 480
                        then 'ERROR'
                    when gap_relevant_de = true
                        then 'INFO'
                    else ''
                end as dq_severity,

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


def build_core(con, run_id):
    """
    Finale Lok-Zeitachse bilden.

    Zusätzlich zu den Bewegungszeilen werden künstliche GAP-Zeilen erzeugt,
    wenn die Ortskette unterbrochen ist und die Lücke größer als
    GAP_THRESHOLD_MINUTES ist.

    GAP-Zeilen bleiben intern für Audit und Exportsegmentierung erhalten.
    Als DE-relevant gelten sie aber nur bei einer fachlich zulässigen
    Kombination der angrenzenden DE-Ereignisse. Nur solche GAPs dürfen in
    Fehlerqueue und farblicher Lok-Detailprüfung erscheinen.
    """
    _build_performing_ru_mp_lookup(con)
    _build_core_timeline_sql(con, run_id)


def build_exports(con):
    """
    Rückwärtskompatibler Wrapper.

    Die zentrale Exportlogik liegt ausschließlich in export_module.py, damit
    CSV- und XLSX-Ausgaben dieselben Fallbacks und Felddefinitionen verwenden.
    NETZENTGELT_HARDENING_V1_20260607
    """
    build_export_tables(con)

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
        import os as _os
        _thread_count = max(1, min(_os.cpu_count() or 1, 8))
        con.execute(f"set threads to {_thread_count}")
        print(f"DuckDB Runtime: threads={_thread_count}")

        # 1. Rohdaten frisch importieren.
        run_id, imported = import_csvs(con)
        build_cancelled_transport_exclusions(con)
        build_dummy_locomotive_catalog(con)

        # 2. Fachliche Mappings und offizielle Marktpartner-Referenzdaten einlesen.
        import_mapping(con)
        import_market_partner_reference(con)
        import_market_partner_mapping(con)
        import_vens_tens_exception(con)

        # Phase 5A: bestätigte manuelle Korrekturen auf die temporär importierten
        # Rohdaten anwenden. Original-CSVs bleiben unverändert.
        import_manual_overrides(con)
        apply_raw_manual_overrides(con, run_id)

        # 3. Bewegungsdaten und Transport-Routen neu berechnen.
        # Die Reihenfolge ist relevant:
        # build_core() benötigt core_transport_route bereits für seinen Join.
        build_loco_events(con)
        exclude_dummy_locomotives_from_staging(con)
        apply_staging_manual_overrides(con, run_id)
        build_transport_routes(con)
        build_core(con, run_id)
        apply_core_assignment_fallbacks(con, run_id)
        prepare_timeline_context_phase6c(con, run_id)
        build_unresolved_performing_ru_market_partner_alias(con)

        # 4. Findings und fachliche Exporttabellen neu berechnen.
        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)
        consolidate_dummy_locomotive_findings(con, run_id)
        harden_findings_and_export_policy(con, run_id)
        harden_findings_and_segments_phase6c(con, run_id)
        build_quality_gate_tables(con, run_id)
        # NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6D_V1_20260608
        # GAP-only-Lok-Tage als R016-Faelle dokumentieren, dann inkrementell
        # ins Gate eintragen statt das Gate komplett neu aufzubauen.
        insert_gap_only_day_findings_phase6d(con, run_id)
        apply_r016_to_quality_gate_tables(con)
        finalize_quality_gate_phase6d(con, run_id)
        build_exports(con)
        refresh_reconciliation_table(con, run_id)
        # NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607: 15-Minuten-Deckung, Export-Gate und Reconciliation

        # 5. Sämtliche CSV-Ausgaben neu schreiben.
        # Bestehende Dateien gleichen Namens werden dabei überschrieben.
        for table, name in [
            ("raw_import_run", "raw_import_run.csv"),
            ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),
            ("cfg_dummy_locomotives_effective", "cfg_dummy_locomotives_effective.csv"),
            ("audit_excluded_dummy_locomotives", "audit_excluded_dummy_locomotives.csv"),
            ("audit_excluded_dummy_locomotive_staging", "audit_excluded_dummy_locomotive_staging.csv"),
            ("cfg_manual_overrides", "cfg_manual_overrides.csv"),
            ("cfg_manual_overrides_effective", "cfg_manual_overrides_effective.csv"),
            ("dq_manual_override_conflicts", "dq_manual_override_conflicts.csv"),
            ("audit_manual_override_application", "audit_manual_override_application.csv"),
            ("dq_rule_engine_hardening_audit", "dq_rule_engine_hardening_audit.csv"),
            ("dq_rule_engine_hardening_blockers", "dq_rule_engine_hardening_blockers.csv"),
            ("dq_rule_engine_hardening_phase6c_audit", "dq_rule_engine_hardening_phase6c_audit.csv"),
            ("dq_rule_engine_hardening_phase6d_audit", "dq_rule_engine_hardening_phase6d_audit.csv"),
            ("dq_phase6d_exact_overlap_days", "dq_phase6d_exact_overlap_days.csv"),
            ("dq_phase6c_uncertain_gaps", "dq_phase6c_uncertain_gaps.csv"),
            ("dq_phase6c_gap_context_review", "dq_phase6c_gap_context_review.csv"),
            ("core_loco_stand_candidates", "core_loco_stand_candidates.csv"),
            ("core_usage_assignment_segment_movements", "core_usage_assignment_segment_movements.csv"),
            ("core_usage_assignment_segments", "core_usage_assignment_segments.csv"),
            ("stg_loco_events", "stg_loco_events.csv"),
            ("core_loco_timeline", "core_loco_timeline.csv"),
            ("dq_findings", "dq_findings.csv"),
            ("dq_run_metadata", "dq_run_metadata.csv"),
            ("core_loco_day_coverage", "core_loco_day_coverage.csv"),
            ("dq_export_gate", "dq_export_gate.csv"),
            ("dq_export_gate_ru", "dq_export_gate_ru.csv"),
            ("dq_global_export_blockers", "dq_global_export_blockers.csv"),
            ("export_excluded_rows", "export_excluded_rows.csv"),
            ("dq_reconciliation", "dq_reconciliation.csv"),
            ("dq_operational_kpis", "dq_operational_kpis.csv"),
            ("cfg_dq_rule_catalog", "cfg_dq_rule_catalog.csv"),
            ("cfg_market_partner_role", "cfg_market_partner_role.csv"),
            ("cfg_market_partner_role_conflicts", "cfg_market_partner_role_conflicts.csv"),
            ("cfg_market_partner_mapping", "cfg_market_partner_mapping.csv"),
            ("cfg_market_partner_mapping_effective", "cfg_market_partner_mapping_effective.csv"),
            ("cfg_market_partner_mapping_conflicts", "cfg_market_partner_mapping_conflicts.csv"),
            ("cfg_market_partner_mapping_invalid", "cfg_market_partner_mapping_invalid.csv"),
            ("cfg_vens_tens_exception", "cfg_vens_tens_exception.csv"),
            ("cfg_vens_tens_exception_effective", "cfg_vens_tens_exception_effective.csv"),
            ("cfg_vens_tens_exception_conflicts", "cfg_vens_tens_exception_conflicts.csv"),
            ("dq_unresolved_performing_ru_market_partner_alias", "dq_unresolved_performing_ru_market_partner_alias.csv"),
            ("export_zuordnungen", "export_zuordnungen.csv"),
            ("export_nutzungsmeldung", "export_nutzungsmeldung.csv"),
            ("stg_loco_events_skipped", "stg_loco_events_skipped.csv"),
            ("stg_transport_details_enriched", "stg_transport_details_enriched.csv"),
            ("core_transport_route", "core_transport_route.csv"),
        ]:
            export_table(con, table, name)

        # 6. Kennzahlen des erfolgreich berechneten Laufs ermitteln.
        quality_gate_summary = con.execute("""
            select
                count(*) filter (where gate_status = 'READY') as ready_days,
                count(*) filter (where gate_status = 'WARNING') as warning_days,
                count(*) filter (where gate_status = 'BLOCKED') as blocked_days
            from dq_export_gate
        """).fetchone()

        print(
            "Quality Gate Lok-Tage: "
            f"READY={quality_gate_summary[0]} | "
            f"WARNING={quality_gate_summary[1]} | "
            f"BLOCKED={quality_gate_summary[2]}"
        )

        # NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607

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
