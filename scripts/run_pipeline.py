"""Alternativer Einstieg in die modularisierte Netzentgelt-Pipeline.

Standard:
    .venv\Scripts\python.exe scripts\run_pipeline.py

Optional:
    .venv\Scripts\python.exe scripts\run_pipeline.py --mode FULL_IMPORT_REBUILD
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Sicherstellen, dass das Package scripts/pipeline auch beim direkten Start als
# Datei gefunden wird.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from pipeline.rebuild_modes import RebuildMode
from pipeline.runner import run_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Netzentgelt-Pipeline im gewaehlten Rebuild-Modus ausfuehren."
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in RebuildMode],
        default=RebuildMode.FULL_IMPORT_REBUILD.value,
        help="Rebuild-Modus. Aktuell produktiv angebunden: FULL_IMPORT_REBUILD.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_pipeline(RebuildMode(args.mode))


if __name__ == "__main__":
    main()
