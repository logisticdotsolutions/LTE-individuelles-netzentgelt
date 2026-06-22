from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
import getpass
import uuid

import pandas as pd
import streamlit as st


OVERLAP_WORKFLOW_MARKER = "NETZENTGELT_OVERLAP_CORRECTION_WORKFLOW_PHASE11P_V2_20260618"


def install_overlap_correction_workflow() -> None:
    """Show a direct date/time correction mask for already selected R011 cases."""
    import manual_override_ui_module as ui

    if getattr(ui, "_PHASE11P_OVERLAP_WORKFLOW_PATCHED_V2", False):
        return

    original_render_new_override = ui._render_new_override

    def parse_dt(value: object) -> datetime | None:
        text = ui._clean(value)
        if not text:
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed).to_pydatetime().replace(tzinfo=None)

    def dt_text(value: object) -> str:
        parsed = parse_dt(value)
        return "" if parsed is None else parsed.strftime("%Y-%m-%dT%H:%M:%S")

    def case_from_state(cases: pd.DataFrame) -> pd.Series | None:
        selected_label = str(st.session_state.get("manual_override_case_select", ""))
        if not selected_label or cases is None or cases.empty:
            return None
        matches = cases[cases["case_label"].astype(str).eq(selected_label)]
        return None if matches.empty else matches.iloc[0]

    def overlap_rows(selected_case: pd.Series, timeline: pd.DataFrame) -> pd.DataFrame:
        loco = ui._clean(selected_case.get("loco_no"))
        selected_start = parse_dt(selected_case.get("period_start_utc"))
        selected_end = parse_dt(selected_case.get("period_end_utc"))
        if timeline is None or timeline.empty or "row_type" not in timeline.columns:
            return pd.DataFrame([selected_case.to_dict()])
        rows = timeline[timeline["row_type"].fillna("").astype(str).str.upper().eq("MOVEMENT")].copy()
        if loco and "loco_no" in rows.columns:
            rows = rows[rows["loco_no"].fillna("").astype(str).str.strip().eq(loco)].copy()
        if selected_start and selected_end:
            starts = pd.to_datetime(rows.get("period_start_utc", pd.Series("", index=rows.index)), errors="coerce")
            ends = pd.to_datetime(rows.get("period_end_utc", pd.Series("", index=rows.index)), errors="coerce")
            rows = rows[starts.lt(selected_end) & ends.gt(selected_start)].copy()
        transport = ui._clean(selected_case.get("transport_number"))
        if rows.empty and transport and "transport_number" in timeline.columns:
            rows = timeline[timeline["transport_number"].fillna("").astype(str).str.strip().eq(transport)].copy()
        if rows.empty:
            rows = pd.DataFrame([selected_case.to_dict()])
        rows["_start"] = pd.to_datetime(rows.get("period_start_utc", pd.Series("", index=rows.index)), errors="coerce")
        return rows.sort_values(["_start", "transport_number"], na_position="last").reset_index(drop=True)

    def display_rows(rows: pd.DataFrame) -> pd.DataFrame:
        result = pd.DataFrame()
        result["Transport"] = rows.get("transport_number", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Lok"] = rows.get("loco_no", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Nutzendes EVU"] = rows.get("performing_ru", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Abfahrt"] = pd.to_datetime(rows.get("period_start_utc", pd.Series("", index=rows.index)), errors="coerce").dt.strftime("%d.%m.%Y %H:%M")
        result["Ankunft"] = pd.to_datetime(rows.get("period_end_utc", pd.Series("", index=rows.index)), errors="coerce").dt.strftime("%d.%m.%Y %H:%M")
        return result.fillna("")

    def write_override(*, override_type: str, row: pd.Series, new_value: str, comment: str, created_by: str) -> str:
        now = ui.utc_now_text()
        override_id = "OVR_" + uuid.uuid4().hex[:12].upper()
        new_row = {
            "override_id": override_id,
            "active_flag": "Y",
            "override_type": override_type,
            "transport_number": ui._clean(row.get("transport_number")),
            "target_loco_no": ui._clean(row.get("loco_no")),
            "target_actual_departure_utc": dt_text(row.get("period_start_utc")),
            "target_actual_arrival_utc": dt_text(row.get("period_end_utc")),
            "target_source_table": ui._clean(row.get("source_table")),
            "target_source_row_id": ui._clean(row.get("source_row_id")),
            "override_value": new_value,
            "classification_code": "",
            "comment": comment.strip(),
            "created_by": created_by.strip() or getpass.getuser(),
            "created_at_utc": now,
            "updated_at_utc": now,
        }
        data = pd.concat([ui._read_overrides(), pd.DataFrame([new_row])], ignore_index=True)
        ui._write_overrides_atomic(data)
        ui._append_change_log(
            action="CREATE_OVERLAP_CORRECTION",
            override_id=override_id,
            override_type=override_type,
            changed_by=new_row["created_by"],
            comment=new_row["comment"],
        )
        return override_id

    def render_r011_mask(*, selected_case: pd.Series, timeline: pd.DataFrame, run_all_script: Path) -> None:
        st.markdown("### Neue lokale Korrektur")
        st.caption("Die Original-CSV-Dateien bleiben unverändert. Die Korrektur wirkt erst nach einer Neuberechnung.")
        cases = ui._build_case_table(findings=pd.DataFrame([selected_case.to_dict()]), timeline=pd.DataFrame())
        st.selectbox("Prüffall oder freie Erfassung", [st.session_state.get("manual_override_case_select", selected_case.get("case_label", "R011"))], key="manual_override_case_select_r011_readonly", disabled=True)
        st.markdown("### Überschneidung anpassen")
        st.caption("Keine zweite Auswahl der Bearbeitungsart. Korrigiere direkt die falsche Abfahrts- oder Ankunftszeit.")
        rows = overlap_rows(selected_case, timeline)
        st.dataframe(display_rows(rows), use_container_width=True, hide_index=True)
        labels = rows.apply(lambda r: f"Transport {ui._clean(r.get('transport_number')) or '-'} | {ui._clean(r.get('performing_ru')) or '-'} | {dt_text(r.get('period_start_utc')) or '-'} bis {dt_text(r.get('period_end_utc')) or '-'}", axis=1).tolist()
        with st.form("manual_overlap_correction_form"):
            chosen = st.selectbox("Welche Bewegung ist falsch?", labels)
            target = rows.iloc[labels.index(chosen)]
            field = st.selectbox("Welche Zeit soll korrigiert werden?", ["Ankunftszeit korrigieren", "Abfahrtszeit korrigieren"])
            current = target.get("period_end_utc") if field.startswith("Ankunft") else target.get("period_start_utc")
            parsed = parse_dt(current) or datetime.now().replace(second=0, microsecond=0)
            col_date, col_time = st.columns(2)
            with col_date:
                new_date = st.date_input("Neues Datum", value=parsed.date())
            with col_time:
                new_time = st.time_input("Neue Uhrzeit", value=parsed.time().replace(microsecond=0), step=60)
            new_dt = datetime.combine(new_date, time(new_time.hour, new_time.minute, 0))
            new_value = new_dt.strftime("%Y-%m-%dT%H:%M:%S")
            st.info(f"Neuer Zeitwert: **{new_value}**")
            departure = parse_dt(target.get("period_start_utc"))
            arrival = parse_dt(target.get("period_end_utc"))
            check_departure = new_dt if field.startswith("Abfahrts") else departure
            check_arrival = new_dt if field.startswith("Ankunft") else arrival
            invalid = bool(check_departure and check_arrival and check_departure >= check_arrival)
            if invalid:
                st.error("Abfahrt muss vor Ankunft liegen.")
            comment = st.text_area("Begründung / Kommentar")
            created_by = st.text_input("Bearbeiter", value=getpass.getuser())
            save = st.form_submit_button("Korrektur speichern", disabled=invalid)
            save_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary", disabled=invalid)
        if not (save or save_rebuild):
            return
        if not comment.strip():
            st.error("Bitte eine Begründung erfassen.")
            return
        override_type = "SET_ACTUAL_ARRIVAL" if field.startswith("Ankunft") else "SET_ACTUAL_DEPARTURE"
        override_id = write_override(override_type=override_type, row=target, new_value=new_value, comment=comment, created_by=created_by)
        st.success(f"Lokale Zeitkorrektur {override_id} wurde gespeichert.")
        if save_rebuild:
            with st.status("Werte werden mit der lokalen Korrektur sicher neu berechnet ...", expanded=True) as status:
                result = ui._run_pipeline(Path(run_all_script))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)

    def patched_render_new_override(*, db_path: Path, run_all_script: Path, findings: pd.DataFrame, timeline: pd.DataFrame) -> None:
        if isinstance(st.session_state.get("manual_override_suggestion_prefill"), dict) and st.session_state.get("manual_override_suggestion_prefill"):
            return original_render_new_override(db_path=db_path, run_all_script=run_all_script, findings=findings, timeline=timeline)
        cases = ui._build_case_table(findings=findings, timeline=timeline)
        selected_case = case_from_state(cases)
        if selected_case is not None and ui._clean(selected_case.get("rule_id")).upper() == "R011":
            return render_r011_mask(selected_case=selected_case, timeline=timeline, run_all_script=run_all_script)
        return original_render_new_override(db_path=db_path, run_all_script=run_all_script, findings=findings, timeline=timeline)

    ui._render_new_override = patched_render_new_override
    ui._PHASE11P_OVERLAP_WORKFLOW_PATCHED_V2 = True
