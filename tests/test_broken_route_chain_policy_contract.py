from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from broken_route_chain_policy_module import is_no_lte_assignment_marker  # noqa: E402


def test_no_lte_marker_requires_explicit_text():
    assert is_no_lte_assignment_marker("Keine " + "LTE Zuordnung") is True
    assert is_no_lte_assignment_marker("R010") is False
