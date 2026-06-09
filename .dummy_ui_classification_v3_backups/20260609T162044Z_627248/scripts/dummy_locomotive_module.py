from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable
ROOT = Path(__file__).resolve().parents[1]
DUMMY_MAPPING_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotives.csv"
MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"
DEFAULT_DUMMY_LOCOMOTIVES = (
    "00000000001-8",
)
def _ensure_mapping_csv() -> None:
    pass

def _read_mapping_rows() -> list[dict[str, str]]:
    return []
