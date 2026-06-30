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


def test_product_tabs_remain_stable_after_review_tab_has_been_removed():
    labels_after_review_removal = [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Exporte erstellen",
        "⚙️ Technik",
    ]

    first_visible, first_waterfall_index, first_timeline_index = _visible_tab_labels(
        labels_after_review_removal
    )
    second_visible, second_waterfall_index, second_timeline_index = _visible_tab_labels(
        labels_after_review_removal
    )

    assert first_visible == second_visible == [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Wasserfall",
        "6. Lok-Zeitachse",
        "7. Exporte erstellen",
        "⚙️ Technik",
    ]
    assert first_waterfall_index == second_waterfall_index == 4
    assert first_timeline_index == second_timeline_index == 5
    assert first_visible.count("7. Exporte erstellen") == 1
    assert first_visible.count("⚙️ Technik") == 1
    assert "Prüfqueue" not in first_visible
    assert "6. Weitere Prüfungen" not in first_visible
