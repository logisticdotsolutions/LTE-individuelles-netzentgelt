from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_suggestion_visibility_module import hide_accepted_active_suggestions  # noqa: E402


def test_accepted_suggestion_is_hidden_while_override_is_active(tmp_path: Path) -> None:
    acceptance_log = tmp_path / "manual_override_suggestion_acceptance_log.csv"
    pd.DataFrame(
        {
            "suggestion_id": ["SUG_KEEP_HIDDEN", "SUG_RESHOW"],
            "override_id": ["OVR_ACTIVE", "OVR_INACTIVE"],
        }
    ).to_csv(acceptance_log, sep=";", index=False, encoding="utf-8-sig")

    overrides = pd.DataFrame(
        {
            "override_id": ["OVR_ACTIVE", "OVR_INACTIVE"],
            "active_flag": ["Y", "N"],
        }
    )
    suggestions = pd.DataFrame(
        {
            "suggestion_id": ["SUG_KEEP_HIDDEN", "SUG_RESHOW", "SUG_NEW"],
            "suggested_value": ["A", "B", "C"],
        }
    )

    visible = hide_accepted_active_suggestions(
        suggestions,
        acceptance_log_path=acceptance_log,
        overrides=overrides,
    )

    assert visible["suggestion_id"].tolist() == ["SUG_RESHOW", "SUG_NEW"]
