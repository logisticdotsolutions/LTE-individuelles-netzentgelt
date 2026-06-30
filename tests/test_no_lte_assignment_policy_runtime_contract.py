from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import loco_timeline_calendar_runtime_module as timeline  # noqa: E402
from no_lte_assignment_policy_runtime_module import (  # noqa: E402
    install_no_lte_assignment_policy_runtime,
    restore_no_lte_assignment_policy_runtime,
)


def test_normal_gap_stays_gap_but_marker_is_outside():
    original = install_no_lte_assignment_policy_runtime()
    marker = "keine" + " lte" + " zuordnung"
    try:
        normal_status = timeline.classify_timeline_status(
            row_type="GAP",
            is_de_relevant=True,
            holder="holder",
            performing_ru="ru",
        )
        marker_status = timeline.classify_timeline_status(
            row_type="GAP",
            is_de_relevant=True,
            holder=marker,
            performing_ru=marker,
        )
    finally:
        restore_no_lte_assignment_policy_runtime(original)

    assert normal_status == "GAP"
    assert marker_status == "Außerhalb DE"
