from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import error_rules
import export_module
import run_all
from tests.support.raw_identity import canonical_row_payload, source_row_hash, stable_source_row_identity


@pytest.mark.unit
def test_safe_name_and_identifiers_are_defensive():
    assert run_all.safe_name("Locomotive Movement.csv") == "raw_locomotive_movement"
    assert run_all.qident('a"b') == '"a""b"'
    assert error_rules.sql_lit("O'Reilly") == "'O''Reilly'"
    assert error_rules.qident('a"b') == '"a""b"'


@pytest.mark.unit
def test_company_normalization_is_conservative_and_stable():
    assert run_all.normalize_company_name_py(" LTE Österreich GmbH ") == "lteoesterreichgmbh"
    assert run_all.normalize_company_name_py("LTE-Österreich GmbH") == "lteoesterreichgmbh"
    assert run_all.normalize_company_name_py(None) == ""


@pytest.mark.unit
def test_export_day_bounds_are_inclusive():
    start, end = export_module._to_day_bounds(date(2026, 6, 1), date(2026, 6, 2))
    assert start == datetime(2026, 6, 1, 0, 0)
    assert end == datetime(2026, 6, 3, 0, 0)
    with pytest.raises(ValueError, match="Von-Datum"):
        export_module._to_day_bounds(date(2026, 6, 2), date(2026, 6, 1))


@pytest.mark.unit
def test_export_ru_helpers_trim_dedupe_and_reject_empty():
    assert export_module._as_ru_tuple([" RU ", "RU", "", "Other"]) == ("RU", "Other")
    assert export_module._placeholders(["a", "b"]) == "?, ?"
    with pytest.raises(ValueError, match="Mindestens eine PerformingRU"):
        export_module._placeholders([])


@pytest.mark.unit
def test_sha256_changes_with_file_content(tmp_path: Path):
    path = tmp_path / "source.csv"
    path.write_text("A;B\n1;2\n", encoding="utf-8")
    first = run_all.sha256(path)
    path.write_text("A;B\n1;3\n", encoding="utf-8")
    assert run_all.sha256(path) != first


@pytest.mark.unit
def test_source_row_hash_reference_contract_is_order_stable_and_content_sensitive():
    columns = ["TransportNumber", "LocomotiveNo", "ActualDeparture"]
    row_a = {"LocomotiveNo": " 9180 ", "ActualDeparture": "2026-06-01T10:00:00", "TransportNumber": "TR-1"}
    row_b = {"TransportNumber": "TR-1", "ActualDeparture": "2026-06-01T10:00:00", "LocomotiveNo": "9180"}
    row_c = {**row_b, "LocomotiveNo": "9181"}
    assert canonical_row_payload(row_a, columns) == canonical_row_payload(row_b, columns)
    assert source_row_hash(row_a, columns) == source_row_hash(row_b, columns)
    assert source_row_hash(row_a, columns) != source_row_hash(row_c, columns)


@pytest.mark.unit
def test_duplicate_source_rows_receive_stable_distinct_identities():
    row_hash = "abc"
    first = stable_source_row_identity("LocomotiveMovement.csv", row_hash, 1)
    second = stable_source_row_identity("LocomotiveMovement.csv", row_hash, 2)
    assert first != second
    assert first == stable_source_row_identity("locomotivemovement.csv", row_hash, 1)
    with pytest.raises(ValueError, match="mindestens 1"):
        stable_source_row_identity("x.csv", row_hash, 0)


@pytest.mark.unit
def test_iso_timestamp_reference_timezone():
    parsed = datetime.fromisoformat("2026-06-01T10:00:00+00:00")
    assert parsed.astimezone(timezone.utc).isoformat() == "2026-06-01T10:00:00+00:00"
