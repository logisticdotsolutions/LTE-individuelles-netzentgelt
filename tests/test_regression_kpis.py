from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.smoke_support import run_isolated_pipeline


@pytest.mark.regression
def test_defined_smoke_kpis_remain_stable(monkeypatch, tmp_path: Path):
    expected_path = Path(__file__).resolve().parent / "fixtures" / "regression_expected.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    _, actual = run_isolated_pipeline(monkeypatch, tmp_path)
    assert actual == expected
