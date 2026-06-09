from __future__ import annotations
import importlib.util, shutil, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installer', ROOT/'apply_controller_ui_clarity_hotfix.py')
installer=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(installer)
OP='''from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import pandas as pd
import streamlit as st
DAU_UX_MARKER = "NETZENTGELT_DAU_UX_PHASE3_V1_20260607"
# NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608
RULE_TEXT = {
    "R012": (
        "Loknummer fehlt oder technische Dummy-Lok wurde verwendet",
        "Loknummer in der Transportplanung fachlich korrigieren.",
    ),
}
def _column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    if df is None or df.empty: return None
    by_lower={str(name).lower():str(name) for name in df.columns}
    for candidate in candidates:
        if candidate.lower() in by_lower: return by_lower[candidate.lower()]
    return None
def _normalized(series: pd.Series) -> pd.Series: return series.fillna("").astype(str).str.strip()
def _friendly_gate_reason(value: object) -> str: return "" if pd.isna(value) else str(value).strip()
def _friendly_rule(rule_id: object, message: object = "") -> tuple[str, str]:
    key = "" if pd.isna(rule_id) else str(rule_id).strip().upper()

    if key in RULE_TEXT:
        return RULE_TEXT[key]

    clean_message = "" if pd.isna(message) else str(message).strip()
    return (
        clean_message or "Prueffall ohne hinterlegte Klartextbeschreibung",
        "Weitere Details prüfen und fachlich bewerten.",
    )
def _format_date_series(series): return series
def _friendly_gate_table(export_gate: pd.DataFrame, only_status: str | None = None) -> pd.DataFrame:
    columns=["Status","Loknummer","Datum","Nutzendes EVU","Zeitliche Abdeckung","Ungeklaerte Minuten","Ueberschneidungsminuten","Warum?","Naechster Schritt"]
    work=export_gate.copy(); status_col='gate_status'; loco_col='loco_no'; reason_col='gate_reason'; status=_normalized(work[status_col]); reason=work[reason_col].apply(_friendly_gate_reason)
    result=pd.DataFrame(index=work.index); result["Status"]=status; result["Loknummer"]=_normalized(work[loco_col]); result["Warum?"]=reason
    result["Naechster Schritt"] = status.str.upper().map(
        {
            "READY": "Keine Aktion erforderlich.",
            "WARNING": "Hinweis vor dem Export fachlich kontrollieren.",
            "BLOCKED": "Lok im Detail pruefen und Ursache bereinigen.",
        }
    ).fillna("Weitere Details prüfen.")

    return result[columns].reset_index(drop=True)
def render_operator_dashboard(export_gate, findings):
    blocked_days = _friendly_gate_table(export_gate, only_status="BLOCKED")
def render_open_tasks(export_gate, findings):
    blocking_gate = _friendly_gate_table(export_gate, only_status="BLOCKED")
    warning_gate = _friendly_gate_table(export_gate, only_status="WARNING")
'''
MAN='''from __future__ import annotations
import pandas as pd
CONFIDENCE_LABELS={"HIGH":"Hoch","LOW":"Niedrig"}
SUGGESTION_TYPE_LABELS={}
def _suggestion_display_table(data: pd.DataFrame) -> pd.DataFrame:
    """Controller-taugliche Vorschlagsliste ohne technische Hilfsspalten."""
    if data.empty:
        return data
    result = data.copy()
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
        "Vorgeschlagener Wert",
        "Begründung",
    ]
    return result[[column for column in visible_columns if column in result.columns]]
'''
def crlf(t): return t.replace('\n','\r\n').encode('utf-8')
def main():
 with tempfile.TemporaryDirectory() as tmp:
  project=Path(tmp); (project/'scripts').mkdir()
  (project/'scripts/operator_ui_module.py').write_bytes(crlf(OP)); (project/'scripts/manual_override_ui_module.py').write_bytes(crlf(MAN))
  originals={rel:(project/rel).read_bytes() for rel in installer.MODIFIED_FILES}
  installer.EXPECTED_LF_BLOBS={rel:installer.git_blob_sha(installer.lf_bytes(raw)) for rel,raw in originals.items()}
  assert installer.dry_run(project)==0
  assert installer.apply(project)==0
  assert installer.verify(project)==0
  assert installer.apply(project)==0
  assert installer.rollback(project)==0
  for rel,raw in originals.items(): assert (project/rel).read_bytes()==raw, rel
 print('OK: Paket-Selbsttest Dry-Run, Apply, Syntax, CRLF, Idempotenz und Rollback erfolgreich.')
 return 0
if __name__=='__main__': raise SystemExit(main())
