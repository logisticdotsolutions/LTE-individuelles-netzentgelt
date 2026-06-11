from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from browser_title_module import DEFAULT_BROWSER_TITLE, browser_title_script  # noqa: E402


def test_browser_title_script_contains_fachliche_title() -> None:
    script = browser_title_script(DEFAULT_BROWSER_TITLE)
    prefix = "<script>window.parent.document.title = "
    suffix = ";</script>"

    assert script.startswith(prefix)
    assert script.endswith(suffix)
    assert json.loads(script[len(prefix) : -len(suffix)]) == DEFAULT_BROWSER_TITLE
    assert "document.title" in script
