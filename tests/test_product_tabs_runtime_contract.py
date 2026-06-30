from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from product_tabs_runtime_module import _visible_tab_labels  # noqa: E402


def test_product_tabs_insert_waterfall_and_timeline_once_before_exports():
    labels = [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Exporte erstellen",
        "⚙️ Technik",
    ]

    visible, waterfall_index, timeline_index = _visible_tab_labels(labels)

    assert waterfall_index == 4
    assert timeline_index == 5
    assert visible == [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Wasserfall",
        "6. Lok-Zeitachse",
        "7. Exporte erstellen",
        "⚙️ Technik",
    ]
    assert visible.count("7. Exporte erstellen") == 1
    assert visible.count("⚙️ Technik") == 1


def test_product_tabs_do_not_reinsert_on_rerun_labels():
    labels = [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Wasserfall",
        "6. Lok-Zeitachse",
        "7. Exporte erstellen",
        "⚙️ Technik",
    ]

    visible, waterfall_index, timeline_index = _visible_tab_labels(labels)

    assert visible == labels
    assert waterfall_index is None
    assert timeline_index is None
    assert visible.count("5. Wasserfall") == 1
    assert visible.count("6. Lok-Zeitachse") == 1
    assert visible.count("7. Exporte erstellen") == 1
    assert visible.count("⚙️ Technik") == 1
