from __future__ import annotations
import argparse, hashlib, json, os, py_compile, shutil
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parent
MARKER_OPERATOR = 'NETZENTGELT_CONTROLLER_UI_DUMMY_LABEL_V1_20260609'
MARKER_SUGGESTIONS = 'NETZENTGELT_CONTROLLER_UI_GAP_MINUTES_V1_20260609'
MODIFIED_FILES = [Path('scripts/operator_ui_module.py'), Path('scripts/manual_override_ui_module.py')]
NEW_FILES = [Path('scripts/test_controller_ui_clarity_hotfix.py'), Path('scripts/verify_controller_ui_clarity_hotfix.py')]
ALL_FILES = MODIFIED_FILES + NEW_FILES
EXPECTED_LF_BLOBS = {
 Path('scripts/operator_ui_module.py'): '2d6537e7c3aeed0a7f4c2457bb4c86e219739bb3',
 Path('scripts/manual_override_ui_module.py'): '04b6a0acb70e0d5a7a5786743495422d4e7b42d5',
}
TEST_FILE = '''from __future__ import annotations
import sys, types
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.modules.setdefault("streamlit", types.SimpleNamespace())
import operator_ui_module as operator_ui
import manual_override_ui_module as manual_ui

def main() -> int:
    problem, action = operator_ui._friendly_rule("R012", "Planungs-/Dummy-Lok erkannt und aus fachlicher Verarbeitung ausgeschlossen.")
    assert problem == "Dummy-Lok", problem
    assert "Echte Loknummer" in action, action
    missing_problem, _ = operator_ui._friendly_rule("R012", "Loknummer fehlt.")
    assert missing_problem == "Loknummer fehlt", missing_problem
    gate = pd.DataFrame([{"gate_status":"BLOCKED","loco_no":"DUMMY-1","coverage_date":"2026-06-06","performing_rus":"","coverage_pct":0,"unresolved_gap_minutes":0,"overlap_minutes":0,"gate_reason":"ERROR-Findings=1"}])
    findings = pd.DataFrame([{"rule_id":"R012","row_type":"RAW_DUMMY_LOCOMOTIVE","loco_no":"DUMMY-1","message":"Planungs-/Dummy-Lok erkannt und aus fachlicher Verarbeitung ausgeschlossen."}])
    gate_display = operator_ui._friendly_gate_table(gate, only_status="BLOCKED", findings=findings)
    assert gate_display.loc[0, "Warum?"] == "Dummy-Lok", gate_display
    suggestions = pd.DataFrame([
      {"suggestion_type":"GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS","confidence":"HIGH","suggested_value":"LTE DE","transport_number":"T1","loco_no":"L1","period_start_utc":"2026-06-06T10:00:00","period_end_utc":"2026-06-06T10:33:00","reason":"Gap"},
      {"suggestion_type":"LOCO_NO_REVIEW","confidence":"LOW","suggested_value":"","transport_number":"T2","loco_no":"","period_start_utc":"2026-06-06T10:00:00","period_end_utc":"2026-06-06T11:00:00","reason":"Kein Gap"},
    ])
    display = manual_ui._suggestion_display_table(suggestions)
    assert "GAP-Minuten" in display.columns, display.columns
    assert int(display.loc[0, "GAP-Minuten"]) == 33, display
    assert pd.isna(display.loc[1, "GAP-Minuten"]), display
    print("OK: Dummy-Lok-Klartext und GAP-Minuten erfolgreich getestet.")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
'''
VERIFY_FILE = '''from __future__ import annotations
import py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def main() -> int:
    checks = {
      ROOT / "scripts" / "operator_ui_module.py": ["NETZENTGELT_CONTROLLER_UI_DUMMY_LABEL_V1_20260609", "Dummy-Lok", "findings: pd.DataFrame | None = None"],
      ROOT / "scripts" / "manual_override_ui_module.py": ["NETZENTGELT_CONTROLLER_UI_GAP_MINUTES_V1_20260609", "GAP-Minuten", "gap_suggestion_types"],
    }
    for path, markers in checks.items():
        if not path.exists(): print(f"FEHLER: Datei fehlt: {path}"); return 1
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text: print(f"FEHLER: Marker fehlt in {path}: {marker}"); return 1
        py_compile.compile(str(path), doraise=True)
    for name in ["test_controller_ui_clarity_hotfix.py", "verify_controller_ui_clarity_hotfix.py"]:
        py_compile.compile(str(ROOT / "scripts" / name), doraise=True)
    print("OK: UI-Hotfix-Marker und Python-Syntax erfolgreich verifiziert.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
'''
def lf_bytes(raw: bytes) -> bytes: return raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
def git_blob_sha(raw: bytes) -> str: return hashlib.sha1(b'blob ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()
def read_text(path: Path):
 raw=path.read_bytes(); nl='\r\n' if b'\r\n' in raw else '\n'; return lf_bytes(raw).decode('utf-8-sig'), nl
def encode_text(text: str, nl: str) -> bytes:
 text=text.replace('\r\n','\n').replace('\r','\n'); return (text.replace('\n','\r\n') if nl=='\r\n' else text).encode('utf-8')
def replace_once(text, old, new, label):
 c=text.count(old)
 if c!=1: raise RuntimeError(f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {c}.")
 return text.replace(old,new,1)
def patch_operator(text):
 if MARKER_OPERATOR in text: return text
 text=replace_once(text,'# NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608\n','# NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608\n# NETZENTGELT_CONTROLLER_UI_DUMMY_LABEL_V1_20260609\n','Operator-Marker')
 text=replace_once(text,'    "R012": (\n        "Loknummer fehlt oder technische Dummy-Lok wurde verwendet",\n        "Loknummer in der Transportplanung fachlich korrigieren.",\n    ),\n','    "R012": (\n        "Loknummer fehlt",\n        "Loknummer in der Transportplanung fachlich korrigieren.",\n    ),\n','R012-Grundtext')
 old='''def _friendly_rule(rule_id: object, message: object = "") -> tuple[str, str]:
    key = "" if pd.isna(rule_id) else str(rule_id).strip().upper()

    if key in RULE_TEXT:
        return RULE_TEXT[key]

    clean_message = "" if pd.isna(message) else str(message).strip()
    return (
        clean_message or "Prueffall ohne hinterlegte Klartextbeschreibung",
        "Weitere Details prüfen und fachlich bewerten.",
    )
'''
 new='''def _dummy_loco_numbers(findings: pd.DataFrame | None) -> set[str]:
    if findings is None or findings.empty:
        return set()
    rule_col = _column(findings, ["rule_id", "rule"])
    loco_col = _column(findings, ["loco_no"])
    message_col = _column(findings, ["message"])
    row_type_col = _column(findings, ["row_type"])
    if not rule_col or not loco_col:
        return set()
    rule = _normalized(findings[rule_col]).str.upper()
    message = _normalized(findings[message_col]).str.lower() if message_col else pd.Series("", index=findings.index)
    row_type = _normalized(findings[row_type_col]).str.upper() if row_type_col else pd.Series("", index=findings.index)
    dummy_mask = rule.eq("R012") & (message.str.contains("dummy", regex=False) | message.str.contains("planungs", regex=False) | row_type.eq("RAW_DUMMY_LOCOMOTIVE"))
    return {value for value in _normalized(findings.loc[dummy_mask, loco_col]).tolist() if value}

def _friendly_rule(rule_id: object, message: object = "") -> tuple[str, str]:
    key = "" if pd.isna(rule_id) else str(rule_id).strip().upper()
    clean_message = "" if pd.isna(message) else str(message).strip()
    clean_message_lower = clean_message.lower()
    if key == "R012" and ("dummy" in clean_message_lower or "planungs" in clean_message_lower):
        return ("Dummy-Lok", "Echte Loknummer beziehungsweise Planung in RailCube pruefen und korrigieren.")
    if key in RULE_TEXT:
        return RULE_TEXT[key]
    return (clean_message or "Prueffall ohne hinterlegte Klartextbeschreibung", "Weitere Details prüfen und fachlich bewerten.")
'''
 text=replace_once(text,old,new,'Dummy-Klartext')
 text=replace_once(text,'def _friendly_gate_table(export_gate: pd.DataFrame, only_status: str | None = None) -> pd.DataFrame:\n','def _friendly_gate_table(\n    export_gate: pd.DataFrame,\n    only_status: str | None = None,\n    findings: pd.DataFrame | None = None,\n) -> pd.DataFrame:\n','Gate-Signatur')
 old='''    result["Naechster Schritt"] = status.str.upper().map(
        {
            "READY": "Keine Aktion erforderlich.",
            "WARNING": "Hinweis vor dem Export fachlich kontrollieren.",
            "BLOCKED": "Lok im Detail pruefen und Ursache bereinigen.",
        }
    ).fillna("Weitere Details prüfen.")

    return result[columns].reset_index(drop=True)
'''
 new='''    result["Naechster Schritt"] = status.str.upper().map(
        {
            "READY": "Keine Aktion erforderlich.",
            "WARNING": "Hinweis vor dem Export fachlich kontrollieren.",
            "BLOCKED": "Lok im Detail pruefen und Ursache bereinigen.",
        }
    ).fillna("Weitere Details prüfen.")

    dummy_loco_numbers = _dummy_loco_numbers(findings)
    if dummy_loco_numbers:
        dummy_mask = result["Loknummer"].isin(dummy_loco_numbers)
        result.loc[dummy_mask, "Warum?"] = "Dummy-Lok"
        result.loc[dummy_mask, "Naechster Schritt"] = "Echte Loknummer beziehungsweise Planung in RailCube pruefen und korrigieren."

    return result[columns].reset_index(drop=True)
'''
 text=replace_once(text,old,new,'Gate-Dummy-Anzeige')
 text=replace_once(text,'    blocked_days = _friendly_gate_table(export_gate, only_status="BLOCKED")\n','    blocked_days = _friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)\n','Dashboard-Aufruf')
 text=replace_once(text,'    blocking_gate = _friendly_gate_table(export_gate, only_status="BLOCKED")\n    warning_gate = _friendly_gate_table(export_gate, only_status="WARNING")\n','    blocking_gate = _friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)\n    warning_gate = _friendly_gate_table(export_gate, only_status="WARNING", findings=findings)\n','Open-Tasks-Aufrufe')
 return text
def patch_manual(text):
 if MARKER_SUGGESTIONS in text: return text
 text=replace_once(text,'    result = data.copy()\n    result["confidence"] = result["confidence"].map(CONFIDENCE_LABELS).fillna(result["confidence"])\n','    result = data.copy()\n    # NETZENTGELT_CONTROLLER_UI_GAP_MINUTES_V1_20260609\n    gap_suggestion_types = {"GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS", "BROKEN_LOCATION_CHAIN", "POSSIBLE_COLD_STAND_SAME_LOCATION"}\n    suggestion_type = result.get("suggestion_type", pd.Series("", index=result.index)).fillna("").astype(str)\n    period_start = pd.to_datetime(result.get("period_start_utc", pd.Series(index=result.index, dtype="object")), errors="coerce")\n    period_end = pd.to_datetime(result.get("period_end_utc", pd.Series(index=result.index, dtype="object")), errors="coerce")\n    gap_minutes = ((period_end - period_start).dt.total_seconds() / 60).round()\n    result["GAP-Minuten"] = gap_minutes.where(suggestion_type.isin(gap_suggestion_types)).astype("Int64")\n    result["confidence"] = result["confidence"].map(CONFIDENCE_LABELS).fillna(result["confidence"])\n','GAP-Minuten-Berechnung')
 text=replace_once(text,'        "Von",\n        "Bis",\n        "Vorgeschlagener Wert",\n','        "Von",\n        "Bis",\n        "GAP-Minuten",\n        "Vorgeschlagener Wert",\n','GAP-Minuten-Spalte')
 return text
PATCHERS={Path('scripts/operator_ui_module.py'):patch_operator,Path('scripts/manual_override_ui_module.py'):patch_manual}
NEW_CONTENT={Path('scripts/test_controller_ui_clarity_hotfix.py'):TEST_FILE,Path('scripts/verify_controller_ui_clarity_hotfix.py'):VERIFY_FILE}
def is_patched(rel,text): return (rel.name=='operator_ui_module.py' and MARKER_OPERATOR in text) or (rel.name=='manual_override_ui_module.py' and MARKER_SUGGESTIONS in text)
def check_state(project):
 for rel in MODIFIED_FILES:
  path=project/rel
  if not path.exists(): raise RuntimeError(f'Datei fehlt: {rel}')
  raw=path.read_bytes(); text=lf_bytes(raw).decode('utf-8-sig')
  if is_patched(rel,text): continue
  actual=git_blob_sha(lf_bytes(raw)); expected=EXPECTED_LF_BLOBS[rel]
  if actual!=expected: raise RuntimeError(f"Lokaler Stand von '{rel}' weicht vom geprüften GitHub-Stand ab. Erwarteter Git-Blob: {expected}, LF-normalisiert lokal: {actual}. Bitte zuerst git status prüfen.")
def payload(project):
 check_state(project); result={}
 for rel in MODIFIED_FILES:
  text,nl=read_text(project/rel); result[rel]=encode_text(PATCHERS[rel](text),nl)
 for rel,text in NEW_CONTENT.items(): result[rel]=encode_text(text,'\r\n')
 return result
def make_backup(project,files):
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_%f'); backup=project/'.controller_ui_clarity_hotfix_backups'/stamp; backup.mkdir(parents=True)
 manifest={'files':[]}
 for rel in files:
  source=project/rel; existed=source.exists(); manifest['files'].append({'path':str(rel).replace('\\','/'),'existed':existed})
  if existed:
   target=backup/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
 (backup/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8'); return backup
def dry_run(project): payload(project); print('OK: Dry Run erfolgreich. Keine Datei wurde verändert.'); return 0
def apply(project):
 data=payload(project); changes=[rel for rel,raw in data.items() if not (project/rel).exists() or (project/rel).read_bytes()!=raw]
 if not changes: print('OK: UI-Hotfix ist bereits vollständig installiert.'); return 0
 backup=make_backup(project,changes)
 for rel in changes:
  target=project/rel; target.parent.mkdir(parents=True,exist_ok=True); tmp=target.with_suffix(target.suffix+'.tmp'); tmp.write_bytes(data[rel]); os.replace(tmp,target)
 print(f'OK: UI-Hotfix installiert. Backup: {backup}'); return 0
def verify(project):
 for rel in ALL_FILES:
  if not (project/rel).exists(): raise RuntimeError(f'Datei fehlt: {rel}')
  if rel.suffix=='.py': py_compile.compile(str(project/rel),doraise=True)
 print('OK: Marker und Python-Syntax erfolgreich verifiziert.'); return 0
def rollback(project):
 root=project/'.controller_ui_clarity_hotfix_backups'; backups=sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []
 if not backups: raise RuntimeError('Kein Backup für Rollback gefunden.')
 backup=backups[-1]; manifest=json.loads((backup/'manifest.json').read_text(encoding='utf-8'))
 for item in manifest['files']:
  rel=Path(item['path']); target=project/rel
  if item['existed']: target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(backup/rel,target)
  elif target.exists(): target.unlink()
 print(f'OK: Rollback aus {backup} erfolgreich.'); return 0
def main():
 p=argparse.ArgumentParser(); p.add_argument('command',choices=['dry-run','apply','verify','rollback']); p.add_argument('--root',type=Path,default=ROOT); a=p.parse_args()
 try: return globals()[a.command.replace('-','_')](a.root.resolve())
 except Exception as e: print(f'FEHLER: {e}'); return 1
if __name__=='__main__': raise SystemExit(main())
