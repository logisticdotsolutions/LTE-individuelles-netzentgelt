from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from loco_timeline_context_scope_runtime_module import _build_context_scoped_segments  # noqa: E402
from loco_timeline_visual_band_runtime_module import build_loco_visual_bands  # noqa: E402


def _segment(
    *,
    day: str,
    status: str,
    start: int,
    end: int,
    loco: str = "91806193933-9",
    event_type: str = "",
    report_scope: str = "",
    route_type: str = "",
    row_type: str = "MOVEMENT",
    holder: str = "ELL Austria GmbH",
    performing_ru: str = "LTE NL - LTE Netherlands B.V.",
) -> dict[str, object]:
    priority = {
        "Prüfen": 50,
        "Overlap": 40,
        "GAP": 30,
        "Zugewiesen": 20,
        "In DE": 10,
        "Außerhalb DE": 0,
    }[status]
    return {
        "Meldetag": day,
        "Loknummer": loco,
        "Halter": holder,
        "Nutzer / PerformingRU": performing_ru,
        "Status": status,
        "StatusPriorität": priority,
        "StartMinute": start,
        "EndMinute": end,
        "Route Type": route_type,
        "Event Type": event_type,
        "Row Type": row_type,
        "Report-Scope": report_scope,
        "Tooltip": f"{day} {status}",
        "Im Filterzeitraum": True,
    }


def test_visual_bands_merge_lueckenlose_movement_fragments_until_explicit_gap():
    segments = pd.DataFrame(
        [
            _segment(day="2026-06-25", status="Zugewiesen", start=9 * 60 + 52, end=22 * 60 + 11),
            _segment(day="2026-06-26", status="Zugewiesen", start=1 * 60 + 36, end=6 * 60 + 40),
            _segment(day="2026-06-27", status="Zugewiesen", start=13 * 60 + 16, end=22 * 60 + 10),
            _segment(day="2026-06-28", status="GAP", start=8 * 60, end=10 * 60),
        ]
    )

    bands = build_loco_visual_bands(segments, visible_from=date(2026, 6, 24))

    assert [band["status"] for band in bands] == ["Zugewiesen", "GAP"]
    assert bands[0]["start"] == 1 * 24 * 60 + 9 * 60 + 52
    assert bands[0]["end"] == 3 * 24 * 60 + 22 * 60 + 10
    assert bands[1]["start"] == 4 * 24 * 60 + 8 * 60


def test_visual_bands_use_event_colors_without_changing_hard_statuses():
    no_lte_marker = "Keine LTE Zuordnung"
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-28",
                loco="91515370037-1",
                status="Zugewiesen",
                start=1 * 60 + 31,
                end=2 * 60 + 30,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Inland",
            ),
            _segment(
                day="2026-06-28",
                loco="91515370037-1",
                status="Zugewiesen",
                start=2 * 60 + 30,
                end=2 * 60 + 57,
                event_type="Ausfahrt",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
            ),
            _segment(
                day="2026-06-28",
                loco="91515370037-1",
                status="Außerhalb DE",
                start=2 * 60 + 57,
                end=3 * 60 + 15,
                event_type="Not in the Report",
                report_scope="NOT_IN_REPORT",
                route_type="Kein Bezug",
            ),
            _segment(
                day="2026-06-28",
                loco="91515370037-1",
                status="GAP",
                start=3 * 60 + 20,
                end=3 * 60 + 40,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Inland",
                row_type="GAP",
            ),
            _segment(
                day="2026-06-28",
                loco="91515370037-1",
                status="Zugewiesen",
                start=3 * 60 + 45,
                end=4 * 60,
                event_type="Ausfahrt",
                report_scope="IN_REPORT",
                route_type="Inland",
                holder=no_lte_marker,
                performing_ru=no_lte_marker,
            ),
        ]
    )

    bands = build_loco_visual_bands(segments, visible_from=date(2026, 6, 28))

    assert [band["visual_status"] for band in bands] == [
        "In DE",
        "Ausfahrt",
        "Not in the report",
        "GAP",
        "Keine LTE Zuordnung",
    ]
    assert [band["status"] for band in bands] == [
        "Zugewiesen",
        "Zugewiesen",
        "Außerhalb DE",
        "GAP",
        "Zugewiesen",
    ]
    assert bands[0]["css_class"] == "status-in-de"
    assert bands[1]["css_class"] == "status-exit"
    assert bands[2]["css_class"] == "status-not-in-report"
    assert bands[3]["css_class"] == "status-gap"
    assert bands[4]["css_class"] == "status-no-lte"
    assert bands[0]["css_class"] != "status-outside"
    assert bands[1]["css_class"] != "status-outside"
    assert bands[2]["css_class"] not in {"status-assigned", "status-entry", "status-exit"}
    assert bands[0]["end"] == bands[1]["start"] == 2 * 60 + 30


def test_context_scoped_segments_keep_outside_de_for_de_relevant_loco_only():
    source = pd.DataFrame(
        [
            {
                "loco_no": "91806193933-9",
                "holder_name": "ELL Austria GmbH",
                "performing_ru": "LTE NL - LTE Netherlands B.V.",
                "row_type": "MOVEMENT",
                "report_scope": "IN_REPORT",
                "cal_route_type_home": "Inland",
                "de_event_label": "In DE",
                "period_start_utc": "2026-06-25T09:52:00Z",
                "period_end_utc": "2026-06-27T22:10:00Z",
            },
            {
                "loco_no": "91806193933-9",
                "holder_name": "ELL Austria GmbH",
                "performing_ru": "LTE CZ - LTE Czechia s.r.o.",
                "row_type": "MOVEMENT",
                "report_scope": "IN_REPORT",
                "cal_route_type_home": "Außerhalb DE",
                "de_event_label": "Außerhalb DE",
                "period_start_utc": "2026-06-28T01:00:00Z",
                "period_end_utc": "2026-06-28T02:00:00Z",
            },
            {
                "loco_no": "OUTSIDE-ONLY",
                "holder_name": "External Holder",
                "performing_ru": "External RU",
                "row_type": "MOVEMENT",
                "report_scope": "IN_REPORT",
                "cal_route_type_home": "Außerhalb DE",
                "de_event_label": "Außerhalb DE",
                "period_start_utc": "2026-06-26T01:00:00Z",
                "period_end_utc": "2026-06-26T02:00:00Z",
            },
        ]
    )

    segments = _build_context_scoped_segments(
        source,
        date_from=date(2026, 6, 25),
        date_to=date(2026, 6, 28),
        context_days=1,
    )

    assert set(segments["Loknummer"]) == {"91806193933-9"}
    assert "Außerhalb DE" in set(segments["Status"])
    outside_rows = segments[segments["Status"].eq("Außerhalb DE")]
    assert len(outside_rows) == 1
    assert outside_rows.iloc[0]["Meldetag"] == "2026-06-28"
