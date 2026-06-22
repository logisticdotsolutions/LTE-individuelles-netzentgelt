"""
Dummy-vEns-/tEns-Mapping für den Netzentgelt-MVP erzeugen
==========================================================

Zweck
-----
Dieses Hilfsskript erzeugt bewusst nur TESTDATEN für den MVP.
Es liest die aktuell lokal vorhandene LocomotiveMovement.csv, ermittelt alle
PerformingRUs mit DE-relevanten Bewegungen und schreibt für jede PerformingRU
zwei getrennte rollenbezogene Dummy-Zuordnungen:

- ANU_VENS: Nutzer-vEns / Nutzerrolle
- ANE_TENS: Marktpartner-ID des Halters / Halterrolle

Erzeugte Dateien
----------------
data/01_mapping/vens liste.csv
data/01_mapping/market_partner_mapping_import.csv

Vorhandene Dateien werden vor dem Überschreiben automatisch mit Zeitstempel
als Backup im selben Ordner gesichert.

Start im Projektstamm
---------------------
.venv\\Scripts\\python.exe scripts\\generate_dummy_vens_tens_mapping.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "00_raw"
MAP_DIR = ROOT / "data" / "01_mapping"
DEFAULT_MOVEMENT_PATH = RAW_DIR / "LocomotiveMovement.csv"
DEFAULT_REFERENCE_PATH = MAP_DIR / "vens liste.csv"
DEFAULT_MAPPING_PATH = MAP_DIR / "market_partner_mapping_import.csv"

PERFORMING_RU_CANDIDATES = [
    "CurrentContractant",
    "CALPerformingRU",
    "PerformingRU",
    "PerformingRailwayUndertaking",
    "RailwayUndertaking",
    "Carrier",
    "ProductionCompany",
]

ORIGIN_COUNTRY_CANDIDATES = [
    "OriginCountryISO",
    "OriginCountryIso",
    "OriginCountry",
    "FromCountryISO",
    "FromCountry",
    "DepartureCountryISO",
    "DepartureCountry",
]

DESTINATION_COUNTRY_CANDIDATES = [
    "DestinationCountryISO",
    "DestinationCountryIso",
    "DestinationCountry",
    "ToCountryISO",
    "ToCountry",
    "ArrivalCountryISO",
    "ArrivalCountry",
]

COUNTRY_FALLBACK_CANDIDATES = [
    "Country",
]

MAPPING_HEADERS = [
    "source_system",
    "source_field",
    "source_value",
    "role_code",
    "official_company_name",
    "market_partner_id",
    "active_flag",
    "match_method",
    "match_score",
    "manual_review",
    "comment",
]


def detect_delimiter(path: Path) -> str:
    """CSV-Trennzeichen anhand der Headerzeile erkennen."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        first_line = handle.readline()

    if not first_line:
        raise RuntimeError(f"CSV-Datei ist leer: {path}")

    try:
        return csv.Sniffer().sniff(first_line, delimiters=",;\t|").delimiter
    except csv.Error:
        return ";"


def find_column(fieldnames: list[str], candidates: list[str]) -> str | None:
    """Erste tatsächlich vorhandene Spalte unabhängig von Großschreibung wählen."""
    by_lower = {str(name).strip().lower(): str(name).strip() for name in fieldnames}

    for candidate in candidates:
        match = by_lower.get(candidate.lower())
        if match:
            return match

    return None


def normalize_text(value: object) -> str:
    """CSV-Textwerte trimmen; None wird zu leerem Text."""
    return "" if value is None else str(value).strip()


def is_de(value: object) -> bool:
    """DE-Ländercode konservativ prüfen."""
    return normalize_text(value).upper() == "DE"


def load_relevant_performing_rus(movement_path: Path) -> tuple[list[str], str, list[str]]:
    """
    PerformingRUs aus DE-relevanten Bewegungen ermitteln.

    Primär gilt exakt die fachliche Regel:
    OriginCountryISO = DE ODER DestinationCountryISO = DE.

    Falls die detaillierten Länderfelder in der konkreten Rohdatei fehlen,
    wird Country als technischer Fallback verwendet und als Warnung ausgegeben.
    """
    if not movement_path.exists():
        raise FileNotFoundError(f"LocomotiveMovement.csv fehlt: {movement_path}")

    delimiter = detect_delimiter(movement_path)

    with movement_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)

        if not reader.fieldnames:
            raise RuntimeError(f"Headerzeile fehlt: {movement_path}")

        fieldnames = [str(name).strip() for name in reader.fieldnames]
        performing_ru_column = find_column(fieldnames, PERFORMING_RU_CANDIDATES)
        origin_column = find_column(fieldnames, ORIGIN_COUNTRY_CANDIDATES)
        destination_column = find_column(fieldnames, DESTINATION_COUNTRY_CANDIDATES)
        country_fallback_column = find_column(fieldnames, COUNTRY_FALLBACK_CANDIDATES)

        if performing_ru_column is None:
            raise RuntimeError(
                "Keine PerformingRU-Spalte gefunden. Erwartete Kandidaten: "
                + ", ".join(PERFORMING_RU_CANDIDATES)
            )

        warnings: list[str] = []

        if origin_column is None and destination_column is None:
            if country_fallback_column is None:
                raise RuntimeError(
                    "Keine Länderfelder gefunden. Erwartet werden OriginCountryISO "
                    "und/oder DestinationCountryISO; als Fallback wird Country unterstützt."
                )

            warnings.append(
                "OriginCountryISO und DestinationCountryISO fehlen. "
                f"Technischer Fallback über {country_fallback_column} verwendet."
            )

        relevant_rus: set[str] = set()
        relevant_row_count = 0

        for row in reader:
            if origin_column is not None or destination_column is not None:
                de_relevant = (
                    (origin_column is not None and is_de(row.get(origin_column)))
                    or (
                        destination_column is not None
                        and is_de(row.get(destination_column))
                    )
                )
            else:
                de_relevant = is_de(row.get(country_fallback_column))

            if not de_relevant:
                continue

            relevant_row_count += 1
            performing_ru = normalize_text(row.get(performing_ru_column))

            if performing_ru:
                relevant_rus.add(performing_ru)

    if not relevant_rus:
        raise RuntimeError(
            "Keine befüllte PerformingRU in DE-relevanten Bewegungen gefunden. "
            "Dummy-Mapping wurde nicht erzeugt."
        )

    warnings.append(f"DE-relevante Bewegungszeilen ausgewertet: {relevant_row_count}")

    return sorted(relevant_rus), performing_ru_column, warnings


def build_dummy_id(role_code: str, performing_ru: str, used_ids: set[str]) -> str:
    """Deterministische 13-stellige Dummy-Marktpartner-ID je Rolle und RU erzeugen."""
    role_prefix = {
        "ANU_VENS": "991",
        "ANE_TENS": "992",
    }[role_code]

    digest = hashlib.sha256(f"{role_code}|{performing_ru}".encode("utf-8")).hexdigest()
    numeric_part = int(digest[:16], 16) % 10_000_000_000

    for offset in range(10_000):
        candidate = role_prefix + f"{(numeric_part + offset) % 10_000_000_000:010d}"
        if candidate not in used_ids:
            used_ids.add(candidate)
            return candidate

    raise RuntimeError("Keine eindeutige Dummy-Marktpartner-ID erzeugbar.")


def backup_if_exists(path: Path) -> Path | None:
    """Vorhandene Mappingdatei mit Zeitstempel sichern."""
    if not path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak_{timestamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def build_dummy_rows(performing_rus: list[str]) -> list[dict[str, str]]:
    """Je RU getrennte ANU_VENS- und ANE_TENS-Dummyzeilen erzeugen."""
    used_ids: set[str] = set()
    rows: list[dict[str, str]] = []

    for role_code in ["ANU_VENS", "ANE_TENS"]:
        for performing_ru in performing_rus:
            market_partner_id = build_dummy_id(
                role_code=role_code,
                performing_ru=performing_ru,
                used_ids=used_ids,
            )

            rows.append(
                {
                    "source_system": "RailCube/DataLake",
                    "source_field": "PerformingRU",
                    "source_value": performing_ru,
                    "role_code": role_code,
                    "official_company_name": performing_ru,
                    "market_partner_id": market_partner_id,
                    "active_flag": "Y",
                    "match_method": "DUMMY_EXACT",
                    "match_score": "1.0",
                    "manual_review": "N",
                    "comment": "DUMMY TESTDATA - nicht produktiv verwenden",
                }
            )

    return rows


def write_reference_file(path: Path, rows: list[dict[str, str]]) -> None:
    """Rollenbezogene Referenzdatei im von run_all.py erwarteten Format schreiben."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")

        for role_code, role_label in [
            ("ANU_VENS", "ANu-vEns (Nutzer) im Bahnstromnetz"),
            ("ANE_TENS", "ANe-tEns (Halter) im Bahnstromnetz"),
        ]:
            writer.writerow([role_label, ""])
            writer.writerow(["Unternehmensname", "Marktpartner-ID"])

            for row in rows:
                if row["role_code"] == role_code:
                    writer.writerow(
                        [
                            row["official_company_name"],
                            row["market_partner_id"],
                        ]
                    )

            writer.writerow([])


def write_mapping_file(path: Path, rows: list[dict[str, str]]) -> None:
    """Explizite Mappingdatei für den produktiven MAPPING_IMPORT-Pfad schreiben."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MAPPING_HEADERS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dummy-vEns-/tEns-Mappings aus DE-relevanten Bewegungen erzeugen."
    )
    parser.add_argument(
        "--movement-file",
        type=Path,
        default=DEFAULT_MOVEMENT_PATH,
        help="Pfad zur LocomotiveMovement.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MAP_DIR,
        help="Zielordner für die beiden Mappingdateien",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    movement_path = args.movement_file.resolve()
    output_dir = args.output_dir.resolve()
    reference_path = output_dir / DEFAULT_REFERENCE_PATH.name
    mapping_path = output_dir / DEFAULT_MAPPING_PATH.name

    performing_rus, detected_ru_column, warnings = load_relevant_performing_rus(
        movement_path=movement_path
    )
    rows = build_dummy_rows(performing_rus)

    reference_backup = backup_if_exists(reference_path)
    mapping_backup = backup_if_exists(mapping_path)

    write_reference_file(reference_path, rows)
    write_mapping_file(mapping_path, rows)

    print("")
    print("=" * 80)
    print("Dummy-vEns-/tEns-Mapping erzeugt")
    print("=" * 80)
    print(f"Quelle:                  {movement_path}")
    print(f"PerformingRU-Spalte:     {detected_ru_column}")
    print(f"Relevante PerformingRUs: {len(performing_rus)}")
    print(f"Dummy-Mappingzeilen:     {len(rows)}")
    print(f"Referenzdatei:           {reference_path}")
    print(f"Mappingdatei:            {mapping_path}")

    if reference_backup:
        print(f"Backup Referenzdatei:    {reference_backup}")

    if mapping_backup:
        print(f"Backup Mappingdatei:     {mapping_backup}")

    for warning in warnings:
        print(f"Hinweis:                 {warning}")

    print("")
    print("ACHTUNG: Die erzeugten Marktpartner-IDs sind ausschließlich Dummy-Testdaten.")
    print("Sie dürfen nicht produktiv oder extern verwendet werden.")


if __name__ == "__main__":
    main()
