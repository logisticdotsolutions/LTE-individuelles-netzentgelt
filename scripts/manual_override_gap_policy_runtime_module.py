from __future__ import annotations


GAP_POLICY_UI_LABEL_MARKER = "NETZENTGELT_GAP_POLICY_UI_LABELS_20260618"


def install_gap_policy_labels() -> None:
    """Register operator-friendly labels and keep movement-based GAP suggestions visible."""
    import re

    import pandas as pd

    import manual_override_suggestion_module as suggestion_module
    import manual_override_ui_module as override_ui

    override_ui.CLASSIFICATION_OPTIONS.setdefault(
        "NO_LTE_ASSIGNMENT",
        "Keine LTE-Zuweisung / nicht im Report",
    )
    override_ui.SUGGESTION_TYPE_LABELS.update(
        {
            "GAP_NO_LTE_ASSIGNMENT": "Keine LTE-Zuweisung / nicht im Report",
            "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "EVU aus direkter GAP-Umgebung übernehmen",
            "POSSIBLE_COLD_STAND_SAME_LOCATION": "Kaltabstellung ab GAP über 120 Minuten prüfen",
        }
    )

    if getattr(suggestion_module, "_PHASE11I_GAP_UI_FALLBACK_PATCHED", False):
        return

    original_build_suggestion_table = suggestion_module.build_suggestion_table

    def _clean(value: object) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
        return str(value).strip()

    def _timestamp_text(value: object) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return pd.Timestamp(parsed).strftime("%Y-%m-%dT%H:%M:%S")

    def _location_key(value: object) -> str:
        return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())

    def _movement_gap_fallback_rows(timeline) -> list[dict[str, str]]:
        if timeline is None or getattr(timeline, "empty", True) or "row_type" not in timeline.columns:
            return []

        movements = timeline[
            timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("MOVEMENT")
        ].copy()
        if movements.empty:
            return []

        movements["_gap_fallback_sort_sequence"] = pd.to_numeric(
            movements.get("sort_sequence", pd.Series(index=movements.index, dtype="object")),
            errors="coerce",
        )
        movements["_gap_fallback_sort_ts"] = pd.to_datetime(
            movements.get("sequence_ts", movements.get("period_start_utc", "")),
            errors="coerce",
        )
        movements["_gap_fallback_source_row_id"] = pd.to_numeric(
            movements.get("source_row_id", pd.Series(index=movements.index, dtype="object")),
            errors="coerce",
        )

        rows: list[dict[str, str]] = []
        for loco_no, group in movements.groupby("loco_no", dropna=False):
            ordered = group.sort_values(
                ["_gap_fallback_sort_sequence", "_gap_fallback_sort_ts", "_gap_fallback_source_row_id"],
                na_position="last",
            ).reset_index(drop=True)
            for index in range(len(ordered) - 1):
                previous = ordered.iloc[index]
                following = ordered.iloc[index + 1]
                previous_end = pd.to_datetime(previous.get("period_end_utc"), errors="coerce")
                following_start = pd.to_datetime(following.get("period_start_utc"), errors="coerce")
                if pd.isna(previous_end) or pd.isna(following_start) or following_start <= previous_end:
                    continue

                duration = float((following_start - previous_end).total_seconds() / 60.0)
                previous_ru = _clean(previous.get("performing_ru"))
                following_ru = _clean(following.get("performing_ru"))
                same_ru = previous_ru if previous_ru and previous_ru == following_ru else ""
                before_location = _clean(previous.get("destination_name")) or _clean(previous.get("origin_name"))
                after_location = _clean(following.get("origin_name")) or _clean(following.get("destination_name"))
                has_jump = bool(before_location and after_location and _location_key(before_location) != _location_key(after_location))
                evidence = (
                    f"GAP-Dauer: {duration:.0f} Minuten; "
                    f"Ort davor: {before_location or '-'}; Ort danach: {after_location or '-'}; "
                    f"PerformingRU davor/danach: {same_ru or '-'}; "
                    "Quelle: Movement-Abstand ohne explizite GAP-Zeile."
                )
                common = {
                    "loco_no": _clean(loco_no),
                    "transport_number": _clean(previous.get("transport_number")),
                    "period_start_utc": _timestamp_text(previous_end),
                    "period_end_utc": _timestamp_text(following_start),
                    "source_table": _clean(previous.get("source_table")),
                    "source_row_id": _clean(previous.get("source_row_id")),
                }

                if has_jump:
                    rows.append(
                        suggestion_module._new_suggestion(
                            suggestion_type="GAP_NO_LTE_ASSIGNMENT",
                            override_type="CLASSIFY_GAP",
                            classification_code="NO_LTE_ASSIGNMENT",
                            confidence="MEDIUM",
                            suggested_value="Keine LTE-Zuweisung / nicht im Report",
                            reason="Ortssprung zwischen zwei Bewegungen erkannt. Vorschlag: keine LTE-Zuweisung / nicht im Report.",
                            evidence=evidence,
                            **common,
                        ).to_dict()
                    )
                    continue

                if duration < 120 and same_ru:
                    rows.append(
                        suggestion_module._new_suggestion(
                            suggestion_type="GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS",
                            override_type="CLASSIFY_GAP",
                            classification_code="SAME_RU_CONTINUITY",
                            confidence="HIGH",
                            suggested_value=same_ru,
                            reason="GAP ist kürzer als 120 Minuten und direkt davor sowie danach ist dasselbe nutzende EVU vorhanden. Vorschlag: EVU übernehmen.",
                            evidence=evidence,
                            **common,
                        ).to_dict()
                    )
                    continue

                if duration > 120 and same_ru:
                    rows.append(
                        suggestion_module._new_suggestion(
                            suggestion_type="POSSIBLE_COLD_STAND_SAME_LOCATION",
                            override_type="CLASSIFY_GAP",
                            classification_code="COLD_STAND",
                            confidence="MEDIUM",
                            suggested_value="Mögliche kalte Abstellung",
                            reason="GAP ist länger als 120 Minuten, es liegt kein Ortssprung vor und direkt davor sowie danach ist dasselbe EVU vorhanden. Vorschlag: mögliche kalte Abstellung prüfen.",
                            evidence=evidence,
                            **common,
                        ).to_dict()
                    )
        return rows

    def build_suggestion_table_with_movement_gap_fallback(*args, **kwargs):
        result = original_build_suggestion_table(*args, **kwargs)
        timeline = kwargs.get("timeline") if "timeline" in kwargs else None
        fallback_rows = _movement_gap_fallback_rows(timeline)

        if fallback_rows:
            fallback = pd.DataFrame(fallback_rows, columns=suggestion_module.SUGGESTION_COLUMNS)
            if result is None or result.empty:
                result = fallback
            else:
                result = pd.concat([result, fallback], ignore_index=True)
            if "suggestion_id" in result.columns:
                result = result.drop_duplicates(subset=["suggestion_id"], keep="first")

        if result is None or result.empty or "suggestion_type" not in result.columns:
            return result

        return result[
            result["suggestion_type"].fillna("").astype(str).ne("BORDER_QUARTER_HOUR_REVIEW")
        ].reset_index(drop=True)

    suggestion_module.build_suggestion_table = build_suggestion_table_with_movement_gap_fallback
    suggestion_module._PHASE11I_GAP_UI_FALLBACK_PATCHED = True
