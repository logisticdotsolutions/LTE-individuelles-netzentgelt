from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from loco_timeline_context_scope_runtime_module import _build_context_scoped_segments  # noqa: E402
from loco_timeline_visual_band_runtime_module import (  # noqa: E402
    _fill_visual_band_gaps,
    build_loco_multiday_axis_html_with_visual_bands,
    build_loco_visual_bands,
)


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
    de_event_label: str = "",
    cal_route_type_home: str = "",
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
        "de_event_label": de_event_label,
        "cal_route_type_home": cal_route_type_home,
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
        "Ausfahrt",
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
    assert bands[4]["css_class"] == "status-exit"
    assert bands[0]["css_class"] != "status-outside"
    assert bands[1]["css_class"] != "status-outside"
    assert bands[2]["css_class"] not in {"status-assigned", "status-entry", "status-exit"}
    assert bands[0]["end"] == bands[1]["start"] == 2 * 60 + 30


def _single_visual_band(**segment_kwargs) -> dict[str, object]:
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                start=60,
                end=90,
                **segment_kwargs,
            )
        ]
    )
    bands = build_loco_visual_bands(segments, visible_from=date(2026, 6, 29))

    assert len(bands) == 1
    return bands[0]


def _filled_visual_bands(
    segments: pd.DataFrame,
    *,
    visible_from: date,
    date_from: date,
    date_to: date,
    visible_end_minute: int = 24 * 60,
) -> list[dict[str, object]]:
    return _fill_visual_band_gaps(
        build_loco_visual_bands(segments, visible_from=visible_from),
        visible_start_minute=0,
        visible_end_minute=visible_end_minute,
        visible_from=visible_from,
        date_from=date_from,
        date_to=date_to,
    )


def _assert_gapless(bands: list[dict[str, object]], start_minute: int, end_minute: int) -> None:
    assert bands
    assert bands[0]["start"] == start_minute
    assert bands[-1]["end"] == end_minute
    for previous, current in zip(bands, bands[1:]):
        assert previous["end"] == current["start"]
        assert previous["end"] >= previous["start"]
    assert bands[-1]["end"] >= bands[-1]["start"]


def test_event_exit_wins_over_route_no_reference():
    band = _single_visual_band(
        status="Außerhalb DE",
        route_type="Kein Bezug",
        event_type="Ausfahrt",
    )

    assert band["visual_status"] == "Ausfahrt"
    assert band["css_class"] == "status-exit"


def test_event_in_de_wins_over_route_no_reference():
    band = _single_visual_band(
        status="Außerhalb DE",
        route_type="Kein Bezug",
        event_type="In DE",
    )

    assert band["visual_status"] == "In DE"
    assert band["css_class"] == "status-in-de"


def test_de_event_label_exit_wins_over_cal_route_no_reference():
    band = _single_visual_band(
        status="Außerhalb DE",
        cal_route_type_home="Kein Bezug",
        de_event_label="Ausfahrt",
    )

    assert band["visual_status"] == "Ausfahrt"
    assert band["css_class"] == "status-exit"


def test_hard_not_in_report_row_stays_dark():
    band = _single_visual_band(
        status="Außerhalb DE",
        event_type="Not in the report",
        row_type="NOT_IN_REPORT",
    )

    assert band["visual_status"] == "Not in the report"
    assert band["css_class"] == "status-not-in-report"


def test_gap_stays_gap_over_event_and_route_fallback():
    band = _single_visual_band(
        status="GAP",
        route_type="Kein Bezug",
        event_type="Ausfahrt",
    )

    assert band["visual_status"] == "GAP"
    assert band["css_class"] == "status-gap"


def test_no_lte_assignment_stays_gray_without_event_type():
    no_lte_marker = "Keine LTE Zuordnung"
    band = _single_visual_band(
        status="Zugewiesen",
        holder=no_lte_marker,
        performing_ru=no_lte_marker,
    )

    assert band["visual_status"] == "Keine LTE Zuordnung"
    assert band["css_class"] == "status-no-lte"


def test_filled_visual_bands_cover_full_day_around_single_in_de_event():
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                status="Zugewiesen",
                start=1 * 60 + 31,
                end=2 * 60 + 30,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
            )
        ]
    )

    bands = _filled_visual_bands(
        segments,
        visible_from=date(2026, 6, 29),
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
    )

    _assert_gapless(bands, 0, 24 * 60)
    assert [band["visual_status"] for band in bands] == [
        "Keine LTE Zuordnung",
        "In DE",
        "Keine LTE Zuordnung",
    ]
    assert bands[0]["end"] == bands[1]["start"] == 1 * 60 + 31
    assert bands[1]["end"] == bands[2]["start"] == 2 * 60 + 30
    assert bands[1]["css_class"] == "status-in-de"


def test_filled_visual_bands_preserve_adjacent_in_de_and_exit_without_gap_status():
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                status="Zugewiesen",
                start=1 * 60 + 31,
                end=2 * 60 + 30,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
            ),
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                status="Zugewiesen",
                start=2 * 60 + 30,
                end=2 * 60 + 50,
                event_type="Ausfahrt",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
            ),
        ]
    )

    bands = _filled_visual_bands(
        segments,
        visible_from=date(2026, 6, 29),
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
    )

    _assert_gapless(bands, 0, 24 * 60)
    assert [band["visual_status"] for band in bands] == [
        "Keine LTE Zuordnung",
        "In DE",
        "Ausfahrt",
        "Keine LTE Zuordnung",
    ]
    assert bands[2]["css_class"] == "status-exit"
    assert "GAP" not in [band["visual_status"] for band in bands]


def test_filled_visual_bands_do_not_convert_true_gap_segments():
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                status="GAP",
                start=0,
                end=6 * 60,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
                row_type="GAP",
            )
        ]
    )

    bands = _filled_visual_bands(
        segments,
        visible_from=date(2026, 6, 29),
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
    )

    _assert_gapless(bands, 0, 24 * 60)
    assert bands[0]["visual_status"] == "GAP"
    assert bands[0]["css_class"] == "status-gap"
    assert bands[0]["end"] == 6 * 60
    assert bands[1]["visual_status"] == "Keine LTE Zuordnung"


def test_filled_visual_bands_cover_multiday_context_with_muted_context_fill():
    segments = pd.DataFrame(
        [
            _segment(
                day="2026-06-29",
                loco="91515370037-1",
                status="Zugewiesen",
                start=1 * 60 + 31,
                end=2 * 60 + 30,
                event_type="In DE",
                report_scope="IN_REPORT",
                route_type="Kein Bezug",
            )
        ]
    )

    bands = _filled_visual_bands(
        segments,
        visible_from=date(2026, 6, 28),
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
        visible_end_minute=3 * 24 * 60,
    )
    html = build_loco_multiday_axis_html_with_visual_bands(
        segments,
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
        context_days=1,
    )

    _assert_gapless(bands, 0, 3 * 24 * 60)
    assert bands[0]["start"] == 0
    assert bands[0]["end"] == 24 * 60
    assert bands[0]["visual_status"] == "Not in the report"
    assert bands[0]["in_filter"] is False
    assert any(
        band["visual_status"] == "Keine LTE Zuordnung" and band["in_filter"] is True
        for band in bands
    )
    assert bands[-1]["visual_status"] == "Not in the report"
    assert bands[-1]["in_filter"] is False
    assert 'data-visual-status="Not in the report"' in html
    assert "context-muted" in html


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
