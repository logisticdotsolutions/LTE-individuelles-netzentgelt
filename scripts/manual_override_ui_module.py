"""
Streamlit-Cockpit für kontrollierte manuelle Overrides.

Die Oberfläche ist bewusst fachanwenderorientiert. Original-CSVs bleiben
unverändert. Änderungen werden ausschließlich in manual_overrides.csv erfasst
und anschließend durch den sicheren Pipeline-Neuaufbau verarbeitet.
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
from typing import Iterable

import duckdb
import pandas as pd
import streamlit as st

from manual_override_module import (
    MANUAL_OVERRIDE_PATH,
    OVERRIDE_COLUMNS,
    ensure_manual_override_csv,
    utc_now_text,
)


PHASE5A_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_UI_V1_20260607"
ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "01_mapping"
BACKUP_DIR = ROOT / ".manual_override_backups"
CHANGE_LOG_PATH = MAP_DIR / "manual_override_change_log.csv"

OVERRIDE_TYPE_LABELS = {
    "SET_PERFORMING_RU": "Nutzendes EVU ergänzen oder korrigieren",
    "SET_LOCO_NO": "Loknummer ergänzen oder korrigieren",
    "SET_SEQUENCE_TS": "Grenzzeitanker korrigieren",
    "SET_ACTUAL_DEPARTURE": "Abfahrtszeit korrigieren",
    "SET_ACTUAL_ARRIVAL": "Ankunftszeit korrigieren",
    "CLASSIFY_GAP": "Unterbrechung fachlich klassifizieren",
    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",
}

CLASSIFICATION_OPTIONS = {
    "": "Keine Klassifikation",
    "COLD_STAND": "Mögliche kalte Abstellung",
    "WORKSHOP": "Werkstattaufenthalt",
    "OUTSIDE_DE": "Lok außerhalb Deutschlands",
    "MISSING_MOVEMENT": "Fehlende Bewegung vermutet",
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


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
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


def _append_change_log(
    *,
    action: str,
    override_id: str,
    override_type: str,
    changed_by: str,
    comment: str,
) -> None:
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    exists = CHANGE_LOG_PATH.exists()
    with CHANGE_LOG_PATH.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHANGE_LOG_COLUMNS, delimiter=";")
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "changed_at_utc": utc_now_text(),
                "action": action,
                "override_id": override_id,
                "override_type": override_type,
                "changed_by": changed_by,
                "comment": comment,
            }
        )


def _table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _columns(con, table_name: str) -> list[str]:
    return [row[0] for row in con.execute(f'describe "{table_name}"').fetchall()]


def _pick(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if str(candidate).lower() in by_lower:
            return by_lower[str(candidate).lower()]
    return None


def _valid_loco(value: object) -> bool:
    text = _clean(value)
    return bool(text and text != "00000000000-0" and "dummy" not in text.lower())


def _suggest_performing_ru(db_path: Path, loco_no: str, period_start: str) -> tuple[str, str, str]:
    if not db_path.exists() or not loco_no:
        return "", "LOW", "Kein belastbarer Vorschlag ableitbar."

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        if not _table_exists(con, "core_loco_timeline"):
            return "", "LOW", "Timeline fehlt."

        rows = con.execute(
            """
            select performing_ru, period_start_utc
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and loco_no = ?
              and nullif(trim(performing_ru), '') is not null
            order by abs(epoch(period_start_utc - try_cast(? as timestamp))) asc nulls last
            limit 4
            """,
            [loco_no, period_start or None],
        ).fetchall()
        values = []
        for row in rows:
            value = _clean(row[0])
            if value and value not in values:
                values.append(value)

        if len(values) == 1:
            return values[0], "MEDIUM", "Angrenzende Bewegungen derselben Lok zeigen eindeutig dieselbe PerformingRU."
        if len(values) > 1:
            return "", "LOW", "Angrenzende Bewegungen enthalten unterschiedliche PerformingRUs. Manuelle Auswahl erforderlich."
        return "", "LOW", "Keine angrenzende PerformingRU gefunden."
    finally:
        con.close()


def _suggest_loco_no(db_path: Path, transport_number: str) -> tuple[str, str, str]:
    if not db_path.exists() or not transport_number:
        return "", "LOW", "Kein belastbarer Vorschlag ableitbar."

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        candidates: list[str] = []
        for table_name, loco_candidates in [
            ("raw_transportdetail", ["FirstLocomotiveNo"]),
            ("raw_locomotivemovement", ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]),
        ]:
            if not _table_exists(con, table_name):
                continue
            cols = _columns(con, table_name)
            transport_col = _pick(cols, ["TransportNumber", "TransportNo", "TransportId", "TransportID"])
            loco_col = _pick(cols, loco_candidates)
            if not transport_col or not loco_col:
                continue
            rows = con.execute(
                f"""
                select distinct trim(cast("{loco_col}" as varchar))
                from "{table_name}"
                where trim(cast("{transport_col}" as varchar)) = ?
                """,
                [transport_number],
            ).fetchall()
            for row in rows:
                value = _clean(row[0])
                if _valid_loco(value) and value not in candidates:
                    candidates.append(value)

        if len(candidates) == 1:
            return candidates[0], "MEDIUM", "Für den Transport wurde genau eine plausible Loknummer in den vorhandenen Daten gefunden."
        if len(candidates) > 1:
            return "", "LOW", "Mehrere plausible Loknummern gefunden. Manuelle Auswahl erforderlich."
        return "", "LOW", "Keine plausible Loknummer in den vorhandenen Daten gefunden."
    finally:
        con.close()


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
            message = _clean(row.get("message"))
            rows.append(
                {
                    "case_label": f"{rule_id or 'Finding'} | Transport {transport or '-'} | Lok {loco or '-'} | {start or '-'}",
                    "rule_id": rule_id,
                    "message": message,
                    "transport_number": transport,
                    "loco_no": loco,
                    "period_start_utc": start,
                    "period_end_utc": _clean(row.get("period_end_utc")),
                    "source_table": _clean(row.get("source_table")),
                    "source_row_id": _clean(row.get("source_row_id")),
                }
            )

    if timeline is not None and not timeline.empty and "row_type" in timeline.columns:
        gap_rows = timeline[
            timeline["row_type"].fillna("").astype(str).str.upper().eq("GAP")
        ]
        for _, row in gap_rows.iterrows():
            loco = _clean(row.get("loco_no"))
            start = _clean(row.get("period_start_utc"))
            end = _clean(row.get("period_end_utc"))
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

    result = pd.DataFrame(rows, columns=columns)
    if result.empty:
        return pd.DataFrame(
            [
                {
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
            ]
        )

    free_row = pd.DataFrame(
        [
            {
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
        ]
    )
    return pd.concat([free_row, result], ignore_index=True)


def _suggestion_for_type(
    *,
    override_type: str,
    db_path: Path,
    transport_number: str,
    loco_no: str,
    period_start: str,
) -> tuple[str, str, str]:
    if override_type == "SET_PERFORMING_RU":
        return _suggest_performing_ru(db_path, loco_no, period_start)
    if override_type == "SET_LOCO_NO":
        return _suggest_loco_no(db_path, transport_number)
    if override_type == "SET_SEQUENCE_TS":
        return period_start, "LOW", "Als Startwert wird der vorhandene Zeitanker angezeigt. Grenzstations- und GPS-Abweichung fachlich prüfen."
    if override_type == "SET_ACTUAL_DEPARTURE":
        return period_start, "LOW", "Als Startwert wird die bisherige Abfahrtszeit angezeigt."
    if override_type == "SET_ACTUAL_ARRIVAL":
        return "", "LOW", "Ankunftszeit bitte anhand der verfügbaren Daten fachlich ergänzen."
    return "", "LOW", "Dokumentation ohne automatische fachliche Wirkung in Phase 5A."


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
    st.dataframe(display, use_container_width=True, hide_index=True)

    options = active["override_id"].fillna("").astype(str).tolist()
    selected = st.selectbox("Override deaktivieren", options, key="manual_override_deactivate_id")
    deactivate_comment = st.text_input(
        "Begründung für die Deaktivierung",
        key="manual_override_deactivate_comment",
    )
    if st.button("Ausgewählten Override deaktivieren", key="manual_override_deactivate_button"):
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
        st.success("Override wurde deaktiviert. Bitte anschließend neu berechnen.")
        st.rerun()


def render_manual_override_cockpit(
    *,
    db_path: Path,
    run_all_script: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    """Fachanwendertaugliches Cockpit zum Erfassen und Prüfen von Overrides."""
    st.subheader("Fall bearbeiten")
    st.caption(
        "Originaldaten bleiben unverändert. Bestätigte Korrekturen werden separat protokolliert "
        "und beim sicheren Neuaufbau der Tagesdaten angewandt."
    )

    tab_new, tab_active, tab_audit = st.tabs(
        ["Neue Korrektur", "Aktive Overrides", "Audit und Hinweise"]
    )

    with tab_new:
        cases = _build_case_table(findings=findings, timeline=timeline)
        selected_label = st.selectbox(
            "Prüffall auswählen",
            cases["case_label"].tolist(),
            key="manual_override_case_select",
        )
        case = cases[cases["case_label"].eq(selected_label)].iloc[0]

        override_type = st.selectbox(
            "Art der Bearbeitung",
            list(OVERRIDE_TYPE_LABELS.keys()),
            format_func=lambda value: OVERRIDE_TYPE_LABELS[value],
            key="manual_override_type_select",
        )

        default_transport = _clean(case.get("transport_number"))
        default_loco = _clean(case.get("loco_no"))
        default_start = _clean(case.get("period_start_utc"))
        default_end = _clean(case.get("period_end_utc"))
        suggestion, confidence, reason = _suggestion_for_type(
            override_type=override_type,
            db_path=Path(db_path),
            transport_number=default_transport,
            loco_no=default_loco,
            period_start=default_start,
        )

        st.markdown("#### Systemvorschlag")
        col_suggestion, col_confidence = st.columns([4, 1])
        with col_suggestion:
            st.write(suggestion or "Kein eindeutiger Vorschlag vorhanden.")
            st.caption(reason)
        with col_confidence:
            st.metric("Sicherheit", confidence)

        form_key = f"manual_override_form_{override_type}_{abs(hash(selected_label))}"
        with st.form(form_key):
            transport_number = st.text_input("Transportnummer", value=default_transport)
            target_loco_no = st.text_input("Betroffene Loknummer", value=default_loco)
            target_actual_departure = st.text_input(
                "Bisherige Abfahrtszeit zur Eingrenzung",
                value=default_start,
                help="Optional. Sinnvoll, wenn ein Transport mehrere Bewegungszeilen enthält.",
            )
            target_actual_arrival = st.text_input(
                "Bisherige Ankunftszeit zur Dokumentation",
                value=default_end,
            )
            override_value = st.text_input(
                "Neuer Wert",
                value=suggestion,
                help="Bei Klassifikation oder reiner Notiz kann dieses Feld leer bleiben.",
            )
            classification_code = st.selectbox(
                "Fachliche Klassifikation",
                list(CLASSIFICATION_OPTIONS.keys()),
                format_func=lambda value: CLASSIFICATION_OPTIONS[value],
            )
            created_by = st.text_input("Bearbeiter", value=getpass.getuser())
            comment = st.text_area(
                "Begründung / Kommentar",
                placeholder="Warum ist diese Korrektur fachlich zulässig?",
            )
            save_only = st.form_submit_button("Override speichern")
            save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary")

        if save_only or save_and_rebuild:
            if not comment.strip():
                st.error("Bitte eine nachvollziehbare Begründung erfassen.")
                return
            if override_type not in {"CLASSIFY_GAP", "CASE_NOTE"} and not override_value.strip():
                st.error("Für diese Korrektur ist ein neuer Wert erforderlich.")
                return
            if override_type == "CLASSIFY_GAP" and not classification_code:
                st.error("Bitte eine fachliche Klassifikation auswählen.")
                return
            if override_type in {"SET_LOCO_NO", "SET_PERFORMING_RU", "SET_ACTUAL_DEPARTURE", "SET_ACTUAL_ARRIVAL"} and not transport_number.strip():
                st.error("Für diese Korrektur ist mindestens eine Transportnummer erforderlich.")
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
                "target_source_table": _clean(case.get("source_table")),
                "target_source_row_id": _clean(case.get("source_row_id")),
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
            st.success(f"Override {override_id} wurde gespeichert.")

            if save_and_rebuild:
                with st.status("Werte werden mit dem neuen Override sicher neu berechnet ...", expanded=True) as status:
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
                st.info("Bitte anschließend neu berechnen, damit Timeline, Quality Gate und Exporte aktualisiert werden.")

    with tab_active:
        _render_active_overrides()

    with tab_audit:
        st.markdown("#### Sicherheitsprinzip")
        st.write(
            "Die Original-CSVs werden nicht verändert. Jede Korrektur besitzt eine ID, Bearbeiter, "
            "Zeitstempel und Kommentar. Widersprüchliche aktive Overrides stoppen die Pipeline, statt "
            "unbemerkt einen unsicheren Datenstand zu erzeugen."
        )
        st.markdown("#### Phase-5A-Grenze")
        st.info(
            "Klassifikationen wie 'mögliche kalte Abstellung' werden bereits dokumentiert. "
            "Sie verändern das Export-Gate noch nicht automatisch. Dafür müssen zuerst verbindliche "
            "fachliche Grenzwerte festgelegt werden."
        )
        if CHANGE_LOG_PATH.exists():
            try:
                change_log = pd.read_csv(CHANGE_LOG_PATH, sep=";", dtype=str, encoding="utf-8-sig").fillna("")
                st.dataframe(change_log, use_container_width=True, hide_index=True)
            except Exception as error:
                st.warning(f"Änderungsprotokoll konnte nicht gelesen werden: {error}")
