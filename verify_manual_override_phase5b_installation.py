#!/usr/bin/env python3
"""Statische Installationsprüfung für Netzentgelt MVP Phase 5B."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys


EXPECTED = {
    "scripts/manual_override_ui_module.py": "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607",
    "scripts/manual_override_suggestion_module.py": "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_SUGGESTIONS_V1_20260607",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    return parser.parse_args()


def syntax_check(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    ast.parse(text.replace("\r\n", "\n").replace("\r", "\n"), filename=str(path))


def main() -> int:
    root = Path(parse_args().project_root).resolve()
    for relative, marker in EXPECTED.items():
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Installationsprüfung fehlgeschlagen: Datei fehlt: {relative}")
        text = path.read_text(encoding="utf-8")
        if marker not in text:
            raise RuntimeError(f"Installationsprüfung fehlgeschlagen: Marker fehlt in {relative}: {marker}")
        syntax_check(path)
        print(f"OK: {relative}")

    app_path = root / "app" / "app.py"
    run_all_path = root / "scripts" / "run_all.py"
    foundation_path = root / "scripts" / "manual_override_module.py"
    for path in [app_path, run_all_path, foundation_path]:
        if not path.exists():
            raise RuntimeError(f"Grundlage fehlt: {path.relative_to(root)}")
        syntax_check(path)

    app_text = app_path.read_text(encoding="utf-8")
    if "from manual_override_ui_module import render_manual_override_cockpit" not in app_text:
        raise RuntimeError("app/app.py enthält die Cockpitintegration nicht.")

    run_all_text = run_all_path.read_text(encoding="utf-8")
    for expected in ["import_manual_overrides", "apply_raw_manual_overrides", "apply_staging_manual_overrides"]:
        if expected not in run_all_text:
            raise RuntimeError(f"scripts/run_all.py enthält die Phase-5A-Grundlage nicht: {expected}")

    sys.path.insert(0, str(root / "scripts"))
    from manual_override_suggestion_module import (  # noqa: PLC0415
        COLD_STAND_MIN_MINUTES,
        BORDER_SLOT_MINUTES,
        SUGGESTION_COLUMNS,
    )

    assert COLD_STAND_MIN_MINUTES == 480
    assert BORDER_SLOT_MINUTES == 15
    assert "confidence" in SUGGESTION_COLUMNS
    assert "automation_policy" in SUGGESTION_COLUMNS

    print("INSTALLATION VERIFY OK")
    print("- Cockpit Phase 5B vorhanden")
    print("- Vorschlags-Engine vorhanden")
    print("- Phase-5A-Grundlage weiterhin eingebunden")
    print("- Syntaxprüfung erfolgreich")
    print("- Schwellwert kalte Abstellung: 480 Minuten")
    print("- Grenzzeit-Prüfraster: 15 Minuten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
