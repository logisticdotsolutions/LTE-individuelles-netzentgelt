from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
import getpass
import uuid

import pandas as pd
import streamlit as st


OVERLAP_WORKFLOW_MARKER = "NETZENTGELT_OVERLAP_CORRECTION_WORKFLOW_PHASE11P_V1_20260618"


def install_overlap_correction_workflow() -> None:
    """Route R011 cases directly into an overlap correction form."""
    import manual_override_ui_module as ui

    if getattr(ui, "_PHASE11P_OVERLAP_WORKFLOW_PATCHED", False):
        return

    original_render_new_override = ui._render_new_override

    def _parse_dt(value: object) -> datetime | None:
        text = ui._clean(value)
        if not text:
            return None
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return pd.Timestamp(parsed).to_pydatetime().replace(tzinfo=None)

    def _dt_text(value: object) -> str:
        parsed = _parse_dt(value)
        if parsed is None:
            return ""
        return parsed.strftime("%Y-%m-%dT%H:%M:%S")

    def _date_default(value: object) -> date:
        parsed = _parse_dt(value)
        return parsed.date() if parsed else datetime.now().date()

    def _time_default(value: object) -> time:
        parsed = _parse_dt(value)
        return parsed.time().replace(microsecond=0) if parsed else time(0, 0)

    def _case_finding(selected_case: pd.Series, findings: pd.DataFrame) -> pd.Series | None:
        if findings is None or findings.empty:
            return None
        work = findings.copy()
        mask = pd.Series(True, index=work.index)
        for source, target in [
            ("rule_id", "rule_id"),
            ("transport_number", "transport_number"),
            ("loco_no", "loco_no"),
            ("period_start_utc", "period_start_utc"),
            ("source_table", "source_table"),
            ("source_row_id", "source_row_id"),
        ]:
            value = ui._clean(selected_case.get(source))
            if value and target in work.columns:
                mask = mask & work[target].fillna("").astype(str).str.strip().eq(value)
        matches = work[mask]
        if matches.empty:
            # Fallback: R011 for same loco and selected start date.
            loco = ui._clean(selected_case.get("loco_no"))
            start = _parse_dt(selected_case.get("period_start_utc"))
            if not loco or start is None or "loco_no" not in work.columns:
                return None
            rule = work.get("rule_id", pd.Series("", index=work.index)).fillna("").astype(str).str.upper()
            times = pd.to_datetime(work.get("period_start_utc", pd.Series("", index=work.index)), errors="coerce")
            fallback = work[
                work["loco_no"].fillna("").astype(str).str.strip().eq(loco)
                & rule.eq("R011")
                & times.dt.date.eq(start.date())
            ]
            if fallback.empty:
                return None
            return fallback.iloc[0]
        return matches.iloc[0]

    def _transport_tokens(value: object) -> list[str]:
        text = ui._clean(value)
        if not text:
            return []
        return [part.strip() for part in text.replace(",", "|").split("|") if part.strip()]

    def _overlap_rows(selected_case: pd.Series, findings: pd.DataFrame, timeline: pd.DataFrame) -> pd.DataFrame:
        selected_transport = ui._clean(selected_case.get("transport_number"))
        selected_loco = ui._clean(selected_case.get("loco_no"))
        finding = _case_finding(selected_case, findings)
        overlap_transports = []
        if finding is not None:
            overlap_transports = _transport_tokens(finding.get("overlap_with_transport_number"))
        wanted = {value for value in [selected_transport, *overlap_transports] if value}

        rows = pd.DataFrame()
        if timeline is not None and not timeline.empty and "row_type" in timeline.columns:
            work = timeline.copy()
            mask = work["row_type"].fillna("").astype(str).str.upper().eq("MOVEMENT")
            if selected_loco and "loco_no" in work.columns:
                mask = mask & work["loco_no"].fillna("").astype(str).str.strip().eq(selected_loco)
            if wanted and "transport_number" in work.columns:
                mask_transport = work["transport_number"].fillna("").astype(str).str.strip().isin(wanted)
                rows = work[mask & mask_transport].copy()
            if rows.empty:
                start = _parse_dt(selected_case.get("period_start_utc"))
                end = _parse_dt(selected_case.get("period_end_utc"))
                if start and end:
                    work_start = pd.to_datetime(work.get("period_start_utc", pd.Series("", index=work.index)), errors="coerce")
                    work_end = pd.to_datetime(work.get("period_end_utc", pd.Series("", index=work.index)), errors="coerce")
                    rows = work[mask & work_start.lt(end) & work_end.gt(start)].copy()

        if rows.empty:
            rows = pd.DataFrame([
                {
                    "transport_number": selected_transport,
                    "loco_no": selected_loco,
                    "performing_ru": ui._clean(selected_case.get("performing_ru")),
                    "period_start_utc": ui._clean(selected_case.get("period_start_utc")),
                    "period_end_utc": ui._clean(selected_case.get("period_end_utc")),
                    "source_table": ui._clean(selected_case.get("source_table")),
                    "source_row_id": ui._clean(selected_case.get("source_row_id")),
                }
            ])
        rows["_start"] = pd.to_datetime(rows.get("period_start_utc", pd.Series("", index=rows.index)), errors="coerce")
        rows["_end"] = pd.to_datetime(rows.get("period_end_utc", pd.Series("", index=rows.index)), errors="coerce")
        rows = rows.sort_values(["_start", "transport_number"], na_position="last").drop_duplicates(
            subset=[column for column in ["transport_number", "source_table", "source_row_id"] if column in rows.columns],
            keep="first",
        )
        return rows

    def _display_overlap_rows(rows: pd.DataFrame) -> pd.DataFrame:
        if rows is None or rows.empty:
            return pd.DataFrame()
        result = pd.DataFrame()
        result["Transport"] = rows.get("transport_number", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Lok"] = rows.get("loco_no", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Nutzendes EVU"] = rows.get("performing_ru", pd.Series("", index=rows.index)).fillna("").astype(str)
        result["Abfahrt"] = pd.to_datetime(rows.get("period_start_utc", pd.Series("", index=rows.index)), errors="coerce").dt.strftime("%d.%m.%Y %H:%M").fillna(rows.get("period_start_utc", pd.Series("", index=rows.index)).fillna("").astype(str))
        result["Ankunft"] = pd.to_datetime(rows.get("period_end_utc", pd.Series("", index=rows.index)), errors="coerce").dt.strftime("%d.%m.%Y %H:%M").fillna(rows.get("period_end_utc", pd.Series("", index=rows.index)).fillna("").astype(str))
        return result

    def _save_override(ui_module, *, override_type: str, row: pd.Series, new_value: str, comment: str, created_by: str) -> str:
        now = ui_module.utc_now_text()
        override_id = "OVR_" + uuid.uuid4().hex[:12].upper()
        new_row = {
            "override_id": override_id,
            "active_flag": "Y",
            "override_type": override_type,
            "transport_number": ui_module._clean(row.get("transport_number")),
            "target_loco_no": ui_module._clean(row.get("loco_no")),
            "target_actual_departure_utc": _dt_text(row.get("period_start_utc")),
            "target_actual_arrival_utc": _dt_text(row.get("period_end_utc")),
            "target_source_table": ui_module._clean(row.get("source_table")),
            "target_source_row_id": ui_module._clean(row.get("source_row_id")),
            "override_value": new_value,
            "classification_code": "",
            "comment": comment.strip(),
            "created_by": created_by.strip() or getpass.getuser(),
            "created_at_utc": now,
            "updated_at_utc": now,
        }
        overrides = ui_module._read_overrides()
        overrides = pd.concat([overrides, pd.DataFrame([new_row])], ignore_index=True)
        ui_module._write_overrides_atomic(overrides)
        ui_module._append_change_log(
            action="CREATE_OVERLAP_CORRECTION",
            override_id=override_id,
            override_type=override_type,
            changed_by=new_row["created_by"],
            comment=new_row["comment"],
        )
        return override_id

    def _render_overlap_form(*, selected_case: pd.Series, findings: pd.DataFrame, timeline: pd.DataFrame, run_all_script: Path) -> None:
        st.markdown("### Überschneidung anpassen")
        st.caption("Wähle den konkret falschen Transport und korrigiere genau eine Zeit. Format wird über Datum/Uhrzeit-Auswahl erzwungen.")
        rows = _overlap_rows(selected_case, findings, timeline)
        st.markdown("#### Betroffene Bewegungen")
        st.dataframe(_display_overlap_rows(rows), use_container_width=True, hide_index=True)
        if rows.empty:
            st.error("Keine betroffene Bewegung gefunden.")
            return

        rows = rows.reset_index(drop=True)
        labels = rows.apply(
            lambda row: (
                f"Transport {ui._clean(row.get('transport_number')) or '-'} | "
                f"{ui._clean(row.get('performing_ru')) or '-'} | "
                f"{_dt_text(row.get('period_start_utc')) or '-'} bis {_dt_text(row.get('period_end_utc')) or '-'}"
            ),
            axis=1,
        ).tolist()

        with st.form("manual_overlap_correction_form"):
            selected_label = st.selectbox("Welche Bewegung ist falsch?", labels, key="overlap_target_movement")
            target = rows.iloc[labels.index(selected_label)]
            field_label = st.selectbox(
                "Welche Zeit soll korrigiert werden?",
                ["Ankunftszeit korrigieren", "Abfahrtszeit korrigieren"],
                key="overlap_target_field",
            )
            current_value = target.get("period_end_utc") if field_label.startswith("Ankunft") else target.get("period_start_utc")
            col_date, col_time = st.columns(2)
            with col_date:
                new_date = st.date_input("Neues Datum", value=_date_default(current_value), key="overlap_new_date")
            with col_time:
                new_time = st.time_input("Neue Uhrzeit", value=_time_default(current_value), step=60, key="overlap_new_time")
            new_dt = datetime.combine(new_date, new_time.replace(second=0, microsecond=0))
            new_value = new_dt.strftime("%Y-%m-%dT%H:%M:%S")

            st.info(f"Neuer Zeitwert: **{new_value}**")
            departure = _parse_dt(target.get("period_start_utc"))
            arrival = _parse_dt(target.get("period_end_utc"))
            corrected_departure = new_dt if field_label.startswith("Abfahrts") else departure
            corrected_arrival = new_dt if field_label.startswith("Ankunft") else arrival
            validation_errors: list[str] = []
            validation_warnings: list[str] = []
            if corrected_departure and corrected_arrival and corrected_departure >= corrected_arrival:
                validation_errors.append("Abfahrt muss vor Ankunft liegen.")

            other_rows = rows.drop(index=labels.index(selected_label), errors="ignore")
            for _, other in other_rows.iterrows():
                other_start = _parse_dt(other.get("period_start_utc"))
                other_end = _parse_dt(other.get("period_end_utc"))
                if corrected_departure and corrected_arrival and other_start and other_end:
                    if corrected_departure < other_end and other_start < corrected_arrival:
                        validation_warnings.append(
                            "Die neue Zeit überschneidet sich weiterhin mit Transport "
                            + (ui._clean(other.get("transport_number")) or "-")
                            + "."
                        )

            for error in validation_errors:
                st.error(error)
            for warning in validation_warnings:
                st.warning(warning)

            created_by = st.text_input("Bearbeiter", value=getpass.getuser(), key="overlap_created_by")
            comment = st.text_area("Begründung / Kommentar", key="overlap_comment")
            save_only = st.form_submit_button("Korrektur speichern", disabled=bool(validation_errors))
            save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary", disabled=bool(validation_errors))

        if not (save_only or save_and_rebuild):
            return
        if not comment.strip():
            st.error("Bitte eine Begründung für die lokale Korrektur erfassen.")
            return
        override_type = "SET_ACTUAL_ARRIVAL" if field_label.startswith("Ankunft") else "SET_ACTUAL_DEPARTURE"
        override_id = _save_override(
            ui,
            override_type=override_type,
            row=target,
            new_value=new_value,
            comment=comment,
            created_by=created_by,
        )
        st.success(f"Lokale Zeitkorrektur {override_id} wurde gespeichert.")
        if save_and_rebuild:
            with st.status("Werte werden mit der lokalen Korrektur sicher neu berechnet ...", expanded=True) as status:
                result = ui._run_pipeline(Path(run_all_script))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.session_state["overview_refresh_completed"] = True
                    st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.error("Der letzte produktive DuckDB-Stand bleibt erhalten.")
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)

    def patched_render_new_override(*, db_path: Path, run_all_script: Path, findings: pd.DataFrame, timeline: pd.DataFrame) -> None:
        st.markdown("### Neue lokale Korrektur")
        st.caption("Die Original-CSV-Dateien bleiben unverändert. Die Korrektur wirkt erst nach einer Neuberechnung.")
        prefill = st.session_state.get("manual_override_suggestion_prefill")
        prefill = prefill if isinstance(prefill, dict) else {}
        if prefill:
            # Systemvorschläge behalten den bestehenden, geprüften Workflow.
            return original_render_new_override(
                db_path=db_path,
                run_all_script=run_all_script,
                findings=findings,
                timeline=timeline,
            )
        cases = ui._build_case_table(findings=findings, timeline=timeline)
        selected_case_label = st.selectbox(
            "Prüffall oder freie Erfassung",
            cases["case_label"].tolist(),
            key="manual_override_case_select",
        )
        selected_case = cases[cases["case_label"].eq(selected_case_label)].iloc[0]
        if ui._clean(selected_case.get("rule_id")).upper() == "R011":
            _render_overlap_form(
                selected_case=selected_case,
                findings=findings,
                timeline=timeline,
                run_all_script=run_all_script,
            )
            return
        st.info("Für diesen Prüffall wird die Standard-Korrekturmaske verwendet.")
        # Avoid duplicating the case selector by temporarily clearing the stored selection only for this rerender.
        return original_render_new_override(
            db_path=db_path,
            run_all_script=run_all_script,
            findings=findings,
            timeline=timeline,
        )

    ui._render_new_override = patched_render_new_override
    ui._PHASE11P_OVERLAP_WORKFLOW_PATCHED = True
