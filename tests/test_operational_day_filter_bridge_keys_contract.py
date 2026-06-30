from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from operational_day_filter_ui_runtime_bridge import (  # noqa: E402
    CANONICAL_FROM_KEY,
    CANONICAL_TO_KEY,
    EARLY_FROM_KEY,
    EARLY_TO_KEY,
)


def test_early_operational_day_filter_uses_private_widget_keys():
    assert CANONICAL_FROM_KEY == "operational_day_filter_from"
    assert CANONICAL_TO_KEY == "operational_day_filter_to"
    assert EARLY_FROM_KEY != CANONICAL_FROM_KEY
    assert EARLY_TO_KEY != CANONICAL_TO_KEY
    assert EARLY_FROM_KEY.startswith("_early_")
    assert EARLY_TO_KEY.startswith("_early_")
