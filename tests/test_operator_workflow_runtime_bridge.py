from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operator_workflow_runtime_bridge import load_case_timeline_once  # noqa: E402


def test_load_case_timeline_once_calls_loader_only_once() -> None:
    cache: dict[str, pd.DataFrame] = {}
    calls = {"count": 0}

    def loader() -> pd.DataFrame:
        calls["count"] += 1
        return pd.DataFrame([{"loco_no": "9180"}])

    first = load_case_timeline_once(cache, loader=loader)
    second = load_case_timeline_once(cache, loader=loader)

    assert calls["count"] == 1
    assert first is second
    assert first["loco_no"].tolist() == ["9180"]
