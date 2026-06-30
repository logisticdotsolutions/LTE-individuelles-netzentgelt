from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline

STRICT_ROUTE_TYPE_KEYWORDS = (
    "inland",
    "einfahrt",
    "ausfahrt",
    "passiert",
    "komplex",
)
EXCLUDED_ROUTE_TYPE_KEYWORDS = (
    "außerhalb",
    "ausserhalb",
    "ausland",
    "kein bezug",
    "no de",
)


def _normalized_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.casefold()


def build_strict_de_relevance_mask(source_df: pd.DataFrame) -> pd.Series:
    """Return a strict DE relevance mask for deciding whether a loco enters the timeline."""
    if source_df.empty:
        return pd.Series(False, index=source_df.index, dtype=bool)

    masks: list[pd.Series] = []
    report_scope_col = timeline._column(source_df, ["report_scope"])
    event_label_col = timeline._column(source_df, timeline.EVENT_LABEL_COLUMNS)
    route_type_col = timeline._column(source_df, timeline.ROUTE_TYPE_COLUMNS)

    if report_scope_col:
        scope_values = _normalized_text(source_df[report_scope_col])
        masks.append(scope_values.isin({"in_report", "de", "home", "in home"}))

    if event_label_col:
        event_values = source_df[event_label_col].fillna("").astype(str).str.strip().str.upper()
        masks.append(event_values.isin(timeline.DE_EVENT_LABELS))

    if route_type_col:
        route_values = _normalized_text(source_df[route_type_col])
        route_positive = route_values.apply(
            lambda value: any(keyword in value for keyword in STRICT_ROUTE_TYPE_KEYWORDS)
        )
        route_excluded = route_values.apply(
            lambda value: any(keyword in value for keyword in EXCLUDED_ROUTE_TYPE_KEYWORDS)
        )
        masks.append(route_positive & ~route_excluded)

    if not masks:
        return pd.Series(True, index=source_df.index, dtype=bool)

    result = masks[0]
    for mask in masks[1:]:
        result = result | mask
    return result.fillna(False).astype(bool)


def filter_loco_timeline_source_for_de_scope(
    source_df: pd.DataFrame,
    *,
    date_from: date,
    date_to: date,
) -> pd.DataFrame:
    """Keep only locos that have real DE relevance inside the selected user period."""
    if source_df.empty:
        return source_df.copy()

    date_from, date_to = timeline._normalize_day_range(date_from, date_to)
    filter_start = pd.Timestamp(date_from, tz="UTC")
    filter_end = pd.Timestamp(date_to + timedelta(days=1), tz="UTC")

    loco_col = timeline._column(source_df, timeline.LOCO_COLUMNS)
    if not loco_col:
        return source_df.iloc[0:0].copy()

    start_ts = timeline._coalesced_timestamp(source_df, timeline.START_TIME_COLUMNS)
    end_ts = timeline._coalesced_timestamp(source_df, timeline.END_TIME_COLUMNS)
    fallback_end = start_ts + pd.Timedelta(minutes=15)
    end_ts = end_ts.fillna(fallback_end)
    invalid_end_mask = start_ts.notna() & (end_ts <= start_ts)
    end_ts.loc[invalid_end_mask] = start_ts.loc[invalid_end_mask] + pd.Timedelta(minutes=15)

    actual_period_overlap = start_ts.notna() & end_ts.gt(filter_start) & start_ts.lt(filter_end)
    de_relevant = build_strict_de_relevance_mask(source_df)
    loco_values = source_df[loco_col].fillna("").astype(str).str.strip()
    valid_loco_values = set(
        loco_values.loc[
            actual_period_overlap & de_relevant & loco_values.ne("") & loco_values.ne("00000000000-0")
        ].tolist()
    )
    if not valid_loco_values:
        return source_df.iloc[0:0].copy()

    return source_df.loc[loco_values.isin(valid_loco_values)].copy()


def install_loco_timeline_de_scope_runtime() -> Callable | None:
    """Patch timeline segment builders so context is shown only for DE-relevant locos."""
    original_builder = timeline.build_loco_timeline_segments
    if getattr(original_builder, "_loco_timeline_de_scope_installed", False):
        return original_builder

    def scoped_builder(
        source_df: pd.DataFrame,
        *,
        date_from: date,
        date_to: date,
        context_days: int = 1,
    ) -> pd.DataFrame:
        scoped_source = filter_loco_timeline_source_for_de_scope(
            source_df,
            date_from=date_from,
            date_to=date_to,
        )
        return original_builder(
            scoped_source,
            date_from=date_from,
            date_to=date_to,
            context_days=context_days,
        )

    scoped_builder._loco_timeline_de_scope_installed = True
    scoped_builder._loco_timeline_de_scope_original = original_builder
    timeline.build_loco_timeline_segments = scoped_builder

    try:
        import loco_timeline_review_queue_runtime_module as review_queue_runtime

        review_queue_runtime.build_loco_timeline_segments = scoped_builder
    except Exception:
        pass

    return original_builder


def restore_loco_timeline_de_scope_runtime(original_builder: Callable | None) -> None:
    if original_builder is None:
        return
    timeline.build_loco_timeline_segments = original_builder
    try:
        import loco_timeline_review_queue_runtime_module as review_queue_runtime

        review_queue_runtime.build_loco_timeline_segments = original_builder
    except Exception:
        pass
