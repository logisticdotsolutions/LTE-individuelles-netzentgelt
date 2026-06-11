from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import technical_loco_fallback_runtime_module as fallback  # noqa: E402


def test_build_technical_loco_fallback_combines_r012_and_catalog(tmp_path: Path, monkeypatch) -> None:
    findings_path = tmp_path / "dq_findings.csv"
    pd.DataFrame(
        [
            {
                "rule_id": "R012",
                "loco_no": "91850000002-4",
                "transport_number": "T1",
                "severity": "ERROR",
                "message": "Dummy-Lok",
                "period_start_utc": "2026-06-10T08:15:00Z",
            },
            {
                "rule_id": "R011",
                "loco_no": "91806189001-1",
                "transport_number": "T2",
                "severity": "ERROR",
                "message": "Overlap",
                "period_start_utc": "2026-06-10T09:00:00Z",
            },
        ]
    ).to_csv(findings_path, sep=";", index=False, encoding="utf-8-sig")

    monkeypatch.setattr(
        fallback,
        "_read_mapping_rows",
        lambda: [{"loco_no": "00000000000-0", "reason": "Bekannte Planungs-/Dummy-Loknummer"}],
    )

    result = fallback.build_technical_loco_fallback(findings_path=findings_path)

    assert result["Loknummer"].tolist() == ["00000000000-0", "91850000002-4"]
    assert result["Quelle"].tolist() == ["Aktiver Dummy-Katalog", "Aktuelle Regelqueue"]
    assert result["Datum"].tolist() == ["", "10.06.2026"]
    assert result["Zeitpunkt UTC"].tolist() == ["", "10.06.2026 08:15:00"]
    assert "91806189001-1" not in result["Loknummer"].tolist()


def test_build_technical_loco_fallback_returns_catalog_without_findings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        fallback,
        "_read_mapping_rows",
        lambda: [{"loco_no": "91850000002-4", "reason": "known"}],
    )

    result = fallback.build_technical_loco_fallback(findings_path=tmp_path / "missing.csv")

    assert result["Loknummer"].tolist() == ["91850000002-4"]
    assert result["Quelle"].tolist() == ["Aktiver Dummy-Katalog"]
    assert result["Datum"].tolist() == [""]
    assert result["Zeitpunkt UTC"].tolist() == [""]
