from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from role_scope_module import LTE_DE_ROLE, LTE_NL_ROLE  # noqa: E402
from role_scope_registry_module import (  # noqa: E402
    build_scope_registry,
    filter_dataframe_with_registry,
)


def _timeline() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_type": ["MOVEMENT", "MOVEMENT", "GAP", "GAP"],
            "loco_no": ["DE-LOCO", "NL-LOCO", "DE-LOCO", "UNKNOWN-LOCO"],
            "transport_number": ["DE-TR", "NL-TR", "", ""],
            "performing_ru": [
                "LTE DE - LTE Germany GmbH",
                "LTE NL - LTE Netherlands B.V.",
                "",
                "",
            ],
        }
    )


def test_registry_filters_related_quality_rows() -> None:
    registry = build_scope_registry(_timeline(), LTE_DE_ROLE)
    gate = pd.DataFrame(
        {
            "loco_no": ["DE-LOCO", "NL-LOCO", "UNKNOWN-LOCO"],
            "gate_status": ["BLOCKED", "BLOCKED", "BLOCKED"],
        }
    )

    filtered = filter_dataframe_with_registry(gate, LTE_DE_ROLE, registry)

    assert filtered["loco_no"].tolist() == ["DE-LOCO", "UNKNOWN-LOCO"]


def test_gap_rows_follow_known_locomotive_scope() -> None:
    registry = build_scope_registry(_timeline(), LTE_NL_ROLE)
    gaps = pd.DataFrame(
        {
            "row_type": ["GAP", "GAP", "GAP"],
            "loco_no": ["DE-LOCO", "NL-LOCO", "UNKNOWN-LOCO"],
            "performing_ru": ["", "", ""],
        }
    )

    filtered = filter_dataframe_with_registry(gaps, LTE_NL_ROLE, registry)

    assert filtered["loco_no"].tolist() == ["NL-LOCO", "UNKNOWN-LOCO"]
