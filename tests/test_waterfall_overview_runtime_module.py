from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import waterfall_overview_runtime_module as module  # noqa: E402


def test_waterfall_overview_is_gap_free_and_de_filtered() -> None:
    source = pd.DataFrame([
        {"row_type": "MOVEMENT", "report_scope": "IN_REPORT", "de_event_label": "In DE", "loco_no": "91801234567-8", "holder_name": "LTE Holding", "performing_ru": "LTE DE", "transport_number": "T-1", "cal_route_type_home": "Inland", "period_start_utc": "2026-06-28T08:00:00Z", "period_end_utc": "2026-06-28T09:00:00Z"},
        {"row_type": "MOVEMENT", "report_scope": "IN_REPORT", "de_event_label": "Einfahrt", "loco_no": "91801234567-8", "holder_name": "LTE Holding", "performing_ru": "LTE DE", "transport_number": "T-2", "cal_route_type_home": "Einfahrt", "period_start_utc": "2026-06-28T10:00:00Z", "period_end_utc": "2026-06-28T11:00:00Z"},
        {"row_type": "MOVEMENT", "report_scope": "IN_REPORT", "de_event_label": "Ausfahrt", "loco_no": "91807654321-0", "holder_name": "Extern Holder", "performing_ru": "LTE NL", "transport_number": "T-3", "cal_route_type_home": "Ausfahrt", "period_start_utc": "2026-06-28T12:00:00Z", "period_end_utc": "2026-06-28T13:00:00Z"},
        {"row_type": "GAP", "report_scope": "IN_REPORT", "de_event_label": "In DE", "loco_no": "91809999999-9", "holder_name": "LTE Holding", "performing_ru": "LTE DE", "transport_number": "", "cal_route_type_home": "Inland", "period_start_utc": "2026-06-28T14:00:00Z", "period_end_utc": "2026-06-28T15:00:00Z"},
        {"row_type": "MOVEMENT", "report_scope": "NOT_IN_REPORT", "de_event_label": "", "loco_no": "91808888888-8", "holder_name": "Foreign", "performing_ru": "Foreign RU", "transport_number": "T-4", "cal_route_type_home": "Kein Bezug", "period_start_utc": "2026-06-28T16:00:00Z", "period_end_utc": "2026-06-28T17:00:00Z"},
        {"row_type": "MOVEMENT", "report_scope": "IN_REPORT", "de_event_label": "In DE", "loco_no": "00000000000-0", "holder_name": "Dummy", "performing_ru": "LTE DE", "transport_number": "T-5", "cal_route_type_home": "Inland", "period_start_utc": "2026-06-28T18:00:00Z", "period_end_utc": "2026-06-28T19:00:00Z"},
    ])

    overview = module.build_waterfall_loco_overview(source, date_from=date(2026, 6, 28), date_to=date(2026, 6, 28))

    assert overview["Loknummer"].tolist() == ["91801234567-8", "91807654321-0"]
    assert overview["Bewegungen"].tolist() == [2, 1]
    assert overview.loc[overview["Loknummer"].eq("91801234567-8"), "Transporte"].iloc[0] == 2

    filtered = module.filter_waterfall_overview(
        overview,
        holder="LTE Holding",
        performing_ru="LTE DE",
        route_type="Inland",
        loco_query="1234567",
    )
    assert filtered["Loknummer"].tolist() == ["91801234567-8"]
