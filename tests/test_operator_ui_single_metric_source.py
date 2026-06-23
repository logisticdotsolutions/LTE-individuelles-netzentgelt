from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPERATOR_UI = ROOT / "scripts" / "operator_ui_module.py"


def test_status_banner_does_not_render_duplicate_gate_metrics() -> None:
    source = OPERATOR_UI.read_text(encoding="utf-8")
    start = source.index("def render_status_banner(")
    end = source.index("def _render_loco_shortcut", start)
    function_source = source[start:end]

    assert "st.metric" not in function_source
    assert "Fachliche Tageszaehler" in function_source


def test_operator_dashboard_remains_single_metric_source() -> None:
    source = OPERATOR_UI.read_text(encoding="utf-8")
    start = source.index("def render_operator_dashboard(")
    end = source.index("def render_open_tasks", start)
    function_source = source[start:end]

    assert 'metric("Freigegebene Lok-Tage"' in function_source
    assert 'metric("Lok-Tage mit Hinweis"' in function_source
    assert 'metric("Gesperrte Lok-Tage"' in function_source
    assert 'metric("Globale Export-Sperren"' in function_source
