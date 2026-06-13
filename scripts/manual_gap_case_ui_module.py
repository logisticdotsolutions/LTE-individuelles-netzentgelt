from __future__ import annotations

import pandas as pd

from manual_gap_ui_labels import clean, duration_label, duration_minutes


def decorate_case_table(cases: pd.DataFrame) -> pd.DataFrame:
    """Add readable GAP duration and R012 detail texts to correction choices."""
    if cases is None or cases.empty:
        return cases
    result = cases.copy()
    result["gap_duration_minutes"] = pd.NA
    for index, row in result.iterrows():
        rule_id = clean(row.get("rule_id")).upper()
        transport = clean(row.get("transport_number")) or "-"
        loco = clean(row.get("loco_no")) or "-"
        start = clean(row.get("period_start_utc")) or "-"
        end = clean(row.get("period_end_utc")) or "-"
        if rule_id == "GAP":
            minutes = duration_minutes(row.get("period_start_utc"), row.get("period_end_utc"))
            result.at[index, "gap_duration_minutes"] = minutes
            result.at[index, "case_label"] = (
                f"GAP – Unterbrechung in der Lok-Zeitachse | Dauer: "
                f"{duration_label(row.get('period_start_utc'), row.get('period_end_utc'))} "
                f"| Lok {loco} | {start} bis {end}"
            )
        elif rule_id in {"R012", "R12"}:
            result.at[index, "case_label"] = (
                f"R012 – Loknummer fehlt oder ist technisch | Transport {transport} "
                f"| Lok {loco} | Zeitpunkt {start}"
            )
    return result


def decorate_context_table(context: pd.DataFrame, case: dict[str, object]) -> pd.DataFrame:
    """Show the GAP duration as an explicit context row before saving."""
    if context is None or context.empty:
        return context
    if clean(case.get("rule_id")).upper() != "GAP":
        return context
    extra = pd.DataFrame(
        [
            {
                "Angabe": "GAP-Dauer",
                "Aktueller Kontext": duration_label(
                    case.get("period_start_utc"),
                    case.get("period_end_utc"),
                ),
            }
        ]
    )
    return pd.concat([context, extra], ignore_index=True)
