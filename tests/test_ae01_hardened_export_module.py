from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import sys

import pytest
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ae01_hardened_export_module as module  # noqa: E402


class DummyConnection:
    def close(self) -> None:
        pass


def _row(**overrides):
    row = {
        "locomotive_no": "91801234567-8",
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "user_vens": "1900100300001",
        "event_location": "München Nord",
        "event_ts": datetime(2026, 6, 9, 8, 0),
        "network_status": "einfahrend",
    }
    row.update(overrides)
    return row


def _build(monkeypatch, tmp_path: Path, row):
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    monkeypatch.setattr(module.duckdb, "connect", lambda *_args, **_kwargs: DummyConnection())
    monkeypatch.setattr(module, "_fetch_hardened_ae01_rows", lambda **_kwargs: [row])
    monkeypatch.setattr(module, "_resolve_export_header", lambda **_kwargs: ("1900100300001", "LTE Germany GmbH"))
    return module.build_hardened_aufenthaltsereignis_xlsx(
        db_path=db_path,
        performing_ru_values=("LTE DE - LTE Germany GmbH",),
        export_label="LTE_DE",
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )


def test_ae01_writes_mapped_vens(monkeypatch, tmp_path: Path) -> None:
    result = _build(monkeypatch, tmp_path, _row())
    worksheet = load_workbook(BytesIO(result.content))["Aufenthaltsereignisse"]
    assert worksheet["B8"].value == "1900100300001"
    assert worksheet["E8"].value == "einfahrend"


def test_ae01_blocks_company_name_as_vens(monkeypatch, tmp_path: Path) -> None:
    performing_ru = "LTE DE - LTE Germany GmbH"
    with pytest.raises(RuntimeError, match="AE01_VENS_COMPANY_NAME_FALLBACK"):
        _build(monkeypatch, tmp_path, _row(user_vens=performing_ru))
