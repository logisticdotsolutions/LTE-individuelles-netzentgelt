from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app" / "app.py"
MODULE_PATH = ROOT / "scripts" / "operator_ui_module.py"
MARKER = "NETZENTGELT_DAU_UX_PHASE3_V1_20260607"


def require_contains(path: Path, needle: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if needle not in text:
        raise RuntimeError(f"Erwarteter Text fehlt in {path}: {needle}")


def main() -> int:
    for path in [APP_PATH, MODULE_PATH]:
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {path}")
        py_compile.compile(str(path), doraise=True)

    require_contains(APP_PATH, MARKER)
    require_contains(APP_PATH, "2. Offene Aufgaben")
    require_contains(APP_PATH, "Daten aktualisieren und neu prüfen")
    require_contains(APP_PATH, "render_operator_dashboard")
    require_contains(APP_PATH, "render_open_tasks")
    require_contains(MODULE_PATH, "Gesperrte Lok-Tage")
    require_contains(MODULE_PATH, "Globale Export-Sperren")

    print("DAU-UX Phase 3 erfolgreich validiert.")
    print("- app/app.py kompiliert")
    print("- scripts/operator_ui_module.py kompiliert")
    print("- Navigation, Tagesprüfung und Offene Aufgaben sind eingebaut")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
