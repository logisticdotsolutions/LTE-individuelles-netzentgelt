from datetime import date, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import t01_preview_module as preview
import t01_ui_runtime_bridge as ui
import zuordnungen_ui_runtime_bridge as export_ui


def test_t01_preview_keeps_blocked_rows_visible(monkeypatch, tmp_path):
    db_path = tmp_path / "netzentgelt.duckdb"
    db_path.touch()
    monkeypatch.setattr(preview, "list_t01_performing_rus", lambda **kwargs: ["LTE DE - LTE Germany GmbH"])
    monkeypatch.setattr(preview.duckdb, "connect", lambda *args, **kwargs: object())
    monkeypatch.setattr(preview, "_raw_rows_without_gate", lambda *args, **kwargs: [{}])
    monkeypatch.setattr(preview, "enrich_t01_rows", lambda rows: [{
        "locomotive_no": "91801234567-8",
        "performing_ru": "LTE DE - LTE Germany GmbH",
        "departure_ts": datetime(2026, 6, 9, 8, 0),
        "departure_location": "8000261",
        "arrival_ts": datetime(2026, 6, 9, 10, 0),
        "arrival_location": "8000207",
        "distance_km": 120.0,
        "trailer_weight_t": 900.0,
        "train_no": "4711",
        "transport_number": "T-1",
        "user_vens": None,
        "order_criterion": None,
        "usage_type": None,
        "max_speed_kmh": None,
        "traffic_day": date(2026, 6, 9),
        "is_multiple_unit": False,
    }])

    class DummyCon:
        def close(self):
            pass
    monkeypatch.setattr(preview.duckdb, "connect", lambda *args, **kwargs: DummyCon())
    result = preview.build_t01_preview(db_path=db_path, date_from=date(2026, 6, 9), date_to=date(2026, 6, 9))
    assert result.iloc[0]["Exportstatus"] == "BLOCKIERT"
    assert "T01_VENS_REQUIRED" in result.iloc[0]["Hinweis"]
    assert "T01_ORDER_CRITERION_REQUIRED" in result.iloc[0]["Hinweis"]


def test_t01_ui_runtime_wraps_and_restores_renderer(monkeypatch):
    original = lambda: None
    monkeypatch.setattr(export_ui, "render_zuordnungen_export_extension", original)
    runtime = ui.install_t01_export_ui_extension()
    try:
        assert export_ui.render_zuordnungen_export_extension is not original
    finally:
        ui.restore_t01_export_ui_extension(runtime)
    assert export_ui.render_zuordnungen_export_extension is original
