from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ukl_preflight_module as module  # noqa: E402


def _z01_row(**overrides):
    row = {
        "locomotive_no": "91801234567-8",
        "usage_start": datetime(2026, 6, 9, 8, 15),
        "usage_end": datetime(2026, 6, 9, 12, 45),
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "user_vens": "1900100300001",
        "holder_market_partner_id": "",
    }
    row.update(overrides)
    return row


def test_valid_z01_row_passes_preflight() -> None:
    assert module.validate_z01_rows([_z01_row()]) == []


def test_z01_rejects_non_quarter_hour_boundary() -> None:
    issues = module.validate_z01_rows([
        _z01_row(usage_start=datetime(2026, 6, 9, 8, 16))
    ])

    assert {issue.code for issue in issues} == {"Z01_BEGIN_NOT_QUARTER_HOUR"}


def test_z01_rejects_period_below_15_minutes() -> None:
    issues = module.validate_z01_rows([
        _z01_row(
            usage_start=datetime(2026, 6, 9, 8, 15),
            usage_end=datetime(2026, 6, 9, 8, 20),
        )
    ])

    assert "Z01_END_NOT_QUARTER_HOUR" in {issue.code for issue in issues}
    assert "Z01_PERIOD_TOO_SHORT" in {issue.code for issue in issues}


def test_z01_rejects_overlapping_rows_for_same_locomotive() -> None:
    issues = module.validate_z01_rows([
        _z01_row(
            usage_start=datetime(2026, 6, 9, 8, 0),
            usage_end=datetime(2026, 6, 9, 10, 0),
        ),
        _z01_row(
            usage_start=datetime(2026, 6, 9, 9, 45),
            usage_end=datetime(2026, 6, 9, 11, 0),
        ),
    ])

    assert "Z01_OVERLAP" in {issue.code for issue in issues}


def test_z01_rejects_performing_ru_company_name_as_vens() -> None:
    performing_ru = "LTE DE - LTE Germany GmbH"
    issues = module.validate_z01_rows([
        _z01_row(performing_ru=performing_ru, user_vens=performing_ru)
    ])

    assert {issue.code for issue in issues} == {"Z01_VENS_COMPANY_NAME_FALLBACK"}


def test_n01_requires_valid_recipient_market_partner_id() -> None:
    missing = module.validate_n01_rows([
        _z01_row(holder_market_partner_id="")
    ])
    malformed = module.validate_n01_rows([
        _z01_row(holder_market_partner_id="LTE Holding")
    ])
    valid = module.validate_n01_rows([
        _z01_row(holder_market_partner_id="1900100300393")
    ])

    assert "N01_RECIPIENT_MP_ID_REQUIRED" in {issue.code for issue in missing}
    assert "N01_RECIPIENT_MP_ID_INVALID" in {issue.code for issue in malformed}
    assert valid == []


def test_ae01_requires_mapped_vens_and_allowed_network_status() -> None:
    issues = module.validate_ae01_rows([
        {
            "locomotive_no": "91801234567-8",
            "performing_ru": "LTE DE - LTE Germany GmbH",
            "user_vens": "LTE DE - LTE Germany GmbH",
            "event_location": "München Nord",
            "event_ts": datetime(2026, 6, 9, 8, 0),
            "network_status": "unknown",
        }
    ])

    assert {issue.code for issue in issues} == {
        "AE01_VENS_COMPANY_NAME_FALLBACK",
        "AE01_NETWORK_STATUS_INVALID",
    }


def test_raise_if_blocking_issues_contains_actionable_details() -> None:
    issue = module.PreflightIssue(
        code="Z01_TEST",
        message="Fehlertext",
        row_number=2,
    )

    with pytest.raises(RuntimeError, match="Z01_TEST Zeile 2"):
        module.raise_if_blocking_issues([issue], export_name="Z01-Zuordnung")
