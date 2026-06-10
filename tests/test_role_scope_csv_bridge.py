from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from role_scope_csv_bridge import build_scoped_csv_reader  # noqa: E402
from role_scope_module import LTE_DE_ROLE  # noqa: E402


def test_raw_diagnostics_are_filtered_when_scope_columns_exist(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "data" / "00_raw"
    export_dir = tmp_path / "data" / "03_exports"
    raw_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)

    raw_path = raw_dir / "LocomotiveMovement.csv"
    pd.DataFrame(
        {
            "id": ["de", "nl", "shared"],
            "PerformingRU": [
                "LTE DE - LTE Germany GmbH",
                "LTE NL - LTE Netherlands B.V.",
                "External RU",
            ],
        }
    ).to_csv(raw_path, index=False)

    import role_scope_csv_bridge as bridge

    monkeypatch.setattr(bridge, "RAW_DIR", raw_dir.resolve())
    monkeypatch.setattr(bridge, "EXPORT_DIR", export_dir.resolve())
    monkeypatch.setattr(bridge, "TIMELINE_PATH", (export_dir / "core_loco_timeline.csv").resolve())

    scoped_reader = build_scoped_csv_reader(pd.read_csv, LTE_DE_ROLE)
    result = scoped_reader(raw_path)

    assert result["id"].tolist() == ["de", "shared"]


def test_raw_diagnostics_without_scope_columns_remain_visible(tmp_path: Path, monkeypatch) -> None:
    raw_dir = tmp_path / "data" / "00_raw"
    export_dir = tmp_path / "data" / "03_exports"
    raw_dir.mkdir(parents=True)
    export_dir.mkdir(parents=True)

    raw_path = raw_dir / "Locomotive.csv"
    pd.DataFrame({"id": ["a", "b"]}).to_csv(raw_path, index=False)

    import role_scope_csv_bridge as bridge

    monkeypatch.setattr(bridge, "RAW_DIR", raw_dir.resolve())
    monkeypatch.setattr(bridge, "EXPORT_DIR", export_dir.resolve())
    monkeypatch.setattr(bridge, "TIMELINE_PATH", (export_dir / "core_loco_timeline.csv").resolve())

    scoped_reader = build_scoped_csv_reader(pd.read_csv, LTE_DE_ROLE)
    result = scoped_reader(raw_path)

    assert result["id"].tolist() == ["a", "b"]
