from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_title_module import DEFAULT_BROWSER_TITLE, browser_title_script  # noqa: E402


def test_browser_title_script_contains_fachliche_title() -> None:
    script = browser_title_script(DEFAULT_BROWSER_TITLE)

    assert "Bahnstrom Deutschland - Tagesprüfung" in script
    assert "document.title" in script
