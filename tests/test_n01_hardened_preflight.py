from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import n01_hardened_export_module as module  # noqa: E402


class DummyConnection:
    def close(self) -> None:
        pass


def _row(**overrides):
    row = {
        "locomotive_no": "91801234567-8",
        "usage_start": datetime(2026, 6, 9, 8, 15),
        "usage_end": datetime(2026, 6, 9, 12, 45),
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "movement_count": 2,
        "user_vens": "1900100300001",
        "holder_market_partner_id": "1900100300393",
    }
    row.update(overrides)
    return row


def _build(monkeypatch, tmp_path: Path, row):
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    monkeypatch.setattr(module.duckdb, "connect", lambda *_args, **_kwargs: DummyConnection())
    monkeypatch.setattr(module, "_fetch_usage_segments", lambda **_kwargs: [row])
    monkeypatch.setattr(module, "_resolve_export_header", lambda **_kwargs: ("1900100300001", "LTE Germany GmbH"))
    return module.build_hardened_n01_xlsx(
        db_path=db_path,
        performing_ru_values=("LTE DE - LTE Germany GmbH",),
        export_label="LTE_DE",
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )


def test_n01_blocks_non_holding_recipient(monkeypatch, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="N01_RECIPIENT_NOT_LTE_HOLDING"):
        _build(monkeypatch, tmp_path, _row(holder_market_partner_id="1900100300009"))


def test_n01_blocks_company_name_as_vens(monkeypatch, tmp_path: Path) -> None:
    performing_ru = "LTE DE - LTE Germany GmbH"
    with pytest.raises(RuntimeError, match="N01_VENS_COMPANY_NAME_FALLBACK"):
        _build(monkeypatch, tmp_path, _row(user_vens=performing_ru))
