from __future__ import annotations
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
