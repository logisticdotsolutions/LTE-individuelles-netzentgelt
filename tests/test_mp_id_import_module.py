from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mp_id_import_module as module


SAMPLE_TEXT = """
DB Energie GmbH Marktpartner-ID (MP-ID)/Codenummern im Bahnstromnetz
ANu-vEns (Nutzer) im Bahnstromnetz
Unternehmensname MP-ID/Codenummer im Bahnstromnetz
LTE Logistik- und Transport-GmbH 1900100300393
LTE Netherlands B.V. 1900100301482
Stand: 30.04.2026 Seite 1 von 16
ANe-tEns (Halter) im Bahnstromnetz
Unternehmensname MP-ID/Codenummer im Bahnstromnetz
LTE Logistik- und Transport-GmbH 1900100400391
Dienstleister im Bahnstromnetz
Unternehmensname MP-ID/Codenummer im Bahnstromnetz
UKL iT & Logistik GmbH 1900100390013
"""


def test_parse_document_date() -> None:
    assert module.parse_document_date(SAMPLE_TEXT) == "2026-04-30"


def test_parse_entries_tracks_role_blocks() -> None:
    entries = module.parse_entries(SAMPLE_TEXT)
    assert [(entry.role_code, entry.market_partner_id) for entry in entries] == [
        ("ANU_VENS", "1900100300393"),
        ("ANU_VENS", "1900100301482"),
        ("ANE_TENS", "1900100400391"),
        ("SERVICE_PROVIDER", "1900100390013"),
    ]


def test_parse_entries_deduplicates_same_role_and_id() -> None:
    entries = module.parse_entries(SAMPLE_TEXT + "\nUKL iT & Logistik GmbH 1900100390013\n")
    assert len(entries) == 4


def test_build_delta_reports_new_changed_removed_and_unchanged() -> None:
    existing = {
        ("ANU_VENS", "1900100300393"): {
            "role_code": "ANU_VENS",
            "market_partner_id": "1900100300393",
            "official_company_name": "LTE Logistik- und Transport-GmbH",
        },
        ("ANE_TENS", "1900100400391"): {
            "role_code": "ANE_TENS",
            "market_partner_id": "1900100400391",
            "official_company_name": "LTE Logistik alt",
        },
        ("ANU_VENS", "1900100309999"): {
            "role_code": "ANU_VENS",
            "market_partner_id": "1900100309999",
            "official_company_name": "Removed Company",
        },
    }
    delta = module.build_delta(module.parse_entries(SAMPLE_TEXT), existing)
    status_by_id = {row["market_partner_id"]: row["delta_status"] for row in delta}
    assert status_by_id["1900100300393"] == "UNCHANGED"
    assert status_by_id["1900100400391"] == "CHANGED"
    assert status_by_id["1900100301482"] == "NEW"
    assert status_by_id["1900100309999"] == "REMOVED"
