from __future__ import annotations

from collections import OrderedDict

import pandas as pd


GATE_DETAIL_RUNTIME_MARKER = "NETZENTGELT_OPERATOR_GATE_DETAIL_PHASE11O_V1_20260618"
BUSINESS_WORKBASKET_MARKER = "NETZENTGELT_OPERATOR_WORKBASKETS_PHASE11Q_V1_20260619"


def _empty_business_baskets() -> OrderedDict[str, pd.DataFrame]:
    return OrderedDict(
        [
            ("Fehler in Lokbewegung", pd.DataFrame()),
            ("Fehlende Loknummer / Dummylok", pd.DataFrame()),
        ]
    )


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _deduplicate(table: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if table is None or table.empty:
        return table
    existing = [column for column in columns if column in table.columns]
    if not existing:
        return table.reset_index(drop=True)
    return table.drop_duplicates(subset=existing, keep="first").reset_index(drop=True)


def _missing_loco_blockers(operator_ui, global_export_blockers: pd.DataFrame | None) -> pd.DataFrame:
    if global_export_blockers is None or global_export_blockers.empty:
        return operator_ui._friendly_global_blockers(global_export_blockers)

    work = global_export_blockers.copy()
    rule_col = operator_ui._column(work, ["rule_id", "rule"])
    message_col = operator_ui._column(work, ["message", "problem", "gate_reason"])
    row_type_col = operator_ui._column(work, ["row_type"])

    rule = work[rule_col].fillna("").astype(str).str.strip().str.upper() if rule_col else pd.Series("", index=work.index)
    message = work[message_col].fillna("").astype(str).str.strip().str.lower() if message_col else pd.Series("", index=work.index)
    row_type = work[row_type_col].fillna("").astype(str).str.strip().str.upper() if row_type_col else pd.Series("", index=work.index)

    mask = (
        rule.eq("R012")
        | row_type.eq("RAW_DUMMY_LOCOMOTIVE")
        | message.str.contains("dummy", regex=False)
        | message.str.contains("dummylok", regex=False)
        | message.str.contains("loknummer", regex=False)
        | message.str.contains("locomotive", regex=False)
    )
    return operator_ui._friendly_global_blockers(work[mask].copy())


def build_business_workbaskets(
    export_gate: pd.DataFrame | None,
    global_export_blockers: pd.DataFrame | None,
    findings: pd.DataFrame | None,
) -> OrderedDict[str, pd.DataFrame]:
    """Build the two business-facing work baskets without hint or technical side lists."""
    import operator_ui_module as operator_ui

    baskets = _empty_business_baskets()
    movement_errors = operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)
    missing_loco = _missing_loco_blockers(operator_ui, global_export_blockers)

    if movement_errors is not None and not movement_errors.empty and "Warum?" in movement_errors.columns:
        problem_text = movement_errors["Warum?"].fillna("").astype(str).str.lower()
        movement_errors = movement_errors[
            ~(
                problem_text.str.contains("dummy", regex=False)
                | problem_text.str.contains("loknummer fehlt", regex=False)
                | problem_text.str.contains("fehlende loknummer", regex=False)
            )
        ].copy()

    baskets["Fehler in Lokbewegung"] = _deduplicate(
        movement_errors,
        ["Loknummer", "Datum", "Nutzendes EVU", "Warum?"],
    )
    baskets["Fehlende Loknummer / Dummylok"] = _deduplicate(
        missing_loco,
        ["Datum", "Problem", "Transportnummer", "Nutzendes EVU"],
    )
    return baskets


def install_operator_gate_detail_runtime() -> None:
    """Show concrete finding reasons in the open-task gate table and simplify baskets."""
    import operator_ui_module as operator_ui
    from export_and_loco_check_runtime_module import install_export_and_loco_check_runtime
    from railverk_branding_runtime_module import install_railverk_branding_runtime

    install_export_and_loco_check_runtime()
    install_railverk_branding_runtime()

    if getattr(operator_ui, "_PHASE11O_GATE_DETAIL_PATCHED", False):
        if not getattr(operator_ui, "_PHASE11Q_BUSINESS_WORKBASKETS_PATCHED", False):
            operator_ui.render_open_tasks = _build_patched_render_open_tasks(operator_ui)
            operator_ui.build_business_workbaskets = build_business_workbaskets
            operator_ui._PHASE11Q_BUSINESS_WORKBASKETS_PATCHED = True
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
            result.loc[r011_mask, "Auswirkung"] = "Export gesperrt nur bei anderem EVU"
        return result

    operator_ui._friendly_gate_table = patched_friendly_gate_table
    operator_ui._friendly_findings = patched_friendly_findings
    operator_ui.render_open_tasks = _build_patched_render_open_tasks(operator_ui)
    operator_ui.build_business_workbaskets = build_business_workbaskets
    operator_ui._PHASE11O_GATE_DETAIL_PATCHED = True
    operator_ui._PHASE11Q_BUSINESS_WORKBASKETS_PATCHED = True


def _build_patched_render_open_tasks(operator_ui):
    def patched_render_open_tasks(
        export_gate: pd.DataFrame,
        global_export_blockers: pd.DataFrame,
        findings: pd.DataFrame,
    ) -> None:
        st = operator_ui.st
        st.subheader("Offene Aufgaben")
        st.caption(
            "Diese Ansicht zeigt nur fachliche Arbeitskoerbe. Hinweise und technische Nebenlisten sind bewusst ausgeblendet."
        )

        baskets = build_business_workbaskets(
            export_gate=export_gate,
            global_export_blockers=global_export_blockers,
            findings=findings,
        )
        movement_errors = baskets["Fehler in Lokbewegung"]
        missing_loco = baskets["Fehlende Loknummer / Dummylok"]

        tab_movements, tab_loco = st.tabs(
            [
                f"Fehler in Lokbewegung ({len(movement_errors)})",
                f"Fehlende Loknummer / Dummylok ({len(missing_loco)})",
            ]
        )

        with tab_movements:
            if movement_errors.empty:
                st.success("Keine fachlichen Fehler in Lokbewegungen offen.")
            else:
                st.dataframe(movement_errors, use_container_width=True, hide_index=True)
                operator_ui._render_loco_shortcut(movement_errors, key_suffix="business_movement")

        with tab_loco:
            if missing_loco.empty:
                st.success("Keine fehlenden Loknummern oder Dummy-Loks offen.")
            else:
                st.dataframe(missing_loco, use_container_width=True, hide_index=True)

        combined_parts = []
        for basket_name, table in baskets.items():
            if table is None or table.empty:
                continue
            export_table = table.copy()
            export_table.insert(0, "Arbeitskorb", basket_name)
            combined_parts.append(export_table)
        if combined_parts:
            csv = pd.concat(combined_parts, ignore_index=True).to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Arbeitsliste als CSV herunterladen",
                data=csv,
                file_name="offene_aufgaben_fachlich.csv",
                mime="text/csv",
                key="download_operator_business_tasks_csv",
            )

    return patched_render_open_tasks
