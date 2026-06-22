from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_VERIFY_V2_20260609"


def require_text(path: Path, values: list[str]) -> None:
    if not path.exists():
        raise RuntimeError(f"Datei fehlt: {path}")
    text = path.read_text(encoding="utf-8-sig")
    for value in values:
        if value not in text:
            raise RuntimeError(f"Marker fehlt in {path}: {value}")


def main() -> int:
    require_text(
        ROOT / "scripts" / "dummy_locomotive_module.py",
        ["NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609", "upsert_dummy_locomotive_mapping"],
    )
    require_text(
        ROOT / "scripts" / "manual_override_ui_module.py",
        ["NETZENTGELT_DUMMY_UI_CLASSIFICATION_V2_20260609", "MARK_DUMMY_LOCOMOTIVE"],
    )
    require_text(ROOT / "data" / "01_mapping" / "dummy_locomotives.csv", ["91806189000-3;"])
    print("OK: Dummy-UI-Klassifikation, Katalogeintrag und UI-Aktion verifiziert.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
