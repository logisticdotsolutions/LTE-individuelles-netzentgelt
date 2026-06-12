from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import sys
import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import zuordnungen_hardened_export_module as module


class DummyConnection:
    def close(self):
        pass


def make_row(**overrides):
    row = {
        "locomotive_no": "91801234567-8",
        "usage_start": datetime(2026, 6, 9, 8, 15),
        "usage_end": datetime(2026, 6, 9, 12, 45),
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "movement_count": 2,
        "user_vens": "1900100300001",
        "holder_market_partner_id": None,
    }
    row.update(overrides)
    return row


def build(monkeypatch, tmp_path, row):
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    monkeypatch.setattr(module.duckdb, "connect", lambda *args, **kwargs: DummyConnection())
    monkeypatch.setattr(module, "_fetch_hardened_holding_rows", lambda *args, **kwargs: [row])
    return module.build_hardened_zuordnungen_holding_xlsx(
        db_path=db_path,
        holding_market_partner_id="1900100300393",
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )


def test_holding_z01_writes_mapped_vens_and_empty_optional_transfer_mp(monkeypatch, tmp_path):
    result = build(monkeypatch, tmp_path, make_row())
    sheet = load_workbook(BytesIO(result.content))["Zuordnungsdatensatzliste"]
    assert sheet["B2"].value == "Z01"
    assert sheet["B3"].value == "1900100300393"
    assert sheet["D7"].value == "1900100300001"
    assert sheet["E7"].value in (None, "")


def test_holding_z01_blocks_company_name_as_vens(monkeypatch, tmp_path):
    performing_ru = "LTE DE - LTE Germany GmbH"
    with pytest.raises(RuntimeError, match="Z01_VENS_COMPANY_NAME_FALLBACK"):
        build(monkeypatch, tmp_path, make_row(user_vens=performing_ru))
