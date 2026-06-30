from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from loco_timeline_multiday_axis_runtime_module import build_loco_multiday_axis_html  # noqa: E402


def test_multiday_axis_uses_date_labels_instead_of_single_day_hours():
    segments = pd.DataFrame(
        [
            {
                "Meldetag": "2026-06-23",
                "Loknummer": "L1",
                "Halter": "Holder A",
                "Nutzer / PerformingRU": "RU A",
                "Status": "Zugewiesen",
                "StatusPriorität": 20,
                "StartMinute": 0,
                "EndMinute": 1440,
                "Tooltip": "Segment",
                "Im Filterzeitraum": True,
            },
            {
                "Meldetag": "2026-06-28",
                "Loknummer": "L1",
                "Halter": "Holder A",
                "Nutzer / PerformingRU": "RU A",
                "Status": "GAP",
                "StatusPriorität": 30,
                "StartMinute": 720,
                "EndMinute": 780,
                "Tooltip": "Gap",
                "Im Filterzeitraum": True,
            },
        ]
    )

    html = build_loco_multiday_axis_html(
        segments,
        date_from=date(2026, 6, 23),
        date_to=date(2026, 6, 28),
        context_days=1,
    )

    assert "22.06." in html
    assert "23.06." in html
    assert "28.06." in html
    assert "29.06." in html
    assert "Arbeitszeitraum 23.06.2026 bis 28.06.2026" in html
    assert "00:00</span><span>06:00" not in html
    assert html.count('<div class="loco-row">') == 1
