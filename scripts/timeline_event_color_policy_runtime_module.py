from __future__ import annotations

from typing import Callable

import pandas as pd

import loco_timeline_calendar_runtime_module as timeline
import no_lte_assignment_policy_runtime_module as no_lte_policy

TIMELINE_EVENT_COLOR_POLICY_MARKER = "NETZENTGELT_TIMELINE_EVENT_COLOR_POLICY_V1_20260701"


def _text_series(source_df: pd.DataFrame, column: str | None, fallback: str = "") -> pd.Series:
    if not column or column not in source_df.columns:
        return pd.Series(fallback, index=source_df.index, dtype="object")
    return source_df[column].fillna("").astype(str).str.strip()


def _row_has_no_lte_marker(row: pd.Series, columns: list[str | None]) -> bool:
    values = []
    for column in columns:
        if not column or column not in row.index:
            continue
        value = row.get(column, "")
        if pd.isna(value):
            value = ""
        values.append(str(value).strip())
    return no_lte_policy.is_no_lte_assignment_marker(*values)


def build_event_aware_de_relevance_mask(source_df: pd.DataFrame) -> pd.Series:
    """
    DE-Relevanz fuer die Lok-Zeitachse.

    Wichtig: Route Type = "Kein Bezug" darf ein explizites DE-Event nicht grau
    ueberschreiben. Beispiel: Event Type = In DE/Ausfahrt bleibt DE-relevant,
    auch wenn cal_route_type_home technisch "Kein Bezug" liefert.
    """
    if source_df.empty:
        return pd.Series(False, index=source_df.index, dtype=bool)

    report_scope_col = timeline._column(source_df, ["report_scope"])
    event_label_col = timeline._column(source_df, timeline.EVENT_LABEL_COLUMNS)
    route_type_col = timeline._column(source_df, timeline.ROUTE_TYPE_COLUMNS)
    holder_col = timeline._column(source_df, timeline.HOLDER_COLUMNS)
    performing_col = timeline._column(source_df, timeline.PERFORMING_RU_COLUMNS)
    rule_col = timeline._column(source_df, timeline.RULE_COLUMNS)
    message_col = timeline._column(source_df, ["dq_message", *timeline.MESSAGE_COLUMNS])
    decision_col = timeline._column(source_df, timeline.DECISION_COLUMNS)

    masks: list[pd.Series] = []
    hard_outside = pd.Series(False, index=source_df.index, dtype=bool)
    event_positive = pd.Series(False, index=source_df.index, dtype=bool)

    if report_scope_col:
        report_values = _text_series(source_df, report_scope_col)
        report_in_scope = report_values.str.upper().eq("IN_REPORT")
        masks.append(report_in_scope)
        hard_outside = hard_outside | report_values.apply(no_lte_policy.is_outside_report_marker)

    if event_label_col:
        event_values = _text_series(source_df, event_label_col)
        event_upper = event_values.str.upper()
        event_positive = event_upper.isin(timeline.DE_EVENT_LABELS)
        event_non_de = event_values.apply(
            lambda value: timeline._contains_any(value, timeline.NON_DE_KEYWORDS)
            or no_lte_policy.is_outside_report_marker(value)
        )
        masks.append(event_positive)
        hard_outside = hard_outside | (event_non_de & ~event_positive)

    if route_type_col:
        route_values = _text_series(source_df, route_type_col)
        route_positive = route_values.apply(lambda value: timeline._contains_any(value, timeline.DE_ROUTE_KEYWORDS))
        route_non_de = route_values.apply(lambda value: timeline._contains_any(value, timeline.NON_DE_KEYWORDS))
        masks.append(route_positive & ~route_non_de)
        # Route "Kein Bezug" ist nur dann hart ausserhalb, wenn kein explizites DE-Event vorliegt.
        hard_outside = hard_outside | ((route_non_de | route_values.apply(no_lte_policy.is_outside_report_marker)) & ~event_positive)

    marker_columns = [holder_col, performing_col, rule_col, message_col, decision_col, event_label_col, route_type_col]
    hard_outside = hard_outside | source_df.apply(lambda row: _row_has_no_lte_marker(row, marker_columns), axis=1)

    if not masks:
        positive = pd.Series(True, index=source_df.index, dtype=bool)
    else:
        positive = masks[0]
        for mask in masks[1:]:
            positive = positive | mask

    return (positive & ~hard_outside).fillna(False).astype(bool)


def install_timeline_event_color_policy_runtime() -> Callable | None:
    """Patch the no-LTE timeline builder to use event-aware DE relevance."""
    original = getattr(no_lte_policy, "_source_de_relevance_mask", None)
    if getattr(original, "_timeline_event_color_policy_installed", False):
        return original

    build_event_aware_de_relevance_mask._timeline_event_color_policy_installed = True
    build_event_aware_de_relevance_mask._timeline_event_color_policy_original = original
    no_lte_policy._source_de_relevance_mask = build_event_aware_de_relevance_mask
    return original


def restore_timeline_event_color_policy_runtime(original: Callable | None) -> None:
    if original is None:
        return
    no_lte_policy._source_de_relevance_mask = original
