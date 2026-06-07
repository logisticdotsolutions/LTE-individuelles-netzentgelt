from __future__ import annotations

import py_compile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app" / "app.py"
MODULE_PATH = ROOT / "scripts" / "rest_export_module.py"
MARKER = "NETZENTGELT_REST_EXPORT_PHASE4_V1_20260607"


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
    require_contains(APP_PATH, 'st.markdown("### Rest")')
    require_contains(APP_PATH, 'Restzeilen je PerformingRU')
    require_contains(APP_PATH, 'OrderOwner')
    require_contains(MODULE_PATH, 'PRIMARY_EXPORT_GROUPS')
    require_contains(MODULE_PATH, 'list_rest_export_overview')
    require_contains(MODULE_PATH, 'LTE_DE')
    require_contains(MODULE_PATH, 'LTE_NL')

    print("Rest-Export Phase 4 erfolgreich validiert.")
    print("- app/app.py kompiliert")
    print("- scripts/rest_export_module.py kompiliert")
    print("- Sichtbare Hauptgruppen: LTE DE, LTE NL und Rest")
    print("- Restübersicht: PerformingRU sowie optional OrderOwner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
