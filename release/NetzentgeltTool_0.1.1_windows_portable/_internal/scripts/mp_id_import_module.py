from __future__ import annotations

from csv import DictReader, DictWriter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from json import dump
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen
import re

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_URL = "https://www.dbenergie.de/resource/blob/4570920/ce260c87155d7495c47acd35cd0dae29/Datei-Marktpartner-IDs-PDF-data.pdf"
CURRENT_CSV = ROOT / "data" / "01_mapping" / "public_market_partner_ids.csv"
AUDIT_DIR = ROOT / "data" / "04_audit" / "mp_id_imports"

ROLE_PATTERNS = (
    ("ANu-vEns (Nutzer)", "ANU_VENS"),
    ("ANe-tEns (Halter)", "ANE_TENS"),
    ("Messdienstleister", "METERING_SERVICE_PROVIDER"),
    ("Übertragungsnetzbetreiber", "TSO"),
    ("Anfordernde Netzbetreiber", "REQUESTING_GRID_OPERATOR"),
    ("Betreiber einer technischen Ressource", "TECHNICAL_RESOURCE_OPERATOR"),
    ("Einsatzverantwortliche", "RESPONSIBLE_PARTY"),
    ("Bilankreisverantwortliche", "BALANCING_RESPONSIBLE"),
    ("Bilanzkreisverantwortliche", "BALANCING_RESPONSIBLE"),
    ("Stromlieferanten", "SUPPLIER"),
    ("Dienstleister", "SERVICE_PROVIDER"),
    ("Netzbetreiber", "GRID_OPERATOR"),
)
ENTRY_PATTERN = re.compile(r"^(?P<name>.+?)\s+(?P<mp_id>\d{13})$")
DATE_PATTERN = re.compile(r"Stand:\s*(\d{2}\.\d{2}\.\d{4})")


@dataclass(frozen=True)
class MarketPartnerEntry:
    role_code: str
    official_company_name: str
    market_partner_id: str


def sha256_hex(content: bytes) -> str:
    return sha256(content).hexdigest()


def download_pdf(url: str = DEFAULT_SOURCE_URL, timeout: int = 30) -> bytes:
    request = Request(url, headers={"User-Agent": "LTE-Netzentgelt-MP-ID-Importer/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_document_date(text: str) -> str:
    match = DATE_PATTERN.search(text)
    if not match:
        raise ValueError("Dokumentstand fehlt in der DB-Energie-Datei.")
    return datetime.strptime(match.group(1), "%d.%m.%Y").date().isoformat()


def parse_entries(text: str) -> list[MarketPartnerEntry]:
    role_code = ""
    entries: list[MarketPartnerEntry] = []
    seen: set[tuple[str, str]] = set()

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line:
            continue

        for needle, mapped_role in ROLE_PATTERNS:
            if needle.casefold() in line.casefold():
                role_code = mapped_role
                break
        else:
            match = ENTRY_PATTERN.match(line)
            if not match or not role_code:
                continue
            key = (role_code, match.group("mp_id"))
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                MarketPartnerEntry(
                    role_code=role_code,
                    official_company_name=match.group("name").strip(),
                    market_partner_id=match.group("mp_id"),
                )
            )

    if not entries:
        raise ValueError("Keine Marktpartner-IDs aus der DB-Energie-Datei gelesen.")
    return entries


def load_existing(path: Path = CURRENT_CSV) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (row["role_code"], row["market_partner_id"]): row
            for row in DictReader(handle, delimiter=";")
        }


def build_delta(entries: Iterable[MarketPartnerEntry], existing: dict[tuple[str, str], dict[str, str]]):
    current = {(e.role_code, e.market_partner_id): e for e in entries}
    delta = []
    for key, entry in current.items():
        old = existing.get(key)
        status = "NEW" if old is None else (
            "UNCHANGED" if old.get("official_company_name") == entry.official_company_name else "CHANGED"
        )
        delta.append({**asdict(entry), "delta_status": status})
    for key, old in existing.items():
        if key not in current:
            delta.append({
                "role_code": old["role_code"],
                "official_company_name": old["official_company_name"],
                "market_partner_id": old["market_partner_id"],
                "delta_status": "REMOVED",
            })
    return sorted(delta, key=lambda row: (row["role_code"], row["market_partner_id"]))


def _write_csv(path: Path, rows: Iterable[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = DictWriter(handle, delimiter=";", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_import(source_url: str = DEFAULT_SOURCE_URL) -> dict[str, object]:
    imported_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pdf = download_pdf(source_url)
    digest = sha256_hex(pdf)
    text = extract_pdf_text(pdf)
    document_date = parse_document_date(text)
    entries = parse_entries(text)
    existing = load_existing()
    delta = build_delta(entries, existing)

    current_rows = [
        {
            "source_url": source_url,
            "source_document_date": document_date,
            "source_sha256": digest,
            "role_code": e.role_code,
            "official_company_name": e.official_company_name,
            "market_partner_id": e.market_partner_id,
            "active_flag": "Y",
            "imported_at_utc": imported_at,
        }
        for e in entries
    ]
    _write_csv(CURRENT_CSV, current_rows, list(current_rows[0]))

    audit_dir = AUDIT_DIR / imported_at
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / "source.pdf").write_bytes(pdf)
    _write_csv(audit_dir / "delta.csv", delta, ["role_code", "official_company_name", "market_partner_id", "delta_status"])
    metadata = {
        "source_url": source_url,
        "source_document_date": document_date,
        "source_sha256": digest,
        "imported_at_utc": imported_at,
        "entry_count": len(entries),
        "delta_counts": {status: sum(1 for row in delta if row["delta_status"] == status) for status in {"NEW", "CHANGED", "REMOVED", "UNCHANGED"}},
    }
    with (audit_dir / "metadata.json").open("w", encoding="utf-8") as handle:
        dump(metadata, handle, ensure_ascii=False, indent=2)
    return metadata
