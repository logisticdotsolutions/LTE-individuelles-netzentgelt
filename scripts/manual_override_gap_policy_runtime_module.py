from __future__ import annotations


GAP_POLICY_UI_LABEL_MARKER = "NETZENTGELT_GAP_POLICY_UI_LABELS_20260618"


def install_gap_policy_labels() -> None:
    """Register labels and enforce the operator GAP proposal matrix."""
    import re
    import pandas as pd
    import manual_override_suggestion_module as suggestion_module
    import manual_override_ui_module as override_ui

    override_ui.CLASSIFICATION_OPTIONS.setdefault("NO_LTE_ASSIGNMENT", "Keine LTE-Zuweisung / nicht im Report")
    override_ui.SUGGESTION_TYPE_LABELS.update({
        "GAP_NO_LTE_ASSIGNMENT": "Keine LTE-Zuweisung / nicht im Report",
        "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "EVU aus direkter GAP-Umgebung übernehmen",
        "POSSIBLE_COLD_STAND_SAME_LOCATION": "Kaltabstellung prüfen",
    })

    if getattr(suggestion_module, "_PHASE11M_GAP_MATRIX_PATCHED", False):
        override_ui.build_suggestion_table = suggestion_module.build_suggestion_table
        return

    original_build_suggestion_table = suggestion_module.build_suggestion_table

    def clean(value: object) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()

    def ts(value: object):
        parsed = pd.to_datetime(value, errors="coerce")
        return None if pd.isna(parsed) else pd.Timestamp(parsed)

    def ts_text(value: object) -> str:
        parsed = ts(value)
        return "" if parsed is None else parsed.strftime("%Y-%m-%dT%H:%M:%S")

    def loc_key(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", clean(value).lower())

    def is_jump(before: str, after: str) -> bool:
        return bool(before and after and loc_key(before) != loc_key(after))

    def mk(kind: str, code: str, value: str, confidence: str, reason: str, evidence: str, common: dict[str, str]):
        return suggestion_module._new_suggestion(
            suggestion_type=kind,
            override_type="CLASSIFY_GAP",
            classification_code=code,
            confidence=confidence,
            suggested_value=value,
            reason=reason,
            evidence=evidence,
            **common,
        ).to_dict()

    def classify(duration, known_end: bool, jump: bool, same_ru: str, evidence: str, common: dict[str, str], open_end: bool = False):
        no_value = "Keine LTE-Zuweisung / nicht im Report"
        if jump:
            return mk(
                "GAP_NO_LTE_ASSIGNMENT",
                "NO_LTE_ASSIGNMENT",
                no_value,
                "MEDIUM",
                "Ortsunterbrechung erkannt. Vorschlag: keine Zuweisung / nicht im Report.",
                evidence,
                common,
            )
        if open_end:
            # Offene GAPs bekommen bewusst keinen automatischen fachlichen Vorschlag.
            # Die Mindestdauer wird nur in der Prüfoberfläche angezeigt, damit kein
            # nicht belegter Abschluss der Unterbrechung simuliert wird.
            return None
        if not known_end or duration is None:
            return None
        if duration < 120 and same_ru:
            return mk(
                "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS",
                "SAME_RU_CONTINUITY",
                same_ru,
                "HIGH",
                "GAP kleiner 120 Minuten, durchgehende Ortskette und EVU davor/danach ident. Vorschlag: dieses EVU.",
                evidence,
                common,
            )
        if 120 < duration < 600:
            return mk(
                "POSSIBLE_COLD_STAND_SAME_LOCATION",
                "COLD_STAND",
                "Mögliche kalte Abstellung",
                "MEDIUM",
                "GAP größer 120 und kleiner 600 Minuten, Endzeit bekannt und Ortskette durchgehend. Vorschlag: Kaltabstellung.",
                evidence,
                common,
            )
        if duration > 600:
            return mk(
                "GAP_NO_LTE_ASSIGNMENT",
                "NO_LTE_ASSIGNMENT",
                no_value,
                "MEDIUM",
                "GAP größer 600 Minuten, Endzeit bekannt und Ortskette durchgehend. Vorschlag: keine Zuweisung / nicht im Report.",
                evidence,
                common,
            )
        return None

    def snapshot_from_timeline(timeline):
        values = []
        for column in ["source_snapshot_at_utc", "calculated_at_utc", "error_cutoff_utc", "period_end_utc", "period_start_utc"]:
            if timeline is not None and column in timeline.columns:
                parsed = pd.to_datetime(timeline[column], errors="coerce")
                if not parsed.dropna().empty:
                    values.append(parsed.max())
        return max(values) if values else None

    def movement_rows(timeline):
        if timeline is None or getattr(timeline, "empty", True) or "row_type" not in timeline.columns:
            return []
        movements = timeline[timeline["row_type"].fillna("").astype(str).str.upper().eq("MOVEMENT")].copy()
        if movements.empty:
            return []
        movements["_seq"] = pd.to_numeric(movements.get("sort_sequence", pd.Series(index=movements.index)), errors="coerce")
        movements["_ts"] = pd.to_datetime(movements.get("sequence_ts", movements.get("period_start_utc", "")), errors="coerce")
        movements["_row"] = pd.to_numeric(movements.get("source_row_id", pd.Series(index=movements.index)), errors="coerce")
        snapshot = snapshot_from_timeline(timeline)
        rows = []
        for loco_no, group in movements.groupby("loco_no", dropna=False):
            ordered = group.sort_values(["_seq", "_ts", "_row"], na_position="last").reset_index(drop=True)
            for index in range(len(ordered)):
                before_row = ordered.iloc[index]
                after_row = ordered.iloc[index + 1] if index + 1 < len(ordered) else None
                start = ts(before_row.get("period_end_utc"))
                if start is None:
                    continue
                if after_row is None:
                    if snapshot is None or snapshot <= start:
                        continue
                    duration = float((snapshot - start).total_seconds() / 60.0)
                    common = {
                        "loco_no": clean(loco_no),
                        "transport_number": clean(before_row.get("transport_number")),
                        "period_start_utc": ts_text(start),
                        "period_end_utc": ts_text(snapshot),
                        "source_table": clean(before_row.get("source_table")),
                        "source_row_id": clean(before_row.get("source_row_id")),
                    }
                    evidence = (
                        f"GAP-Dauer: mind. {duration:.0f} Minuten; "
                        f"Ort davor: {clean(before_row.get('destination_name')) or '-'}; "
                        "Ort danach: -; Endzeit bekannt: nein."
                    )
                    suggestion = classify(duration, False, False, "", evidence, common, open_end=True)
                    if suggestion:
                        rows.append(suggestion)
                    continue
                end = ts(after_row.get("period_start_utc"))
                if end is None or end <= start:
                    continue
                duration = float((end - start).total_seconds() / 60.0)
                before_loc = clean(before_row.get("destination_name")) or clean(before_row.get("origin_name"))
                after_loc = clean(after_row.get("origin_name")) or clean(after_row.get("destination_name"))
                before_ru = clean(before_row.get("performing_ru"))
                after_ru = clean(after_row.get("performing_ru"))
                same_ru = before_ru if before_ru and before_ru == after_ru else ""
                common = {
                    "loco_no": clean(loco_no),
                    "transport_number": clean(before_row.get("transport_number")),
                    "period_start_utc": ts_text(start),
                    "period_end_utc": ts_text(end),
                    "source_table": clean(before_row.get("source_table")),
                    "source_row_id": clean(before_row.get("source_row_id")),
                }
                evidence = (
                    f"GAP-Dauer: {duration:.0f} Minuten; Ort davor: {before_loc or '-'}; "
                    f"Ort danach: {after_loc or '-'}; EVU davor/danach: {same_ru or '-'}; "
                    "Endzeit bekannt: ja."
                )
                suggestion = classify(duration, True, is_jump(before_loc, after_loc), same_ru, evidence, common)
                if suggestion:
                    rows.append(suggestion)
        return rows

    def finding_gap_rows(findings, timeline):
        if findings is None or getattr(findings, "empty", True):
            return []
        work = findings.copy()
        rule_col = "rule_id" if "rule_id" in work.columns else "rule" if "rule" in work.columns else None
        if not rule_col:
            return []
        rules = work[rule_col].fillna("").astype(str).str.upper()
        work = work[rules.isin(["R010", "R010.5", "R015", "R016"])].copy()
        if work.empty:
            return []
        rows = []
        for _, row in work.iterrows():
            loco = clean(row.get("loco_no"))
            start = ts(row.get("period_start_utc"))
            end = ts(row.get("period_end_utc"))
            if not loco or start is None:
                continue
            duration = None if end is None else float((end - start).total_seconds() / 60.0)
            before_ru = after_ru = before_loc = after_loc = ""
            if timeline is not None and not timeline.empty and "loco_no" in timeline.columns:
                movements = timeline[(timeline["loco_no"].fillna("").astype(str).str.strip() == loco) & (timeline["row_type"].fillna("").astype(str).str.upper() == "MOVEMENT")].copy()
                if not movements.empty:
                    movements["_start"] = pd.to_datetime(movements.get("period_start_utc"), errors="coerce")
                    movements["_end"] = pd.to_datetime(movements.get("period_end_utc"), errors="coerce")
                    previous = movements[movements["_end"].le(start)].sort_values("_end").tail(1)
                    following = movements[movements["_start"].ge(start)].sort_values("_start").head(1)
                    if not previous.empty:
                        prow = previous.iloc[0]
                        before_ru = clean(prow.get("performing_ru"))
                        before_loc = clean(prow.get("destination_name")) or clean(prow.get("origin_name"))
                    if not following.empty:
                        frow = following.iloc[0]
                        after_ru = clean(frow.get("performing_ru"))
                        after_loc = clean(frow.get("origin_name")) or clean(frow.get("destination_name"))
            same_ru = before_ru if before_ru and before_ru == after_ru else ""
            common = {
                "loco_no": loco,
                "transport_number": clean(row.get("transport_number")),
                "period_start_utc": ts_text(start),
                "period_end_utc": ts_text(end),
                "source_table": clean(row.get("source_table")),
                "source_row_id": clean(row.get("source_row_id")),
            }
            evidence = (
                f"GAP aus Fehlerliste; Dauer: {duration:.0f} Minuten; Ort davor: {before_loc or '-'}; "
                f"Ort danach: {after_loc or '-'}; EVU davor/danach: {same_ru or '-'}; "
                f"Endzeit bekannt: {'ja' if end is not None else 'nein'}."
                if duration is not None
                else f"GAP aus Fehlerliste; Dauer unbekannt; Ort davor: {before_loc or '-'}; Ort danach: {after_loc or '-'}; Endzeit bekannt: nein."
            )
            suggestion = classify(duration, end is not None, is_jump(before_loc, after_loc), same_ru, evidence, common, open_end=end is None)
            if suggestion:
                rows.append(suggestion)
        return rows

    def remove_open_gap_suggestions(result):
        if result is None or getattr(result, "empty", True):
            return result
        if "suggestion_type" not in result.columns:
            return result
        text = (
            result.get("reason", pd.Series("", index=result.index)).fillna("").astype(str)
            + " | "
            + result.get("evidence", pd.Series("", index=result.index)).fillna("").astype(str)
        ).str.lower()
        open_gap_mask = result["suggestion_type"].fillna("").astype(str).eq("GAP_NO_LTE_ASSIGNMENT") & (
            text.str.contains("offenes ende: ja", regex=False)
            | text.str.contains("ohne nachfolgende bewegung", regex=False)
            | text.str.contains("gap ohne bekannte endzeit", regex=False)
            | text.str.contains("endzeit bekannt: nein", regex=False)
        )
        return result.loc[~open_gap_mask].copy()

    def build_suggestion_table_with_gap_matrix(*args, **kwargs):
        result = original_build_suggestion_table(*args, **kwargs)
        timeline = kwargs.get("timeline") if "timeline" in kwargs else None
        findings = kwargs.get("findings") if "findings" in kwargs else None
        rows = movement_rows(timeline) + finding_gap_rows(findings, timeline)
        if rows:
            extra = pd.DataFrame(rows, columns=suggestion_module.SUGGESTION_COLUMNS)
            result = extra if result is None or result.empty else pd.concat([result, extra], ignore_index=True)
            result = result.drop_duplicates(subset=["suggestion_id"], keep="last")
        result = remove_open_gap_suggestions(result)
        if result is None or result.empty or "suggestion_type" not in result.columns:
            return result
        return result[result["suggestion_type"].fillna("").astype(str).ne("BORDER_QUARTER_HOUR_REVIEW")].reset_index(drop=True)

    suggestion_module.build_suggestion_table = build_suggestion_table_with_gap_matrix
    override_ui.build_suggestion_table = build_suggestion_table_with_gap_matrix
    suggestion_module._PHASE11M_GAP_MATRIX_PATCHED = True
