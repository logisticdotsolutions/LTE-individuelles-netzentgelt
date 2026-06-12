from datetime import date, datetime
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import zuordnungen_hardened_preview_module as module


def make_preview(vens):
    return pd.DataFrame([{
        "TfzE oder tEns*": "91801234567-8",
        "Beginn der Zuordnung*": datetime(2026, 6, 9, 8, 15),
        "Ende der Zuordnung": datetime(2026, 6, 9, 12, 45),
        "Nutzer-vEns*": vens,
        "Marktpartner ID für Nutzungsüberlassung": "unsicher",
        "PerformingRU": "LTE DE - LTE Germany GmbH",
        "Exportstatus": "EXPORTFÄHIG",
        "Hinweis": "",
    }])


def build(monkeypatch, vens):
    monkeypatch.setattr(module, "build_zuordnungen_holding_preview", lambda **kwargs: make_preview(vens))
    return module.build_hardened_zuordnungen_holding_preview(
        db_path=Path("dummy.duckdb"), date_from=date(2026, 6, 9), date_to=date(2026, 6, 9)
    )


def test_preview_blanks_optional_transfer_id(monkeypatch):
    result = build(monkeypatch, "1900100300001")
    assert result.iloc[0][module.OPTIONAL_TRANSFER_MP_COLUMN] == ""
    assert result.iloc[0]["Exportstatus"] == "EXPORTFÄHIG"


def test_preview_blocks_company_name_fallback(monkeypatch):
    result = build(monkeypatch, "LTE DE - LTE Germany GmbH")
    assert result.iloc[0]["Exportstatus"] == "BLOCKIERT"
    assert "Z01_VENS_COMPANY_NAME_FALLBACK" in result.iloc[0]["Hinweis"]
