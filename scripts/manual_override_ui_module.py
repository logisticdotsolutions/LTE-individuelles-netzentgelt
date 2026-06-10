"""
Streamlit-Cockpit für kontrollierte manuelle Overrides und Systemvorschläge.

Original-CSVs bleiben unverändert. Phase 5B ergänzt nachvollziehbare, regelbasierte
Vorschläge mit Sicherheitsstufe und Begründung. Kein Vorschlag wird automatisch
übernommen. Fachanwender bestätigen jede Korrektur ausdrücklich.
"""

from __future__ import annotations

import csv
import getpass
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from manual_override_module import (
    MANUAL_OVERRIDE_PATH,
    OVERRIDE_COLUMNS,
    ensure_manual_override_csv,
    utc_now_text,
)
from manual_override_suggestion_module import (
    PHASE5B_SUGGESTION_MARKER,
    SUGGESTION_COLUMNS,
    build_suggestion_table,
    suggestion_for_case,
)
from manual_override_batch_module import (
    PHASE5D_BATCH_MARKER,
    create_overrides_from_selected_suggestions,
)
from manual_override_suggestion_visibility_module import (
    hide_accepted_active_suggestions,
)
from dummy_locomotive_module import (
    DUMMY_CHANGE_LOG_COLUMNS,
    DUMMY_CHANGE_LOG_PATH,
    upsert_dummy_locomotive_mapping,
)


PHASE5B_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607"
# NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608
PHASE5D_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"
DUMMY_UI_CLASSIFICATION_MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609"
SUGGESTION_VISIBILITY_UI_MARKER = "NETZENTGELT_SUGGESTION_VISIBILITY_UI_PHASE9D_V1_20260610"
ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "01_mapping"
BACKUP_DIR = ROOT / ".manual_override_backups"
CHANGE_LOG_PATH = MAP_DIR / "manual_override_change_log.csv"
SUGGESTION_ACCEPTANCE_LOG_PATH = MAP_DIR / "manual_override_suggestion_acceptance_log.csv"

OVERRIDE_TYPE_LABELS = {
    "SET_PERFORMING_RU": "Nutzendes EVU ergänzen oder korrigieren",
    "SET_LOCO_NO": "Loknummer ergänzen oder korrigieren",
    "SET_SEQUENCE_TS": "Grenzzeitanker korrigieren",
    "SET_ACTUAL_DEPARTURE": "Abfahrtszeit korrigieren",
    "SET_ACTUAL_ARRIVAL": "Ankunftszeit korrigieren",
    "CLASSIFY_GAP": "Unterbrechung fachlich klassifizieren",
    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",
    "MARK_DUMMY_LOCOMOTIVE": "Als Dummy-/Planungslok markieren",
}

CLASSIFICATION_OPTIONS = {
    "": "Keine Klassifikation",
    "COLD_STAND": "Mögliche kalte Abstellung",
    "WORKSHOP": "Werkstattaufenthalt",
    "OUTSIDE_DE": "Lok außerhalb Deutschlands",
    "MISSING_MOVEMENT": "Fehlende Bewegung vermutet",
    "SAME_RU_CONTINUITY": "Gleiches nutzendes EVU vor und nach der Unterbrechung",
    "PLAUSIBLE_SHORT_DEVIATION": "Plausible kurze Abweichung",
    "OTHER": "Sonstiger Grund",
}

CHANGE_LOG_COLUMNS = (
    "changed_at_utc",
    "action",
    "override_id",
    "override_type",
    "changed_by",
    "comment",
)

SUGGESTION_ACCEPTANCE_COLUMNS = (
    "accepted_at_utc",
    "suggestion_id",
    "override_id",
    "suggestion_type",
    "override_type",
    "confidence",
    "suggested_value",
    "accepted_value",
    "classification_code",
    "transport_number",
    "loco_no",
    "period_start_utc",
    "period_end_utc",
    "accepted_by",
    "reason",
    "evidence",
    "comment",
)

CONFIDENCE_LABELS = {
    "HIGH": "🟢 Hoch",
    "MEDIUM": "🟡 Mittel",
    "LOW": "⚪ Niedrig",
}

SUGGESTION_TYPE_LABELS = {
    "PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "Nutzendes EVU aus beiden Nachbarbewegungen",
    "PERFORMING_RU_FROM_NEIGHBOURHOOD": "Nutzendes EVU aus angrenzenden Bewegungen",
    "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "Gleiches nutzendes EVU vor und nach der Unterbrechung",
    "PERFORMING_RU_CONFLICT": "Unterschiedliche nutzende EVU prüfen",
    "PERFORMING_RU_REVIEW": "Nutzendes EVU manuell prüfen",
    "LOCO_NO_FROM_TRANSPORT": "Loknummer aus Transportdaten",
    "LOCO_NO_CONFLICT": "Mehrere Loknummern prüfen",
    "LOCO_NO_REVIEW": "Loknummer manuell prüfen",
    "SEQUENCE_TS_FROM_DIRECTION": "Grenzzeitanker aus Richtungslogik",
    "SEQUENCE_TS_REVIEW": "Grenzzeitanker manuell prüfen",
    "BORDER_QUARTER_HOUR_REVIEW": "Grenzereignis am Viertelstundenraster prüfen",
    "BROKEN_LOCATION_CHAIN": "Unterbrochene Ortskette prüfen",
    "POSSIBLE_COLD_STAND_SAME_LOCATION": "Mögliche kalte Abstellung prüfen",
    "ACTUAL_DEPARTURE_REVIEW": "Abfahrtszeit prüfen",
    "ACTUAL_ARRIVAL_REVIEW": "Ankunftszeit prüfen",
    "DOCUMENTATION_REVIEW": "Dokumentationsfall prüfen",
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _read_overrides() -> pd.DataFrame:
    ensure_manual_override_csv()
    try:
        data = pd.read_csv(MANUAL_OVERRIDE_PATH, sep=";", dtype=str, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        data = pd.DataFrame(columns=OVERRIDE_COLUMNS)

    for column in OVERRIDE_COLUMNS:
        if column not in data.columns:
            data[column] = ""

    return data[list(OVERRIDE_COLUMNS)].fillna("")


def _backup_override_file() -> Path | None:
    if not MANUAL_OVERRIDE_PATH.exists():
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_%f")
    target_dir = BACKUP_DIR / stamp
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / MANUAL_OVERRIDE_PATH.name
    shutil.copy2(MANUAL_OVERRIDE_PATH, target)
    return target


def _write_overrides_atomic(data: pd.DataFrame) -> None:
    ensure_manual_override_csv()
    _backup_override_file()
    MANUAL_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = MANUAL_OVERRIDE_PATH.with_name(MANUAL_OVERRIDE_PATH.name + ".tmp")
    data[list(OVERRIDE_COLUMNS)].fillna("").to_csv(
        temporary,
        sep=";",
        index=False,
        encoding="utf-8-sig",
        lineterminator="\r\n",
    )
    os.replace(temporary, MANUAL_OVERRIDE_PATH)


def _append_csv_row(path: Path, fieldnames: tuple[str, ...], row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=";")
        if not exists:
            writer.writeheader()
        writer.writerow({field: _clean(row.get(field)) for field in fieldnames})


def _append_change_log(
    *,
    action: str,
    override_id: str,
    override_type: str,
    changed_by: str,
    comment: str,
) -> None:
    _append_csv_row(
        CHANGE_LOG_PATH,
        CHANGE_LOG_COLUMNS,
        {
            "changed_at_utc": utc_now_text(),
            "action": action,
            "override_id": override_id,
            "override_type": override_type,
            "changed_by": changed_by,
            "comment": comment,
        },
    )


def _append_suggestion_acceptance_log(
    *,
    suggestion: dict[str, object],
    override_id: str,
    accepted_value: str,
    accepted_by: str,
    comment: str,
) -> None:
    if not _clean(suggestion.get("suggestion_id")):
        return
    _append_csv_row(
        SUGGESTION_ACCEPTANCE_LOG_PATH,
        SUGGESTION_ACCEPTANCE_COLUMNS,
        {
            "accepted_at_utc": utc_now_text(),
            "suggestion_id": suggestion.get("suggestion_id"),
            "override_id": override_id,
            "suggestion_type": suggestion.get("suggestion_type"),
            "override_type": suggestion.get("override_type"),
            "confidence": suggestion.get("confidence"),
            "suggested_value": suggestion.get("suggested_value"),
            "accepted_value": accepted_value,
            "classification_code": suggestion.get("classification_code"),
            "transport_number": suggestion.get("transport_number"),
            "loco_no": suggestion.get("loco_no"),
            "period_start_utc": suggestion.get("period_start_utc"),
            "period_end_utc": suggestion.get("period_end_utc"),
            "accepted_by": accepted_by,
            "reason": suggestion.get("reason"),
            "evidence": suggestion.get("evidence"),
            "comment": comment,
        },
    )


def _read_csv_safe(path: Path, columns: tuple[str, ...]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    try:
        return pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
    except Exception:
        return pd.DataFrame(columns=columns)


def _build_case_table(findings: pd.DataFrame, timeline: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "case_label",
        "rule_id",
        "message",
        "transport_number",
        "loco_no",
        "period_start_utc",
        "period_end_utc",
        "source_table",
        "source_row_id",
    ]
    rows: list[dict[str, object]] = []

    if findings is not None and not findings.empty:
        for _, row in findings.iterrows():
            rule_id = _clean(row.get("rule_id"))
            transport = _clean(row.get("transport_number"))
            loco = _clean(row.get("loco_no"))
            start = _clean(row.get("period_start_utc"))
            rows.append(
                {
                    "case_label": f"{rule_id or 'Finding'} | Transport {transport or '-'} | Lok {loco or '-'} | {start or '-'}",
                    "rule_id": rule_id,
                    "message": _clean(row.get("message")),
                    "transport_number": transport,
                    "loco_no": loco,
                    "period_start_utc": start,
                    "period_end_utc": _clean(row.get("period_end_utc")),
                    "source_table": _clean(row.get("source_table")),
                    "source_row_id": _clean(row.get("source_row_id")),
                }
            )

    existing_case_keys = {
        (
            _clean(item.get("loco_no")),
            _clean(item.get("period_start_utc")),
            _clean(item.get("period_end_utc")),
            _clean(item.get("source_table")),
            _clean(item.get("source_row_id")),
        )
        for item in rows
    }

    if timeline is not None and not timeline.empty and "row_type" in timeline.columns:
        gap_mask = timeline["row_type"].fillna("").astype(str).str.upper().eq("GAP")
        if "gap_relevant_de" in timeline.columns:
            gap_mask = gap_mask & (
                timeline["gap_relevant_de"]
                .fillna(False)
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(["true", "1", "yes", "y", "ja"])
            )
        gap_rows = timeline[gap_mask]
        for _, row in gap_rows.iterrows():
            loco = _clean(row.get("loco_no"))
            start = _clean(row.get("period_start_utc"))
            end = _clean(row.get("period_end_utc"))
            case_key = (
                loco,
                start,
                end,
                _clean(row.get("source_table")),
                _clean(row.get("source_row_id")),
            )
            if case_key in existing_case_keys:
                continue
            existing_case_keys.add(case_key)
            rows.append(
                {
                    "case_label": f"GAP | Lok {loco or '-'} | {start or '-'} bis {end or '-'}",
                    "rule_id": "GAP",
                    "message": _clean(row.get("dq_message")) or "Unterbrechung der Lok-Zeitachse",
                    "transport_number": _clean(row.get("transport_number")),
                    "loco_no": loco,
                    "period_start_utc": start,
                    "period_end_utc": end,
                    "source_table": _clean(row.get("source_table")),
                    "source_row_id": _clean(row.get("source_row_id")),
                }
            )

    free_row = {
        "case_label": "Freie manuelle Erfassung",
        "rule_id": "",
        "message": "",
        "transport_number": "",
        "loco_no": "",
        "period_start_utc": "",
        "period_end_utc": "",
        "source_table": "",
        "source_row_id": "",
    }
    return pd.DataFrame([free_row, *rows], columns=columns)


def _run_pipeline(run_all_script: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(run_all_script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )


def _render_active_overrides() -> None:
    overrides = _read_overrides()
    if overrides.empty:
        st.info("Noch keine manuellen Overrides vorhanden.")
        return

    active = overrides[
        ~overrides["active_flag"].fillna("Y").astype(str).str.strip().str.upper().isin(["N", "NO", "FALSE", "0"])
    ].copy()

    if active.empty:
        st.success("Keine aktiven Overrides vorhanden.")
        return

    display = active.copy()
    display["override_type"] = display["override_type"].map(OVERRIDE_TYPE_LABELS).fillna(display["override_type"])
    display = display.rename(
        columns={
            "override_type": "Korrektur",
            "transport_number": "Transportnummer",
            "target_loco_no": "Loknummer",
            "target_actual_departure_utc": "Von",
            "target_actual_arrival_utc": "Bis",
            "override_value": "Neuer Wert",
            "comment": "Begründung",
            "created_by": "Bearbeiter",
            "created_at_utc": "Erstellt am",
        }
    )
    visible_columns = [
        "Korrektur",
        "Loknummer",
        "Transportnummer",
        "Von",
        "Bis",
        "Neuer Wert",
        "Begründung",
        "Bearbeiter",
        "Erstellt am",
    ]
    st.dataframe(
        display[[column for column in visible_columns if column in display.columns]],
        use_container_width=True,
        hide_index=True,
    )

    options = active["override_id"].fillna("").astype(str).tolist()
    selected = st.selectbox("Lokale Korrektur deaktivieren", options, key="manual_override_deactivate_id")
    deactivate_comment = st.text_input(
        "Begründung für die Deaktivierung",
        key="manual_override_deactivate_comment",
    )
    if st.button("Ausgewählte lokale Korrektur deaktivieren", key="manual_override_deactivate_button"):
        if not deactivate_comment.strip():
            st.error("Bitte eine Begründung für die Deaktivierung erfassen.")
            return
        mask = overrides["override_id"].fillna("").astype(str).eq(selected)
        overrides.loc[mask, "active_flag"] = "N"
        overrides.loc[mask, "updated_at_utc"] = utc_now_text()
        _write_overrides_atomic(overrides)
        _append_change_log(
            action="DEACTIVATE",
            override_id=selected,
            override_type=_clean(overrides.loc[mask, "override_type"].iloc[0]),
            changed_by=getpass.getuser(),
            comment=deactivate_comment,
        )
        st.success("Lokale Korrektur wurde deaktiviert. Bitte anschließend neu berechnen.")
        st.rerun()


def _suggestion_display_table(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    result = data.copy()
    gap_suggestion_types = {"GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS", "BROKEN_LOCATION_CHAIN", "POSSIBLE_COLD_STAND_SAME_LOCATION"}
    suggestion_type = result.get("suggestion_type", pd.Series("", index=result.index)).fillna("").astype(str)
    period_start = pd.to_datetime(result.get("period_start_utc", pd.Series(index=result.index, dtype="object")), errors="coerce")
    period_end = pd.to_datetime(result.get("period_end_utc", pd.Series(index=result.index, dtype="object")), errors="coerce")
    gap_minutes = ((period_end - period_start).dt.total_seconds() / 60).round()
    result["GAP-Minuten"] = gap_minutes.where(suggestion_type.isin(gap_suggestion_types)).astype("Int64")
    result["confidence"] = result["confidence"].map(CONFIDENCE_LABELS).fillna(result["confidence"])
    result["suggestion_type"] = result["suggestion_type"].map(SUGGESTION_TYPE_LABELS).fillna(result["suggestion_type"])
    result = result.rename(
        columns={
            "suggestion_type": "Prüfvorschlag",
            "confidence": "Sicherheit",
            "suggested_value": "Vorgeschlagener Wert",
            "transport_number": "Transportnummer",
            "loco_no": "Loknummer",
            "period_start_utc": "Von",
            "period_end_utc": "Bis",
            "reason": "Begründung",
        }
    )
    visible_columns = [
        "Sicherheit",
        "Prüfvorschlag",
        "Loknummer",
        "Transportnummer",
        "Von",
        "Bis",
        "GAP-Minuten",
        "Vorgeschlagener Wert",
        "Begründung",
    ]
    return result[[column for column in visible_columns if column in result.columns]]


def _save_selected_suggestions(
    *,
    suggestions: pd.DataFrame,
    selected_suggestion_ids: list[str],
    created_by: str,
    comment: str,
) -> tuple[list[object], list[object]]:
    overrides = _read_overrides()
    updated, created, skipped = create_overrides_from_selected_suggestions(
        overrides=overrides,
        suggestions=suggestions,
        selected_suggestion_ids=selected_suggestion_ids,
        created_by=created_by,
        comment=comment,
    )

    if created:
        _write_overrides_atomic(updated)
        for item in created:
            override_row = item.override_row
            suggestion = item.suggestion
            _append_change_log(
                action="CREATE_FROM_SUGGESTION_BULK",
                override_id=override_row["override_id"],
                override_type=override_row["override_type"],
                changed_by=override_row["created_by"],
                comment=override_row["comment"],
            )
            _append_suggestion_acceptance_log(
                suggestion=suggestion,
                override_id=override_row["override_id"],
                accepted_value=override_row["override_value"],
                accepted_by=override_row["created_by"],
                comment=override_row["comment"],
            )

    return created, skipped


def _render_suggestions(
    *,
    db_path: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    st.markdown("#### Prüfvorschläge")
    st.caption(
        "Die Anwendung schlägt nachvollziehbare Korrekturen vor. Bitte prüfe jeden Eintrag fachlich. "
        "Bereits übernommene Vorschläge verschwinden aus dieser Liste, solange der zugehörige lokale Override aktiv ist."
    )
    try:
        suggestions = build_suggestion_table(
            db_path=Path(db_path),
            findings=findings,
            timeline=timeline,
        )
        suggestions = hide_accepted_active_suggestions(
            suggestions,
            acceptance_log_path=SUGGESTION_ACCEPTANCE_LOG_PATH,
            overrides=_read_overrides(),
        )
    except Exception as error:
        st.error(f"Prüfvorschläge konnten nicht erzeugt werden: {error}")
        return

    if suggestions.empty:
        st.success("Aktuell wurden keine offenen regelbasierten Prüfvorschläge erzeugt.")
        return

    high_count = int((suggestions["confidence"] == "HIGH").sum())
    medium_count = int((suggestions["confidence"] == "MEDIUM").sum())
    low_count = int((suggestions["confidence"] == "LOW").sum())
    col_all, col_high, col_medium, col_low = st.columns(4)
    col_all.metric("Vorschläge gesamt", len(suggestions))
    col_high.metric("Hohe Sicherheit", high_count)
    col_medium.metric("Mittlere Sicherheit", medium_count)
    col_low.metric("Nur einzeln prüfen", low_count)

    filter_col_confidence, filter_col_type = st.columns(2)
    with filter_col_confidence:
        selected_confidences = st.multiselect(
            "Sicherheitsstufen",
            ["HIGH", "MEDIUM", "LOW"],
            default=["HIGH", "MEDIUM", "LOW"],
            format_func=lambda value: CONFIDENCE_LABELS[value],
            key="manual_override_suggestion_confidence_filter",
        )
    with filter_col_type:
        suggestion_types = sorted(suggestions["suggestion_type"].dropna().astype(str).unique().tolist())
        selected_types = st.multiselect(
            "Vorschlagsarten",
            suggestion_types,
            default=suggestion_types,
            format_func=lambda value: SUGGESTION_TYPE_LABELS.get(value, value),
            key="manual_override_suggestion_type_filter",
        )

    filtered = suggestions[
        suggestions["confidence"].isin(selected_confidences)
        & suggestions["suggestion_type"].isin(selected_types)
    ].copy()
    st.write(f"Treffer: **{len(filtered)}**")
    if filtered.empty:
        st.info("Für die gesetzten Filter sind keine offenen Prüfvorschläge vorhanden.")
        return

    csv_data = _suggestion_display_table(filtered).to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Vorschlagsliste als CSV herunterladen",
        data=csv_data,
        file_name="pruefvorschlaege.csv",
        mime="text/csv",
        key="download_manual_override_suggestions",
    )

    bulk_source = filtered.reset_index(drop=True).copy()
    bulk_source["_actionable"] = (
        bulk_source["suggested_value"].fillna("").astype(str).str.strip().ne("")
        | bulk_source["classification_code"].fillna("").astype(str).str.strip().ne("")
    )
    bulk_source["_bulk_allowed"] = (
        bulk_source["_actionable"]
        & bulk_source["confidence"].fillna("").astype(str).str.upper().isin(["HIGH", "MEDIUM"])
    )
    bulk_source["_bulk_status"] = "Nur Hinweis"
    bulk_source.loc[
        bulk_source["_actionable"]
        & bulk_source["confidence"].fillna("").astype(str).str.upper().eq("LOW"),
        "_bulk_status",
    ] = "Nur einzeln prüfen"
    bulk_source.loc[bulk_source["_bulk_allowed"], "_bulk_status"] = "Sammelübernahme möglich"

    st.markdown("##### Vorschläge auswählen")
    st.caption(
        "Die Checkboxen sind immer sichtbar. Markiere nur fachlich geprüfte Einträge. "
        "Hinweise mit niedriger Sicherheit oder ohne konkreten Wert können nicht gesammelt gespeichert werden."
    )
    bulk_table = _suggestion_display_table(bulk_source).copy()
    bulk_table.insert(0, "_suggestion_id", bulk_source["suggestion_id"].fillna("").astype(str).tolist())
    bulk_table.insert(1, "Übernehmen", False)
    bulk_table.insert(2, "Sammelübernahme", bulk_source["_bulk_status"].tolist())
    bulk_table = st.data_editor(
        bulk_table,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[column for column in bulk_table.columns if column != "Übernehmen"],
        column_config={
            "_suggestion_id": None,
            "Übernehmen": st.column_config.CheckboxColumn(
                "Übernehmen",
                help="Nur fachlich geprüfte Vorschläge markieren.",
                default=False,
            ),
        },
        key="manual_override_suggestion_bulk_editor",
    )

    checked_mask = bulk_table["Übernehmen"].fillna(False)
    if "_suggestion_id" in bulk_table.columns:
        checked_ids = bulk_table.loc[checked_mask, "_suggestion_id"].fillna("").astype(str).tolist()
    else:
        checked_ids = bulk_source.loc[checked_mask.to_numpy(), "suggestion_id"].fillna("").astype(str).tolist()
    allowed_ids = set(
        bulk_source.loc[bulk_source["_bulk_allowed"], "suggestion_id"].fillna("").astype(str).tolist()
    )
    selected_ids = [suggestion_id for suggestion_id in checked_ids if suggestion_id in allowed_ids]
    blocked_ids = [suggestion_id for suggestion_id in checked_ids if suggestion_id not in allowed_ids]
    st.write(f"Ausgewählt für Sammelübernahme: **{len(selected_ids)}**")
    if blocked_ids:
        st.warning(
            f"{len(blocked_ids)} markierter Hinweis kann nicht gesammelt übernommen werden. "
            "Öffne ihn unten für die detaillierte Einzelprüfung."
        )

    bulk_created_by = st.text_input(
        "Bearbeiter für Sammelübernahme",
        value=getpass.getuser(),
        key="manual_override_bulk_created_by",
    )
    bulk_comment = st.text_area(
        "Gemeinsame Begründung für die ausgewählten Vorschläge",
        placeholder="Warum dürfen diese Vorschläge lokal übernommen werden?",
        key="manual_override_bulk_comment",
    )
    bulk_save_col, bulk_rebuild_col = st.columns(2)
    with bulk_save_col:
        save_selected = st.button(
            "Ausgewählte Vorschläge speichern",
            key="manual_override_bulk_save",
            use_container_width=True,
            disabled=not selected_ids,
        )
    with bulk_rebuild_col:
        save_selected_and_rebuild = st.button(
            "Speichern und neu prüfen",
            type="primary",
            key="manual_override_bulk_save_rebuild",
            use_container_width=True,
            disabled=not selected_ids,
        )

    if save_selected or save_selected_and_rebuild:
        try:
            created, skipped = _save_selected_suggestions(
                suggestions=bulk_source,
                selected_suggestion_ids=selected_ids,
                created_by=bulk_created_by,
                comment=bulk_comment,
            )
        except ValueError as error:
            st.error(str(error))
            return

        if created:
            st.success(f"{len(created)} lokale Korrektur(en) wurden gespeichert.")
        for skipped_item in skipped:
            st.warning(f"{skipped_item.suggestion_id}: {skipped_item.reason}")

        if save_selected_and_rebuild and created:
            with st.status("Werte werden mit den neuen lokalen Korrekturen sicher neu berechnet ...", expanded=True) as status:
                result = _run_pipeline(Path(ROOT / "scripts" / "run_all.py"))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.session_state["overview_refresh_completed"] = True
                    st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.error("Der letzte produktive Stand bleibt erhalten.")
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)
        elif created:
            st.info("Bitte anschließend neu prüfen, damit Timeline, automatische Prüfung und Exporte aktualisiert werden.")

    st.markdown("##### Einzelvorschlag detailliert prüfen")
    with st.expander("Einzelvorschlag öffnen", expanded=False):
        detail_source = filtered.copy()
        detail_source["_selection_label"] = detail_source.apply(
            lambda row: (
                f"{SUGGESTION_TYPE_LABELS.get(_clean(row['suggestion_type']), _clean(row['suggestion_type']))} "
                f"| Lok {_clean(row['loco_no']) or '-'} | Transport {_clean(row['transport_number']) or '-'}"
            ),
            axis=1,
        )
        selected_label = st.selectbox(
            "Vorschlag für Bearbeitung auswählen",
            detail_source["_selection_label"].tolist(),
            key="manual_override_suggestion_select",
        )
        selected = detail_source[detail_source["_selection_label"].eq(selected_label)].iloc[0].to_dict()
        st.caption(_clean(selected.get("reason")))
        if _clean(selected.get("evidence")):
            st.caption("Nachweis: " + _clean(selected.get("evidence")))
        if st.button("Vorschlag in Bearbeitungsmaske öffnen", key="manual_override_suggestion_prefill_button"):
            st.session_state["manual_override_suggestion_prefill"] = selected
            st.success("Vorschlag wurde vorgemerkt. Öffne jetzt den Reiter 'Neue Korrektur'.")
            st.rerun()


def _render_new_override(
    *,
    db_path: Path,
    run_all_script: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    st.markdown("### Neue lokale Korrektur")
    st.caption("Die Original-CSV-Dateien bleiben unverändert. Die Korrektur wirkt erst nach einer Neuberechnung.")

    prefill = st.session_state.get("manual_override_suggestion_prefill")
    prefill = prefill if isinstance(prefill, dict) else {}
    cases = _build_case_table(findings=findings, timeline=timeline)
    if prefill:
        st.success("Ein Systemvorschlag ist vorgemerkt. Prüfe die Werte bewusst und bestätige die Korrektur erst nach fachlicher Kontrolle.")
        if st.button("Vorgemerkten Systemvorschlag verwerfen", key="manual_override_discard_prefill"):
            st.session_state.pop("manual_override_suggestion_prefill", None)
            st.rerun()

    selected_case_label = st.selectbox(
        "Prüffall oder freie Erfassung",
        cases["case_label"].tolist(),
        key="manual_override_case_select",
    )
    selected_case = cases[cases["case_label"].eq(selected_case_label)].iloc[0]

    override_types = list(OVERRIDE_TYPE_LABELS)
    prefill_type = _clean(prefill.get("override_type"))
    default_type_index = override_types.index(prefill_type) if prefill_type in override_types else 0

    with st.form("manual_override_create_form"):
        override_type = st.selectbox(
            "Art der Bearbeitung",
            override_types,
            index=default_type_index,
            format_func=lambda value: OVERRIDE_TYPE_LABELS[value],
        )
        generated = suggestion_for_case(
            db_path=Path(db_path),
            override_type=override_type,
            transport_number=_clean(prefill.get("transport_number")) or _clean(selected_case.get("transport_number")),
            loco_no=_clean(prefill.get("loco_no")) or _clean(selected_case.get("loco_no")),
            period_start_utc=_clean(prefill.get("period_start_utc")) or _clean(selected_case.get("period_start_utc")),
            period_end_utc=_clean(prefill.get("period_end_utc")) or _clean(selected_case.get("period_end_utc")),
            source_table=_clean(prefill.get("source_table")) or _clean(selected_case.get("source_table")),
            source_row_id=_clean(prefill.get("source_row_id")) or _clean(selected_case.get("source_row_id")),
        )
        suggested_value = _clean(prefill.get("suggested_value")) or _clean(generated.suggested_value)
        suggested_classification = _clean(prefill.get("classification_code")) or _clean(generated.classification_code)
        if suggested_value:
            st.info(f"Systemvorschlag: **{suggested_value}**")
        elif _clean(generated.reason):
            st.caption("Hinweis: " + _clean(generated.reason))

        transport_number = st.text_input(
            "Transportnummer",
            value=_clean(prefill.get("transport_number")) or _clean(selected_case.get("transport_number")),
        )
        target_loco_no = st.text_input(
            "Betroffene Loknummer",
            value=_clean(prefill.get("loco_no")) or _clean(selected_case.get("loco_no")),
        )
        target_actual_departure = st.text_input(
            "Bisherige Abfahrtszeit zur Eingrenzung",
            value=_clean(prefill.get("period_start_utc")) or _clean(selected_case.get("period_start_utc")),
            placeholder="YYYY-MM-DDTHH:MM:SS",
        )
        target_actual_arrival = st.text_input(
            "Bisherige Ankunftszeit zur Dokumentation",
            value=_clean(prefill.get("period_end_utc")) or _clean(selected_case.get("period_end_utc")),
            placeholder="YYYY-MM-DDTHH:MM:SS",
        )
        override_value = st.text_input(
            "Neuer Wert",
            value=suggested_value,
            placeholder="z. B. EVU, Loknummer oder ISO-Zeitstempel",
        )
        classification_options = list(CLASSIFICATION_OPTIONS)
        default_classification_index = classification_options.index(suggested_classification) if suggested_classification in classification_options else 0
        classification_code = st.selectbox(
            "Fachliche Klassifikation",
            classification_options,
            index=default_classification_index,
            format_func=lambda value: CLASSIFICATION_OPTIONS[value],
        )
        created_by = st.text_input("Bearbeiter", value=getpass.getuser())
        comment = st.text_area("Begründung / Kommentar")
        save_only = st.form_submit_button("Override speichern")
        save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary")

    if not (save_only or save_and_rebuild):
        return

    if not comment.strip():
        st.error("Bitte eine Begründung für die lokale Korrektur erfassen.")
        return
    if override_type == "MARK_DUMMY_LOCOMOTIVE":
        if not target_loco_no.strip():
            st.error("Bitte die Dummy-/Planungslok erfassen.")
            return
        action = upsert_dummy_locomotive_mapping(
            loco_no=target_loco_no.strip(),
            reason=comment.strip(),
            changed_by=created_by.strip() or getpass.getuser(),
        )
        st.success(f"Dummy-/Planungslok {target_loco_no.strip()} wurde gespeichert. Aktion: {action}.")
        if save_and_rebuild:
            with st.status("Dummy-Katalog wird gespeichert und sicher neu berechnet ...", expanded=True) as status:
                result = _run_pipeline(Path(run_all_script))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.session_state["overview_refresh_completed"] = True
                    st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.error("Der letzte produktive DuckDB-Stand bleibt erhalten.")
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)
        return

    now = utc_now_text()
    override_id = "OVR_" + uuid.uuid4().hex[:12].upper()
    new_row = {
        "override_id": override_id,
        "active_flag": "Y",
        "override_type": override_type,
        "transport_number": transport_number.strip(),
        "target_loco_no": target_loco_no.strip(),
        "target_actual_departure_utc": target_actual_departure.strip(),
        "target_actual_arrival_utc": target_actual_arrival.strip(),
        "target_source_table": _clean(prefill.get("source_table")) or _clean(selected_case.get("source_table")),
        "target_source_row_id": _clean(prefill.get("source_row_id")) or _clean(selected_case.get("source_row_id")),
        "override_value": override_value.strip(),
        "classification_code": classification_code,
        "comment": comment.strip(),
        "created_by": created_by.strip() or getpass.getuser(),
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    overrides = _read_overrides()
    overrides = pd.concat([overrides, pd.DataFrame([new_row])], ignore_index=True)
    _write_overrides_atomic(overrides)
    _append_change_log(
        action="CREATE",
        override_id=override_id,
        override_type=override_type,
        changed_by=new_row["created_by"],
        comment=new_row["comment"],
    )
    if prefill:
        _append_suggestion_acceptance_log(
            suggestion=prefill,
            override_id=override_id,
            accepted_value=override_value.strip(),
            accepted_by=new_row["created_by"],
            comment=new_row["comment"],
        )
        st.session_state.pop("manual_override_suggestion_prefill", None)
    st.success(f"Lokale Korrektur {override_id} wurde gespeichert.")
    if save_and_rebuild:
        with st.status("Werte werden mit der lokalen Korrektur sicher neu berechnet ...", expanded=True) as status:
            result = _run_pipeline(Path(run_all_script))
            if result.returncode == 0:
                status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                st.session_state["overview_refresh_completed"] = True
                st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                st.rerun()
            status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
            st.error("Der letzte produktive DuckDB-Stand bleibt erhalten.")
            st.text_area("Fehler der Berechnung", result.stderr, height=220)
            st.text_area("Output der Berechnung", result.stdout, height=220)
    else:
        st.info("Bitte anschließend neu prüfen, damit Timeline, Quality Gate und Exporte aktualisiert werden.")


def _render_override_log() -> None:
    log = _read_csv_safe(CHANGE_LOG_PATH, CHANGE_LOG_COLUMNS)
    if log.empty:
        st.info("Noch kein Änderungsverlauf vorhanden.")
        return
    st.dataframe(log.iloc[::-1], use_container_width=True, hide_index=True)


def render_manual_override_cockpit(
    *,
    db_path: Path,
    run_all_script: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    st.info("Lokale Korrekturen ändern weder RailCube noch die importierten Original-CSVs. Ein neuer Rohdatenimport kann lokale Annahmen fachlich überholen.")
    tab_suggestions, tab_new, tab_active, tab_log = st.tabs(
        ["Systemvorschläge", "Neue Korrektur", "Aktive Korrekturen", "Verlauf"]
    )
    with tab_suggestions:
        _render_suggestions(db_path=db_path, findings=findings, timeline=timeline)
    with tab_new:
        _render_new_override(db_path=db_path, run_all_script=run_all_script, findings=findings, timeline=timeline)
    with tab_active:
        _render_active_overrides()
    with tab_log:
        _render_override_log()
