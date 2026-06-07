import csv
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from azure.storage.blob import (
    BlobQueryError,
    BlobServiceClient,
    DelimitedTextDialect,
)

# ======================================================
# Azure Blob Download für Netzentgelt MVP
# ======================================================
#
# ZIEL:
# - LocomotiveMovement.csv: serverseitig nur die letzten 30 Kalendertage laden
# - TransportDetail.csv:    serverseitig nur die letzten 30 Kalendertage laden
# - Locomotive.csv:         vollständig laden, da Stammdaten
# - LocomotiveUsage.csv:    nicht mehr laden und lokal entfernen
#
# WICHTIG:
# Die Bewegungsdateien werden NICHT mehr vollständig heruntergeladen.
# Azure Blob Storage filtert die CSV-Dateien serverseitig über query_blob().
# Lokal werden nur die Treffer ab dem UTC-Cutoff gespeichert.
#
# Beispiel bei Ausführung am 03.06.2026:
# - Cutoff: 04.05.2026 UTC
# - Geladen werden nur CSV-Zeilen mit ActualDeparture >= Cutoff.
#
# Voraussetzung:
# - Standard General-Purpose-v2 Storage Account
# - Block Blob
# - CSV-Datei mit Headerzeile
# - Query Blob Contents / Query Acceleration wird vom Storage Account unterstützt
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
ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = ROOT / "data" / "00_raw"
TEMP_ROOT_DIR = DOWNLOAD_DIR / "_tmp_blob_download"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_ROOT_DIR.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------
# Fachliche Konfiguration
# ------------------------------------------------------
ROLLING_DAYS = 30

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

FILES_TO_REMOVE_LOCALLY = {
    "locomotiveusage.csv",
}

# Lokale CSV-Dateien werden einheitlich mit Semikolon gespeichert.
LOCAL_OUTPUT_DELIMITER = ";"


# ======================================================
# Hilfsfunktionen
# ======================================================

def sql_identifier(name: str) -> str:
    """SQL-Identifier für Query Blob Contents sicher quoten."""
    return '"' + name.replace('"', '""') + '"'


def sql_literal(value: str) -> str:
    """SQL-Textwert für Query Blob Contents sicher quoten."""
    return "'" + str(value).replace("'", "''") + "'"


def download_blob_to_file(blob_client, target_path: Path) -> None:
    """
    Lädt einen Blob vollständig herunter.

    Diese Funktion wird nur noch für kleine Stammdaten wie Locomotive.csv
    verwendet. Große Bewegungsdateien werden serverseitig gefiltert.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as file:
        stream = blob_client.download_blob(max_concurrency=4)
        stream.readinto(file)


def replace_file_safely(source_path: Path, target_path: Path) -> None:
    """
    Ersetzt eine bestehende lokale Datei atomar, soweit dies durch das
    Dateisystem unterstützt wird.

    Die bestehende lokale CSV wird nicht vorab gelöscht. Dadurch bleibt sie
    erhalten, falls das Ersetzen fehlschlägt.
    """
    if not source_path.exists():
        raise RuntimeError(f"Temporäre Quelldatei fehlt: {source_path}")

    try:
        os.replace(source_path, target_path)

    except PermissionError as error:
        raise RuntimeError(
            "Lokale Zieldatei ist gesperrt und konnte nicht ersetzt werden: "
            f"{target_path}\n"
            "Bitte die Datei in Excel, Power BI oder einem anderen Programm "
            "schließen und den Import erneut starten."
        ) from error


def remove_obsolete_local_files() -> None:
    """Entfernt lokal verbliebene Dateien, die nicht mehr verwendet werden."""
    for file_name in FILES_TO_REMOVE_LOCALLY:
        local_path = DOWNLOAD_DIR / file_name

        if local_path.exists():
            local_path.unlink()
            print(f"Entfernt: {local_path.name} wird nicht mehr benötigt.")


def find_matching_blobs(container_client) -> dict[str, str]:
    """
    Ermittelt die benötigten Blob-Dateien im Azure-Container.

    Falls dieselbe erwartete Datei mehrfach vorkommt, wird bewusst ein
    Fehler ausgelöst, damit keine Datei zufällig ausgewählt wird.
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


def detect_csv_settings(blob_client) -> tuple[str, str, list[str]]:
    """
    Lädt nur einen kleinen Anfangsbereich des Blobs, erkennt das CSV-Trennzeichen
    und liest die Headerzeile aus.

    Dadurch muss für die serverseitige Filterung nicht die ganze Datei geladen
    werden.
    """
    sample_bytes = blob_client.download_blob(
        offset=0,
        length=64 * 1024,
    ).readall()

    sample_text = sample_bytes.decode("utf-8-sig", errors="replace")

    if not sample_text.strip():
        raise RuntimeError("CSV-Blob ist leer.")

    first_line = sample_text.splitlines()[0]

    try:
        dialect = csv.Sniffer().sniff(
            first_line,
            delimiters=",;\t|",
        )
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    # Azure Query Blob Contents akzeptiert für RecordSeparator nur
    # genau ein Zeichen. Auch bei Windows-CSV-Dateien mit CRLF wird daher
    # ausschließlich "\n" übergeben. Ein "\r\n"-String würde vom Service
    # mit InvalidXmlDocument / RecordSeparator has more than 1 character
    # abgelehnt werden.
    line_terminator = "\n"

    header = next(
        csv.reader(
            [first_line],
            delimiter=delimiter,
        )
    )

    columns = [
        column.strip().lstrip("\ufeff")
        for column in header
    ]

    return delimiter, line_terminator, columns


def pick_existing_column(
    available_columns: list[str],
    candidates: list[str],
) -> str:
    """Wählt die erste tatsächlich vorhandene Zeitspalte aus."""
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


def parse_iso_timestamp(value: str):
    """ISO-Zeitwert robust für die lokale Kontrollausgabe interpretieren."""
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except ValueError:
        return None


def inspect_filtered_csv(
    csv_path: Path,
    timestamp_column: str,
) -> tuple[int, str]:
    """
    Prüft die lokal gespeicherte Teilmenge und liefert:
    - Anzahl Datenzeilen
    - neuesten enthaltenen Zeitwert
    """
    row_count = 0
    max_timestamp = None

    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(
            file,
            delimiter=LOCAL_OUTPUT_DELIMITER,
        )

        if not reader.fieldnames:
            raise RuntimeError(
                f"Die gefilterte Datei enthält keine Headerzeile: {csv_path.name}"
            )

        for row in reader:
            row_count += 1

            parsed = parse_iso_timestamp(
                row.get(timestamp_column, "")
            )

            if parsed is not None:
                if max_timestamp is None or parsed > max_timestamp:
                    max_timestamp = parsed

    if row_count == 0:
        raise RuntimeError(
            f"Der serverseitige {ROLLING_DAYS}-Tage-Filter ergab 0 Zeilen. "
            "Die bisherige lokale Datei bleibt unverändert erhalten."
        )

    max_timestamp_text = (
        max_timestamp.isoformat()
        if max_timestamp is not None
        else "Kein gültiger Zeitwert in der gefilterten Teilmenge"
    )

    return row_count, max_timestamp_text


def query_last_days_to_file(
    blob_client,
    target_path: Path,
    timestamp_candidates: list[str],
    days: int,
) -> tuple[str, str, str, int]:
    """
    Fragt eine große CSV-Datei direkt auf Azure serverseitig ab.

    Ablauf:
    1. Nur Headerbereich laden und CSV-Format erkennen.
    2. UTC-Cutoff = aktueller Zeitpunkt minus n Tage bestimmen.
    3. query_blob() mit SQL-Filter ausführen.
    4. Nur die gefilterten Treffer lokal speichern.
    5. Ergebnis lokal kurz validieren.
    """
    (
        source_delimiter,
        source_line_terminator,
        available_columns,
    ) = detect_csv_settings(blob_client)

    timestamp_column = pick_existing_column(
        available_columns=available_columns,
        candidates=timestamp_candidates,
    )

    cutoff_timestamp = (
        datetime.now(timezone.utc)
        - timedelta(days=days)
    )

    # Die DataLake-Zeitwerte liegen in einem lexikographisch sortierbaren
    # ISO-8601-Format vor, z. B.:
    # 2026-05-06T22:00:00.0000000
    #
    # Azure Query Blob Contents liest CSV-Felder zunächst als STRING.
    # Eine direkte TO_TIMESTAMP()-Konvertierung wäre fehleranfällig:
    # Bereits ein leerer Einzelwert führt serverseitig zu einem fatalen
    # "String can't be converted to TimeStamp"-Fehler.
    #
    # Deshalb erfolgt der 30-Tage-Filter bewusst als STRING-Vergleich.
    # Für einheitliche ISO-8601-Werte ist die alphabetische Reihenfolge
    # gleichzeitig die chronologische Reihenfolge.
    cutoff_iso = cutoff_timestamp.strftime(
        "%Y-%m-%dT%H:%M:%S"
    )

    timestamp_identifier = sql_identifier(timestamp_column)

    query = f"""
        SELECT *
        FROM BlobStorage
        WHERE CHAR_LENGTH(TRIM({timestamp_identifier})) > 0
          AND TRIM({timestamp_identifier}) >= {sql_literal(cutoff_iso)}
    """

    query_errors: list[str] = []

    def report_error(error: BlobQueryError) -> None:
        """
        Protokolliert Fehler, die Azure während der serverseitigen Blob-Abfrage
        innerhalb des Datenstroms meldet.

        Das Azure-SDK verwendet bei BlobQueryError das Attribut "error" und
        nicht "name". getattr() macht den Callback zusätzlich robust gegenüber
        kleineren Versionsunterschieden des SDK.
        """
        error_name = getattr(error, "error", None) or type(error).__name__
        description = getattr(error, "description", None) or str(error)
        position = getattr(error, "position", None)
        is_fatal = getattr(error, "is_fatal", False)

        query_errors.append(
            f"Position={position}; "
            f"Fehler={error_name}; "
            f"Fatal={is_fatal}; "
            f"Beschreibung={description}"
        )

    input_format = DelimitedTextDialect(
        delimiter=source_delimiter,
        quotechar='"',
        lineterminator=source_line_terminator,
        escapechar="\\",
        has_header=True,
    )

    output_format = DelimitedTextDialect(
        delimiter=LOCAL_OUTPUT_DELIMITER,
        quotechar='"',
        lineterminator="\n",
        escapechar="\\",
        has_header=True,
    )

    target_path.parent.mkdir(parents=True, exist_ok=True)

    reader = blob_client.query_blob(
        query_expression=query,
        blob_format=input_format,
        output_format=output_format,
        on_error=report_error,
        encoding="utf-8",
    )

    with open(target_path, "wb") as file:
        reader.readinto(file)

    if query_errors:
        raise RuntimeError(
            "Azure Query Blob Contents meldete Fehler:\n"
            + "\n".join(f"- {message}" for message in query_errors[:20])
        )

    (
        filtered_count,
        max_timestamp,
    ) = inspect_filtered_csv(
        csv_path=target_path,
        timestamp_column=timestamp_column,
    )

    return (
        timestamp_column,
        max_timestamp,
        cutoff_iso,
        filtered_count,
    )


# ======================================================
# Hauptlogik
# ======================================================

def main() -> None:
    """
    Führt den Blob-Download aus.

    Ablauf:
    1. Veraltete lokale LocomotiveUsage.csv entfernen.
    2. Erwartete Blob-Dateien im Azure-Container suchen.
    3. Locomotive.csv vollständig laden.
    4. LocomotiveMovement.csv serverseitig auf 30 Tage filtern.
    5. TransportDetail.csv serverseitig auf 30 Tage filtern.
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
    print(f"Zeitfenster:     letzte {ROLLING_DAYS} Kalendertage ab aktuellem UTC-Zeitpunkt")
    print("Filterung:       serverseitig über Azure Query Blob Contents")
    print("=" * 80)

    remove_obsolete_local_files()

    account_url = f"https://{ACCOUNT_NAME}.blob.core.windows.net"

    blob_service_client = BlobServiceClient(
        account_url=account_url,
        credential=ACCOUNT_KEY,
    )

    container_client = blob_service_client.get_container_client(
        CONTAINER_NAME
    )

    resolved_blobs = find_matching_blobs(container_client)

    summary_rows = []

    # Jeder Importlauf erhält einen eigenen temporären Unterordner.
    # Dadurch blockiert eine gesperrte Altdatei aus einem früheren,
    # abgebrochenen Lauf keinen neuen Import mehr.
    with TemporaryDirectory(
        prefix="run_",
        dir=TEMP_ROOT_DIR,
        ignore_cleanup_errors=True,
    ) as run_temp_dir_text:
        run_temp_dir = Path(run_temp_dir_text)

        try:
            for expected_file, blob_name in resolved_blobs.items():
                rule = FILE_RULES[expected_file]

                local_target = DOWNLOAD_DIR / Path(blob_name).name
                temp_full_download = run_temp_dir / f"{expected_file}.full.tmp"
                temp_filtered_output = run_temp_dir / f"{expected_file}.filtered.tmp"

                print("")
                print("-" * 80)
                print(f"Datei: {blob_name}")
                print(f"Ziel:  {local_target}")

                blob_client = container_client.get_blob_client(
                    blob_name
                )

                for temp_path in [
                    temp_full_download,
                    temp_filtered_output,
                ]:
                    if temp_path.exists():
                        temp_path.unlink()

                filter_days = rule["filter_days"]

                if filter_days is None:
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

                print(
                    "Modus: Azure filtert serverseitig; "
                    "lokal werden nur die Treffer gespeichert"
                )

                (
                    timestamp_column,
                    max_timestamp,
                    cutoff_timestamp,
                    filtered_count,
                ) = query_last_days_to_file(
                    blob_client=blob_client,
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
                        f"serverseitig letzte {filter_days} Tage",
                        timestamp_column,
                        max_timestamp,
                        cutoff_timestamp,
                        f"{filtered_count} Zeilen",
                    )
                )

                print(f"Zeitspalte:        {timestamp_column}")
                print(f"Neuester Treffer:  {max_timestamp}")
                print(f"Cutoff UTC:        {cutoff_timestamp}")
                print(f"Status:            erfolgreich gefiltert ({filtered_count} Zeilen)")

        finally:
            # Der eindeutige Laufordner wird durch TemporaryDirectory
            # best-effort bereinigt. Gesperrte Altdateien anderer Läufe
            # beeinträchtigen den aktuellen Import nicht.
            pass

    # Den gemeinsamen Temp-Wurzelordner nur entfernen, wenn er leer ist.
    # Alte gesperrte Dateien bleiben ansonsten bewusst liegen und können
    # nach dem Schließen des blockierenden Prozesses manuell gelöscht werden.
    try:
        TEMP_ROOT_DIR.rmdir()
    except OSError:
        pass

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
