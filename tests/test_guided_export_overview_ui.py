from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "zuordnungen_ui_runtime_bridge.py"


def test_guided_export_overview_marker_and_labels_present():
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "NETZENTGELT_GUIDED_EXPORT_OVERVIEW_PHASE14B_V1_20260624" in source
    assert "Export-Cockpit" in source
    assert "Fachliche Downloads" in source
    assert "Kontrolllisten" in source
    assert "Vorschau der Holding-Zuordnungen anzeigen" in source
