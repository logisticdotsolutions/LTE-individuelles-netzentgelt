from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from technical_loco_fallback_runtime_module import load_technical_loco_fallback_once  # noqa: E402


def test_load_technical_loco_fallback_once_calls_loader_only_once() -> None:
    cache: dict[str, pd.DataFrame] = {}
    calls = {"count": 0}

    def loader() -> pd.DataFrame:
        calls["count"] += 1
        return pd.DataFrame([{"Loknummer": "91850000002-4"}])

    first = load_technical_loco_fallback_once(cache, loader=loader)
    second = load_technical_loco_fallback_once(cache, loader=loader)

    assert calls["count"] == 1
    assert first is second
    assert first["Loknummer"].tolist() == ["91850000002-4"]
