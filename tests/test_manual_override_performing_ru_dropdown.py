from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manual_override_widget_value_module import EMPTY_DROPDOWN_VALUE, performing_ru_options  # noqa: E402


def test_performing_ru_dropdown_is_stable_and_deduplicated() -> None:
    timeline = pd.DataFrame(
        {
            "performing_ru": [
                "LTE NL - LTE Netherlands B.V.",
                "LTE DE - LTE Germany GmbH",
                "LTE NL - LTE Netherlands B.V.",
                "",
            ]
        }
    )

    options = performing_ru_options(
        timeline,
        current_value="LTE NL - LTE Netherlands B.V.",
        suggested_value="LTE DE - LTE Germany GmbH",
    )

    assert options[0] == EMPTY_DROPDOWN_VALUE
    assert options.count("LTE NL - LTE Netherlands B.V.") == 1
    assert options.count("LTE DE - LTE Germany GmbH") == 1
