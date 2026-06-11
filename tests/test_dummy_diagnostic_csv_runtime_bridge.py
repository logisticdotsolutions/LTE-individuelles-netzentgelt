from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dummy_diagnostic_csv_runtime_bridge as bridge  # noqa: E402


def test_augment_dummy_types_marks_catalogued_locomotive(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_read_mapping_rows",
        lambda: [{"loco_no": "91850000002-4", "reason": "known"}],
    )
    data = pd.DataFrame(
        [
            {"LocomotiveNo": "91850000002-4", "LocomotiveType": "Electric"},
            {"LocomotiveNo": "91806189001-1", "LocomotiveType": "Electric"},
        ]
    )

    result = bridge._augment_dummy_types(data)

    assert result.loc[0, "LocomotiveType"] == "Electric | Dummy-Katalog"
    assert result.loc[1, "LocomotiveType"] == "Electric"


def test_augment_dummy_types_creates_type_column_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_read_mapping_rows",
        lambda: [{"loco_no": "91850000002-4", "reason": "known"}],
    )
    data = pd.DataFrame([{"LocomotiveNo": "91850000002-4"}])

    result = bridge._augment_dummy_types(data)

    assert result.loc[0, "LocomotiveType"] == "Dummy-Katalog"


def test_augment_dummy_types_uses_preloaded_catalog_without_reading_mapping(monkeypatch) -> None:
    def fail_read():
        raise AssertionError("mapping must not be reread when a preloaded catalog is supplied")

    monkeypatch.setattr(bridge, "_read_mapping_rows", fail_read)
    data = pd.DataFrame([{"LocomotiveNo": "91850000002-4", "LocomotiveType": "Electric"}])

    result = bridge._augment_dummy_types(data, known={"91850000002-4"})

    assert result.loc[0, "LocomotiveType"] == "Electric | Dummy-Katalog"


def test_known_dummy_locomotives_normalizes_and_deduplicates_rows() -> None:
    result = bridge._known_dummy_locomotives(
        [
            {"loco_no": " 91850000002-4 "},
            {"loco_no": "91850000002-4"},
            {"loco_no": ""},
        ]
    )

    assert result == {"91850000002-4"}


def test_is_locomotive_movement_source_accepts_windows_path() -> None:
    assert bridge._is_locomotive_movement_source(Path("data/00_raw/LocomotiveMovement.csv"))
