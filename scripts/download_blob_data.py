import os
import shutil
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# ======================================================
# Azure Blob Download für Netzentgelt MVP
# ======================================================
#
# ZIEL:
# - LocomotiveMovement.csv: nur die letzten 30 Tage der verfügbaren Daten
# - TransportDetail.csv:    nur die letzten 30 Tage der verfügbaren Daten
# - Locomotive.csv:         vollständig laden, da Stammdaten
# - LocomotiveUsage.csv:    nicht mehr laden und lokal entfernen
#
# WICHTIG:
# "Letzte 30 Tage der verfügbaren Daten" bedeutet:
# Der Filter orientiert sich am aktuellsten ActualDeparture-Wert
# innerhalb der jeweiligen CSV-Datei.
#
# Beispiel:
# - Neuester Datensatz in der Datei: 31.05.2026
# - Geladen wird: 01.05.2026 bis 31.05.2026
#
# Dadurch entstehen keine leeren CSV-Dateien, nur weil die Quelldaten
# zeitlich hinter dem heutigen Datum liegen.
#
# TECHNISCH:
# Die vollständige Blob-Datei wird zunächst nur temporär heruntergeladen.
# Danach reduziert DuckDB die Datei lokal auf das gewünschte Zeitfenster.
# Im Ordner data/00_raw verbleibt ausschließlich die reduzierte CSV-Datei.
#
# Das ist für das MVP bewusst robuster als ein serverseitiger Azure-SQL-
# Filter. Sobald die fachliche Logik stabil ist, kann später optimiert werden.
# ======================================================

load_dotenv()

# ------------------------------------------------------
# Azure-Zugangsdaten aus der lokalen .env-Datei lesen
# ------------------------------------------------------
ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
ACCOUNT_KEY = os.getenv("AZURE_STORAGE_ACCOUNT_KEY")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME")

if not all([ACCOUNT_NAME, ACCOUNT_KEY, CONTAINER_NAME]):
    raise RuntimeError(
        "Azure-Storage-Konfiguration fehlt. "
        "Bitte die lokale .env-Datei prüfen. Erwartet werden:\n"
        "- AZURE_STORAGE_ACCOUNT_NAME\n"
        "- AZURE_STORAGE_ACCOUNT_KEY\n"
        "- AZURE_STORAGE_CONTAINER_NAME"
    )

# ------------------------------------------------------
# Projektpfade
# ------------------------------------------------------
# Das Skript liegt unter scripts/.
# parents[1] verweist daher auf den Projektstamm.
ROOT = Path(__file__).resolve().parents[1]

# Hier liegen nach dem Lauf die für die Pipeline verwendeten CSV-Dateien.
DOWNLOAD_DIR = ROOT / "data" / "00_raw"

# Temporärer Unterordner für vollständige Downloads.
# Dieser Ordner wird nach dem Lauf automatisch wieder entfernt.
TEMP_DIR = DOWNLOAD_DIR / "_tmp_blob_download"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------
# Fachliche Konfiguration
# ------------------------------------------------------
ROLLING_DAYS = 30

# Nur diese drei Dateien werden benötigt.
#
# filter_days = None:
# Die Datei wird vollständig geladen.
#
# filter_days = 30:
# Es werden nur die letzten 30 Tage der verfügbaren Daten behalten.
#
# timestamp_candidates:
# Das Skript verwendet die erste tatsächlich vorhandene Zeitspalte.
FILE_RULES = {
    "locomotivemovement.csv": {
        "filter_days": ROLLING_DAYS,
        "timestamp_candidates": [
            "ActualDeparture",
            "LocomotiveActualDeparture",
        ],
    },
    "transportdetail.csv": {
        "filter_days": ROLLING_DAYS,
        "timestamp_candidates": [
            "ActualDeparture",
        ],
    },
    "locomotive.csv": {
        "filter_days": None,
        "timestamp_candidates": [],
    },
}

# Diese Datei wird nicht mehr verwendet.
# Falls sie noch lokal aus einem alten Lauf vorhanden ist, wird sie entfernt.
FILES_TO_REMOVE_LOCALLY = {
    "locomotiveusage.csv",
}


# ======================================================
# Hilfsfunktionen
# ======================================================

def qident(name: str) -> str:
    """
    SQL-Spaltenname sicher in doppelte Anführungszeichen setzen.

    Beispiel:
    ActualDeparture -> "ActualDeparture"
    """
    return '"' + name.replace('"', '""') + '"'


def qlit(value: str) -> str:
    """
    SQL-Textwert sicher in einfache Anführungszeichen setzen.

    Beispiel:
    C:\\data\\file.csv -> 'C:\\data\\file.csv'
    """
    return "'" + str(value).replace("'", "''") + "'"


def timestamp_expression(column_name: str) -> str:
    """
    Erzeugt einen robusten DuckDB-Ausdruck zum Lesen von Datumswerten.

    Das Skript versucht zuerst einen normalen CAST.
    Falls das nicht funktioniert, werden typische Formate zusätzlich geprüft.

    Dadurch funktioniert der Filter auch dann, wenn die CSV-Daten nicht
    überall exakt gleich formatiert sind.
    """
    col = qident(column_name)

    return f"""
        coalesce(
            try_cast({col} as timestamp),
            try_strptime({col}, '%d.%m.%Y %H:%M:%S'),
            try_strptime({col}, '%d.%m.%Y %H:%M'),
            try_strptime({col}, '%Y-%m-%d %H:%M:%S'),
            try_strptime({col}, '%Y-%m-%dT%H:%M:%S'),
            try_strptime({col}, '%Y-%m-%dT%H:%M:%SZ')
        )
    """


def download_blob_to_file(blob_client, target_path: Path) -> None:
    """
    Lädt eine Azure-Blob-Datei vollständig auf die lokale Festplatte.

    Die Datei wird immer zunächst temporär abgelegt.
    Erst nach erfolgreicher Verarbeitung wird die produktive lokale CSV ersetzt.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as file:
        stream = blob_client.download_blob(max_concurrency=4)
        stream.readinto(file)


def replace_file_safely(source_path: Path, target_path: Path) -> None:
    """
    Ersetzt eine bestehende lokale Datei erst dann, wenn die neue Datei
    vollständig erstellt wurde.

    Dadurch bleibt bei einem Fehler die bisherige Datei erhalten.
    """
    if not source_path.exists():
        raise RuntimeError(f"Temporäre Quelldatei fehlt: {source_path}")

    if target_path.exists():
        target_path.unlink()

    source_path.replace(target_path)


def remove_obsolete_local_files() -> None:
    """
    Entfernt lokal verbliebene Dateien, die in der aktuellen MVP-Logik
    nicht mehr verwendet werden.

    Aktuell betrifft das LocomotiveUsage.csv.
    """
    for file_name in FILES_TO_REMOVE_LOCALLY:
        local_path = DOWNLOAD_DIR / file_name

        if local_path.exists():
            local_path.unlink()
            print(f"Entfernt: {local_path.name} wird nicht mehr benötigt.")


def find_matching_blobs(container_client) -> dict[str, str]:
    """
    Ermittelt die benötigten Blob-Dateien im Azure-Container.

    Rückgabewert:
    {
        "locomotivemovement.csv": "möglicher/unterordner/LocomotiveMovement.csv",
        ...
    }

    Falls dieselbe Datei in mehreren Blob-Unterordnern vorkommt,
    wird bewusst ein Fehler ausgelöst. So wird keine Datei zufällig gewählt.
    """
    matches: dict[str, list[str]] = {
        expected_file: []
        for expected_file in FILE_RULES
    }

    for blob in container_client.list_blobs():
        file_name = Path(blob.name).name.lower()

        if file_name in matches:
            matches[file_name].append(blob.name)

    resolved: dict[str, str] = {}

    for expected_file, blob_names in matches.items():
        if not blob_names:
            raise RuntimeError(
                f"Erwartete Datei nicht im Azure-Container gefunden: {expected_file}"
            )

        if len(blob_names) > 1:
            raise RuntimeError(
                f"Datei mehrfach im Azure-Container gefunden: {expected_file}\n"
                + "\n".join(f"- {name}" for name in blob_names)
            )

        resolved[expected_file] = blob_names[0]

    return resolved


def get_csv_columns(connection, csv_path: Path) -> list[str]:
    """
    Liest die Spaltennamen einer CSV-Datei über DuckDB aus.

    Die CSV wird nur beschrieben, noch nicht in die Datenbank importiert.
    """
    relation = f"""
        read_csv_auto(
            {qlit(str(csv_path))},
            header=true,
            all_varchar=true,
            ignore_errors=true
        )
    """

    rows = connection.execute(
        f"describe select * from {relation}"
    ).fetchall()

    return [row[0] for row in rows]


def pick_existing_column(
    available_columns: list[str],
    candidates: list[str],
) -> str:
    """
    Wählt die erste vorhandene Zeitspalte aus der Kandidatenliste aus.

    Der Vergleich erfolgt ohne Beachtung von Groß-/Kleinschreibung.
    """
    by_lower = {
        column.lower(): column
        for column in available_columns
    }

    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]

    raise RuntimeError(
        "Keine geeignete Zeitspalte gefunden.\n"
        f"Erwartete Kandidaten: {candidates}\n"
        f"Vorhandene Spalten: {available_columns}"
    )


def filter_last_available_days(
    source_path: Path,
    target_path: Path,
    timestamp_candidates: list[str],
    days: int,
) -> tuple[str, str, str, int]:
    """
    Reduziert eine vollständige temporäre CSV-Datei lokal mit DuckDB.

    Filterregel:
    - Ermittle den aktuellsten gültigen Zeitwert in der Datei.
    - Behalte alle Datensätze ab max_timestamp - days.
    - Schreibe das Ergebnis in eine neue CSV-Datei.

    Rückgabe:
    (
        verwendete Zeitspalte,
        aktuellster Zeitwert als Text,
        Cutoff-Zeitwert als Text,
        Anzahl exportierter Zeilen
    )
    """
    connection = duckdb.connect()

    try:
        source_relation = f"""
            read_csv_auto(
                {qlit(str(source_path))},
                header=true,
                all_varchar=true,
                ignore_errors=true
            )
        """

        available_columns = get_csv_columns(connection, source_path)

        timestamp_column = pick_existing_column(
            available_columns=available_columns,
            candidates=timestamp_candidates,
        )

        ts_expr = timestamp_expression(timestamp_column)

        max_timestamp = connection.execute(f"""
            select max({ts_expr})
            from {source_relation}
        """).fetchone()[0]

        if max_timestamp is None:
            raise RuntimeError(
                f"Keine gültigen Zeitwerte in Spalte {timestamp_column} gefunden. "
                "Die reduzierte CSV-Datei wurde nicht erzeugt."
            )

        cutoff_timestamp = connection.execute(
            f"select ?::timestamp - interval '{days} days'",
            [max_timestamp],
        ).fetchone()[0]

        filtered_count = connection.execute(f"""
            select count(*)
            from {source_relation}
            where {ts_expr} >= ?::timestamp
        """, [cutoff_timestamp]).fetchone()[0]

        if filtered_count == 0:
            raise RuntimeError(
                f"Der 30-Tage-Filter für {source_path.name} ergab 0 Zeilen. "
                "Die bisherige lokale Datei bleibt unverändert erhalten."
            )

        # COPY schreibt die reduzierte CSV inklusive Header.
        connection.execute(f"""
            copy (
                select *
                from {source_relation}
                where {ts_expr} >= ?::timestamp
            )
            to {qlit(str(target_path))}
            (
                header true,
                delimiter ';'
            )
        """, [cutoff_timestamp])

        return (
            timestamp_column,
            str(max_timestamp),
            str(cutoff_timestamp),
            int(filtered_count),
        )

    finally:
        connection.close()


# ======================================================
# Hauptlogik
# ======================================================

def main() -> None:
    """
    Führt den vollständigen Blob-Download aus.

    Ablauf:
    1. Veraltete lokale LocomotiveUsage.csv entfernen.
    2. Erwartete Blob-Dateien im Azure-Container suchen.
    3. Locomotive.csv vollständig laden.
    4. LocomotiveMovement.csv temporär vollständig laden und lokal filtern.
    5. TransportDetail.csv temporär vollständig laden und lokal filtern.
    6. Temporäre Dateien löschen.
    7. Übersicht im Terminal ausgeben.
    """

    print("")
    print("=" * 80)
    print("Netzentgelt MVP - Azure Blob Download")
    print("=" * 80)
    print(f"Storage Account: {ACCOUNT_NAME}")
    print(f"Container:       {CONTAINER_NAME}")
    print(f"Lokales Ziel:    {DOWNLOAD_DIR.resolve()}")
    print(f"Zeitfenster:     letzte {ROLLING_DAYS} Tage der verfügbaren Daten")
    print("=" * 80)

    remove_obsolete_local_files()

    account_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net"

    blob_service_client = BlobServiceClient(
        account_url=account_url,
        credential=ACCOUNT_KEY,
    )

    container_client = blob_service_client.get_container_client(CONTAINER_NAME)

    resolved_blobs = find_matching_blobs(container_client)

    summary_rows = []

    try:
        for expected_file, blob_name in resolved_blobs.items():
            rule = FILE_RULES[expected_file]

            local_target = DOWNLOAD_DIR / Path(blob_name).name
            temp_full_download = TEMP_DIR / f"{expected_file}.full.tmp"
            temp_filtered_output = TEMP_DIR / f"{expected_file}.filtered.tmp"

            print("")
            print("-" * 80)
            print(f"Datei: {blob_name}")
            print(f"Ziel:  {local_target}")

            blob_client = container_client.get_blob_client(blob_name)

            # Alte temporäre Dateien sicherheitshalber entfernen.
            for temp_path in [temp_full_download, temp_filtered_output]:
                if temp_path.exists():
                    temp_path.unlink()

            filter_days = rule["filter_days"]

            if filter_days is None:
                # Stammdaten werden vollständig geladen.
                print("Modus: vollständiger Download ohne Zeitfilter")

                download_blob_to_file(
                    blob_client=blob_client,
                    target_path=temp_full_download,
                )

                replace_file_safely(
                    source_path=temp_full_download,
                    target_path=local_target,
                )

                summary_rows.append(
                    (
                        local_target.name,
                        "vollständig",
                        "-",
                        "-",
                        "-",
                        "OK",
                    )
                )

                print("Status: erfolgreich vollständig geladen")
                continue

            # Bewegungsdaten:
            # vollständige Blob-Datei nur temporär laden.
            print("Modus: temporärer Voll-Download, danach lokaler 30-Tage-Filter")

            download_blob_to_file(
                blob_client=blob_client,
                target_path=temp_full_download,
            )

            (
                timestamp_column,
                max_timestamp,
                cutoff_timestamp,
                filtered_count,
            ) = filter_last_available_days(
                source_path=temp_full_download,
                target_path=temp_filtered_output,
                timestamp_candidates=rule["timestamp_candidates"],
                days=filter_days,
            )

            replace_file_safely(
                source_path=temp_filtered_output,
                target_path=local_target,
            )

            summary_rows.append(
                (
                    local_target.name,
                    f"letzte {filter_days} Tage",
                    timestamp_column,
                    max_timestamp,
                    cutoff_timestamp,
                    f"{filtered_count} Zeilen",
                )
            )

            print(f"Zeitspalte:        {timestamp_column}")
            print(f"Neuester Datensatz:{max_timestamp}")
            print(f"Cutoff:            {cutoff_timestamp}")
            print(f"Status:            erfolgreich gefiltert ({filtered_count} Zeilen)")

    finally:
        # Temporäre Dateien und Ordner immer entfernen,
        # auch wenn während des Laufs ein Fehler aufgetreten ist.
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)

    print("")
    print("=" * 80)
    print("Download abgeschlossen")
    print("=" * 80)

    for (
        file_name,
        mode,
        timestamp_column,
        max_timestamp,
        cutoff_timestamp,
        status,
    ) in summary_rows:
        print(f"Datei:          {file_name}")
        print(f"Modus:          {mode}")
        print(f"Zeitspalte:     {timestamp_column}")
        print(f"Neuester Wert:  {max_timestamp}")
        print(f"Cutoff:         {cutoff_timestamp}")
        print(f"Ergebnis:       {status}")
        print("-" * 80)

    print("Fertig.")


if __name__ == "__main__":
    main()
