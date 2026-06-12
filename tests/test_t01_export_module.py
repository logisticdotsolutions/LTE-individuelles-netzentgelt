from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import sys
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import t01_export_module as module


class DummyConnection:
    def close(self):
        pass


def test_t01_export_writes_official_schema(monkeypatch, tmp_path):
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    rows = [{
        "locomotive_no": "91801234567-8",
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "user_vens": "1900100300001",
        "departure_ts": datetime(2026, 6, 9, 8, 0),
        "departure_location": "8000261",
        "arrival_ts": datetime(2026, 6, 9, 10, 0),
        "arrival_location": "8000207",
        "distance_km": 120.5,
        "trailer_weight_t": 900.0,
        "train_no": "4711",
        "order_criterion": "Güterverkehr",
        "usage_type": "SE",
        "max_speed_kmh": 120,
        "traffic_day": date(2026, 6, 9),
        "is_multiple_unit": False,
    }]
    monkeypatch.setattr(module, "fetch_t01_rows", lambda **kwargs: rows)
    monkeypatch.setattr(module.duckdb, "connect", lambda *args, **kwargs: DummyConnection())
    monkeypatch.setattr(module, "_resolve_export_header", lambda **kwargs: ("1900100302454", "LTE Germany GmbH"))

    result = module.build_t01_xlsx(
        db_path=db_path,
        performing_ru_values=("LTE DE - LTE Germany GmbH",),
        virtual_extraction_point="1900100300001",
        export_label="LTE_DE",
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )

    sheet = load_workbook(BytesIO(result.content))["Traktionsleistungen"]
    assert sheet["B2"].value == "T01"
    assert sheet["B5"].value == "1900100300001"
    assert sheet["A9"].value == "91801234567-8"
    assert sheet["F9"].value == 120.5
    assert sheet["G9"].value == 900
    assert sheet["I9"].value == "Güterverkehr"
    assert sheet["J9"].value == "SE"
    assert sheet["K9"].value == 120
