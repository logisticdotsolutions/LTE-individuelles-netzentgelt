from __future__ import annotations

from collections import OrderedDict

import pandas as pd


GATE_DETAIL_RUNTIME_MARKER = "NETZENTGELT_OPERATOR_GATE_DETAIL_PHASE11O_V1_20260618"


def install_operator_gate_detail_runtime() -> None:
    """Show concrete finding reasons in the open-task gate table."""
    import operator_ui_module as operator_ui

    if getattr(operator_ui, "_PHASE11O_GATE_DETAIL_PATCHED", False):
        return

    original_friendly_gate_table = operator_ui._friendly_gate_table
    original_friendly_findings = operator_ui._friendly_findings

    def _clean(value: object) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()

    def _date_text(value: object) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%d.%m.%Y")

    def _rule_columns(findings: pd.DataFrame | None) -> dict[str, str | None]:
        if findings is None or findings.empty:
            return {}
        return {
            "severity": operator_ui._column(findings, ["severity"]),
            "rule": operator_ui._column(findings, ["rule_id", "rule"]),
            "loco": operator_ui._column(findings, ["loco_no"]),
            "transport": operator_ui._column(findings, ["transport_number"]),
            "ru": operator_ui._column(findings, ["performing_ru"]),
            "start": operator_ui._column(findings, ["period_start_utc"]),
            "end": operator_ui._column(findings, ["period_end_utc"]),
            "message": operator_ui._column(findings, ["message"]),
        }

    def _finding_date(row: pd.Series, start_col: str | None, end_col: str | None) -> str:
        for column in [start_col, end_col]:
            if column and _clean(row.get(column)):
                text = _date_text(row.get(column))
                if text:
                    return text
        return ""

    def _details_for_loco_day(findings: pd.DataFrame | None, loco_no: str, date_text: str, *, gate_overlap_minutes: int = 0) -> tuple[str, str]:
        if findings is None or findings.empty or not loco_no or not date_text:
            return "", ""
        cols = _rule_columns(findings)
        required = [cols.get("severity"), cols.get("rule"), cols.get("loco")]
        if any(column is None for column in required):
            return "", ""

        work = findings.copy()
        severity = work[cols["severity"]].fillna("").astype(str).str.strip().str.upper()
        loco = work[cols["loco"]].fillna("").astype(str).str.strip()
        rules = work[cols["rule"]].fillna("").astype(str).str.strip().str.upper()
        row_dates = work.apply(lambda row: _finding_date(row, cols.get("start"), cols.get("end")), axis=1)
        mask = loco.eq(loco_no) & row_dates.eq(date_text) & severity.isin(["ERROR", "MANUAL_REVIEW"])
        day_findings = work[mask].copy()
        if day_findings.empty:
            return "", ""

        # Same-EVU overlaps may still exist in an old DB before the recalculation. If the gate already has
        # zero relevant overlap minutes, do not show R011 as the visible blocking reason.
        if gate_overlap_minutes <= 0:
            day_findings = day_findings[~rules[mask].eq("R011")].copy()
        if day_findings.empty:
            return "", ""

        reasons: OrderedDict[str, None] = OrderedDict()
        actions: OrderedDict[str, None] = OrderedDict()
        for _, row in day_findings.iterrows():
            rule = _clean(row.get(cols["rule"])).upper()
            message = _clean(row.get(cols.get("message"))) if cols.get("message") else ""
            problem, action = operator_ui._friendly_rule(rule, message)
            transport = _clean(row.get(cols.get("transport"))) if cols.get("transport") else ""
            ru = _clean(row.get(cols.get("ru"))) if cols.get("ru") else ""
            suffix_parts = []
            if rule:
                suffix_parts.append(rule)
            if transport:
                suffix_parts.append(f"Transport {transport}")
            if ru:
                suffix_parts.append(ru)
            label = problem if not suffix_parts else problem + " (" + ", ".join(suffix_parts) + ")"
            reasons[label] = None
            actions[action] = None

        return " | ".join(reasons.keys()), " | ".join(actions.keys())

    def patched_friendly_gate_table(export_gate, only_status=None, findings=None):
        result = original_friendly_gate_table(export_gate, only_status=only_status, findings=findings)
        if result is None or result.empty:
            return result

        for index, row in result.iterrows():
            loco_no = _clean(row.get("Loknummer"))
            date_text = _clean(row.get("Datum"))
            overlap_minutes = 0
            try:
                overlap_minutes = int(row.get("Ueberschneidungsminuten") or 0)
            except (TypeError, ValueError):
                overlap_minutes = 0
            details, next_step = _details_for_loco_day(
                findings,
                loco_no,
                date_text,
                gate_overlap_minutes=overlap_minutes,
            )
            if details:
                result.at[index, "Warum?"] = details
            if next_step:
                result.at[index, "Naechster Schritt"] = next_step
            if _clean(row.get("Status")).startswith("⛔") and _clean(row.get("Zeitliche Abdeckung")).startswith("100"):
                result.at[index, "Zeitliche Abdeckung"] = "100 % Zeitkette, aber Pflichtdaten/Prueffall offen"

        return result

    def patched_friendly_findings(findings: pd.DataFrame, include_info: bool = True) -> pd.DataFrame:
        result = original_friendly_findings(findings, include_info=include_info)
        if result is None or result.empty:
            return result
        if "Regel" in result.columns and "Auswirkung" in result.columns:
            r011_mask = result["Regel"].fillna("").astype(str).str.strip().str.upper().eq("R011")
            # R011 shown after recalculation should be only different-EVU. Make the impact text explicit.
            result.loc[r011_mask, "Auswirkung"] = "Export gesperrt nur bei anderem EVU"
        return result

    operator_ui._friendly_gate_table = patched_friendly_gate_table
    operator_ui._friendly_findings = patched_friendly_findings
    operator_ui._PHASE11O_GATE_DETAIL_PATCHED = True
