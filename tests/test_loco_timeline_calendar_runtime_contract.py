from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from loco_timeline_calendar_runtime_module import (  # noqa: E402
    _build_de_relevance_mask,
    _coerce_selectbox_state,
    build_loco_timeline_segments,
)


def _source_row(
    *,
    report_scope: str | None = "IN_REPORT",
    event_label: str = "In DE",
    route_type: str = "Kein Bezug",
    start: str = "2026-06-29 01:31:00",
    end: str = "2026-06-29 02:30:00",
) -> dict[str, object]:
    row = {
        "loco_no": "91515370037-1",
        "holder_name": "Cargounit",
        "performing_ru": "LTE NL - LTE Netherlands B.V.",
        "row_type": "MOVEMENT",
        "de_event_label": event_label,
        "cal_route_type_home": route_type,
        "period_start_utc": start,
        "period_end_utc": end,
    }
    if report_scope is not None:
        row["report_scope"] = report_scope
    return row


def _segments_for(row: dict[str, object]) -> pd.DataFrame:
    return build_loco_timeline_segments(
        pd.DataFrame([row]),
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
        context_days=0,
    )


def test_in_report_in_de_event_wins_over_route_no_reference():
    segments = _segments_for(_source_row(event_label="In DE", route_type="Kein Bezug"))

    assert len(segments) == 1
    assert segments.iloc[0]["Event Type"] == "In DE"
    assert segments.iloc[0]["Route Type"] == "Kein Bezug"
    assert segments.iloc[0]["Status"] != "Außerhalb DE"
    assert segments.iloc[0]["StartMinute"] == 91
    assert segments.iloc[0]["EndMinute"] == 150


def test_in_report_exit_event_wins_over_route_no_reference():
    segments = _segments_for(
        _source_row(
            event_label="Ausfahrt",
            route_type="Kein Bezug",
            start="2026-06-29 02:30:00",
            end="2026-06-29 02:50:00",
        )
    )

    assert len(segments) == 1
    assert segments.iloc[0]["Event Type"] == "Ausfahrt"
    assert segments.iloc[0]["Route Type"] == "Kein Bezug"
    assert segments.iloc[0]["Status"] != "Außerhalb DE"


def test_not_in_report_stays_not_de_relevant():
    source = pd.DataFrame(
        [
            _source_row(
                report_scope="NOT_IN_REPORT",
                event_label="Not in the Report",
                route_type="Kein Bezug",
            )
        ]
    )

    assert _build_de_relevance_mask(source).tolist() == [False]
    assert _segments_for(source.iloc[0].to_dict()).empty


def test_route_no_reference_without_report_or_positive_event_is_not_de_relevant():
    row = _source_row(report_scope=None, event_label="", route_type="Kein Bezug")
    source = pd.DataFrame([row])

    assert _build_de_relevance_mask(source).tolist() == [False]
    assert _segments_for(row).empty


def test_target_loco_integration_in_report_in_de_route_no_reference():
    source = pd.DataFrame(
        [
            _source_row(
                report_scope="IN_REPORT",
                event_label="In DE",
                route_type="Kein Bezug",
                start="2026-06-29 01:31:00",
                end="2026-06-29 02:30:00",
            )
        ]
    )

    segments = build_loco_timeline_segments(
        source,
        date_from=date(2026, 6, 29),
        date_to=date(2026, 6, 29),
        context_days=0,
    )

    assert len(segments) == 1
    assert segments.iloc[0]["Loknummer"] == "91515370037-1"
    assert segments.iloc[0]["Event Type"] == "In DE"
    assert segments.iloc[0]["Route Type"] == "Kein Bezug"
    assert segments.iloc[0]["Status"] != "Außerhalb DE"


def test_loco_timeline_selectbox_state_resets_stale_filter_value():
    session_state = {"loco_timeline_holder": "Alter Halter"}

    index = _coerce_selectbox_state(
        session_state,
        "loco_timeline_holder",
        ["Alle", "Cargounit"],
    )

    assert index == 0
    assert session_state["loco_timeline_holder"] == "Alle"

    session_state["loco_timeline_holder"] = "Cargounit"
    index = _coerce_selectbox_state(
        session_state,
        "loco_timeline_holder",
        ["Alle", "Cargounit"],
    )

    assert index == 1
    assert session_state["loco_timeline_holder"] == "Cargounit"
