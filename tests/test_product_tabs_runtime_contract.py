from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import product_tabs_runtime_module as product_tabs  # noqa: E402


BASE_LABELS = [
    "1. Tagesprüfung",
    "2. Offene Aufgaben",
    "3. Fall bearbeiten",
    "4. Lok prüfen",
]
EXPECTED_PRODUCT_LABELS = [
    "1. Tagesprüfung",
    "2. Offene Aufgaben",
    "3. Fall bearbeiten",
    "4. Lok prüfen",
    "5. Exporte erstellen",
    "⚙️ Technik",
]


def test_product_tabs_add_export_and_tech_once_after_loco_tab():
    visible, waterfall_index, timeline_index = product_tabs._visible_tab_labels(BASE_LABELS)

    assert visible == EXPECTED_PRODUCT_LABELS
    assert waterfall_index is None
    assert timeline_index is None
    assert visible.count("5. Exporte erstellen") == 1
    assert visible.count("⚙️ Technik") == 1


def test_product_tabs_normalize_duplicate_export_and_tech_labels_on_rerun():
    rerun_labels = [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Exporte erstellen",
        "⚙️ Technik",
        "7. Exporte erstellen",
        "⚙️ Technik",
    ]

    visible, waterfall_index, timeline_index = product_tabs._visible_tab_labels(rerun_labels)

    assert visible == EXPECTED_PRODUCT_LABELS
    assert waterfall_index is None
    assert timeline_index is None
    assert visible.count("5. Exporte erstellen") == 1
    assert visible.count("⚙️ Technik") == 1


def test_product_tabs_remove_legacy_inserted_product_tabs_from_labels():
    legacy_labels = [
        "1. Tagesprüfung",
        "2. Offene Aufgaben",
        "3. Fall bearbeiten",
        "4. Lok prüfen",
        "5. Wasserfall",
        "6. Lok-Zeitachse",
        "7. Exporte erstellen",
        "⚙️ Technik",
    ]

    visible, waterfall_index, timeline_index = product_tabs._visible_tab_labels(legacy_labels)

    assert visible == EXPECTED_PRODUCT_LABELS
    assert waterfall_index is None
    assert timeline_index is None
    assert "5. Wasserfall" not in visible
    assert "6. Lok-Zeitachse" not in visible


def test_product_tabs_leave_unrelated_tab_sets_unchanged():
    labels = ["A", "B", "⚙️ Technik", "7. Exporte erstellen"]

    visible, waterfall_index, timeline_index = product_tabs._visible_tab_labels(labels)

    assert visible == labels
    assert waterfall_index is None
    assert timeline_index is None


def test_install_product_tabs_runtime_is_idempotent_and_restorable(monkeypatch):
    import streamlit as st

    rendered_label_sets: list[list[str]] = []

    def original_tabs(labels, *args, **kwargs):
        rendered_label_sets.append([str(label) for label in labels])
        return [str(label) for label in labels]

    monkeypatch.setattr(st, "tabs", original_tabs)
    monkeypatch.setattr(product_tabs, "_PRODUCT_TABS_ORIGINAL", None)
    monkeypatch.setattr(product_tabs, "_PRODUCT_TABS_PATCHED", None)
    monkeypatch.setattr(product_tabs, "install_no_lte_assignment_policy_runtime", lambda: None)
    monkeypatch.setattr(product_tabs, "install_timeline_event_color_policy_runtime", lambda: None)

    first_original = product_tabs.install_product_tabs_runtime()
    patched_once = st.tabs
    second_original = product_tabs.install_product_tabs_runtime()

    assert first_original is original_tabs
    assert second_original is original_tabs
    assert st.tabs is patched_once
    assert getattr(st.tabs, "_product_tabs_runtime_installed", False) is True

    tabs = st.tabs(BASE_LABELS)
    assert tabs == EXPECTED_PRODUCT_LABELS
    assert rendered_label_sets[-1] == EXPECTED_PRODUCT_LABELS

    tabs = st.tabs(
        [
            "1. Tagesprüfung",
            "2. Offene Aufgaben",
            "3. Fall bearbeiten",
            "4. Lok prüfen",
            "5. Exporte erstellen",
            "⚙️ Technik",
            "7. Exporte erstellen",
            "⚙️ Technik",
        ]
    )
    assert tabs == EXPECTED_PRODUCT_LABELS
    assert rendered_label_sets[-1] == EXPECTED_PRODUCT_LABELS

    product_tabs.restore_product_tabs_runtime(second_original)
    assert st.tabs is original_tabs

    reinstalled_original = product_tabs.install_product_tabs_runtime()
    try:
        assert reinstalled_original is original_tabs
        assert st.tabs is not original_tabs
        tabs = st.tabs(BASE_LABELS)
        assert tabs == EXPECTED_PRODUCT_LABELS
        assert rendered_label_sets[-1] == EXPECTED_PRODUCT_LABELS
    finally:
        product_tabs.restore_product_tabs_runtime(reinstalled_original)

    assert st.tabs is original_tabs
