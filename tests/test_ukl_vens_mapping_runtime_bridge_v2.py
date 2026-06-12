from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ukl_vens_mapping_runtime_bridge_v2 as module


def test_runtime_bridge_accepts_positional_fetch_arguments(monkeypatch):
    calls = []

    def original_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return [{
            "performing_ru": "LTE DE - LTE Germany GmbH",
            "usage_start": "2026-06-09T12:00:00Z",
            "user_vens": "STATIC",
        }]

    monkeypatch.setattr(module.n01, "_fetch_usage_segments", original_fetch)
    monkeypatch.setattr(
        module,
        "apply_vens_mapping",
        lambda rows, timestamp_keys: [dict(rows[0], user_vens="MAPPED")],
    )

    runtime = module.install_vens_mapping_runtime()
    try:
        result = module.n01._fetch_usage_segments("connection", date_from="2026-06-09")
    finally:
        module.restore_vens_mapping_runtime(runtime)

    assert calls == [(('connection',), {"date_from": "2026-06-09"})]
    assert result[0]["user_vens"] == "MAPPED"
    assert module.n01._fetch_usage_segments is original_fetch


def test_preview_mapping_is_restored(monkeypatch):
    original = lambda *args, **kwargs: pd.DataFrame()
    monkeypatch.setattr(module.preview, "build_zuordnungen_holding_preview", original)
    runtime = module.install_vens_mapping_runtime()
    module.restore_vens_mapping_runtime(runtime)
    assert module.preview.build_zuordnungen_holding_preview is original
