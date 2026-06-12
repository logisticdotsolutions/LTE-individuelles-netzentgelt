from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mp_id_import_module as module


def test_specific_role_headings_win_over_generic_substrings() -> None:
    text = """
    Messdienstleister im Bahnstromnetz
    DB Energie Dummy 1900100500000
    Übertragungsnetzbetreiber im Bahnstromnetz
    DB Energie GmbH 1900100310003
    Anfordernde Netzbetreiber
    DB Energie GmbH 1900100330001
    Dienstleister im Bahnstromnetz
    UKL iT & Logistik GmbH 1900100390013
    Netzbetreiber im Bahnstromnetz
    DB Energie GmbH 1900100370007
    """

    assert [(entry.role_code, entry.market_partner_id) for entry in module.parse_entries(text)] == [
        ("METERING_SERVICE_PROVIDER", "1900100500000"),
        ("TSO", "1900100310003"),
        ("REQUESTING_GRID_OPERATOR", "1900100330001"),
        ("SERVICE_PROVIDER", "1900100390013"),
        ("GRID_OPERATOR", "1900100370007"),
    ]
