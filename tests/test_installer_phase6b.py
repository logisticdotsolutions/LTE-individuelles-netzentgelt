from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
# NETZENTGELT_HISTORICAL_INSTALLER_TEST_SKIP_V1_20260609
INSTALLER_PATH = PKG / 'apply_rule_engine_hardening_phase6b.py'
installer = None
if INSTALLER_PATH.exists():
    spec = importlib.util.spec_from_file_location('installer', INSTALLER_PATH)
    installer = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(installer)

def test_historical_phase6b_installer_artifact():
    if installer is None:
        import pytest
        pytest.skip('Historischer Phase-6B-Installer wurde beim Repository-Cleanup entfernt.')


def write_crlf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace('\n', '\r\n').encode('utf-8'))


def main() -> int:
    if installer is None:
        print('SKIP: historischer Phase-6B-Installer wurde beim Repository-Cleanup entfernt.')
        return 0
    with tempfile.TemporaryDirectory() as tmp_text:
        root = Path(tmp_text)
        shutil.copytree(PKG / 'payload', root / 'payload')
        run_all = "\n".join([
            "from manual_override_module import (",
            "    apply_raw_manual_overrides,",
            "    apply_staging_manual_overrides,",
            "    import_manual_overrides,",
            ")",
            "",
            "def build():",
            "        build_core(con, run_id)",
            "        build_unresolved_performing_ru_market_partner_alias(con)",
            "        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)",
            "        build_quality_gate_tables(con, run_id)",
            "        rows = [",
            "            (\"audit_manual_override_application\", \"audit_manual_override_application.csv\"),",
            "            (\"stg_loco_events\", \"stg_loco_events.csv\"),",
            "        ]",
            "",
            "def gaps():",
            "    sql = f\"\"\"",
            "                coalesce(period_end_utc, sequence_ts) as gap_from,",
            "                coalesce(next_period_start_utc, next_sequence_ts) as gap_to",
            "    \"\"\"",
            "",
        ])
        quality = '''def build():\n    sql = """\n                  and coalesce(export_ready, false) = false\n            count(*) filter (where coalesce(export_ready, false) = false)\n                as not_export_ready_movement_rows\n    """\n'''
        export = '''def build():\n    sql = """\n                         and coalesce(export_ready, false) = false\n    """\n'''
        manual = '''from __future__ import annotations\n\ndef _clean(value):\n    return str(value or "").strip()\n\ndef table(findings, timeline):\n    rows = []\n    if findings is not None:\n        for _, row in findings.iterrows():\n            rows.append({\n                "loco_no": _clean(row.get("loco_no")),\n                "period_start_utc": _clean(row.get("period_start_utc")),\n                "period_end_utc": _clean(row.get("period_end_utc")),\n                "source_table": _clean(row.get("source_table")),\n                "source_row_id": _clean(row.get("source_row_id")),\n            })\n    if timeline is not None and not timeline.empty and "row_type" in timeline.columns:\n        # NETZENTGELT_GAP_SCOPE_UI_HOTFIX_V1_20260608\n        gap_mask = timeline["row_type"].fillna("").astype(str).str.upper().eq("GAP")\n        if "gap_relevant_de" in timeline.columns:\n            gap_mask = gap_mask\n        gap_rows = timeline[gap_mask]\n        for _, row in gap_rows.iterrows():\n            loco = _clean(row.get("loco_no"))\n            start = _clean(row.get("period_start_utc"))\n            end = _clean(row.get("period_end_utc"))\n            rows.append(\n                {"loco_no": loco, "period_start_utc": start, "period_end_utc": end, "source_table": _clean(row.get("source_table")), "source_row_id": _clean(row.get("source_row_id"))}\n            )\n    return rows\n'''
        diagnostic = (PKG / 'tests' / 'fixtures' / 'rule_engine_diagnostic_phase6a.py').read_text(encoding='utf-8')
        # Create pre-Phase6B diagnostic by reversing the two safe textual changes if payload ever contains them.
        diagnostic = diagnostic.replace('NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6B_V1_20260608\n\n', '')
        diagnostic = diagnostic.replace('), actual_overlaps as (', '), overlaps as (')
        diagnostic = diagnostic.replace('            from actual_overlaps o\n', '            from overlaps o\n')

        files = {
            Path('scripts/run_all.py'): run_all,
            Path('scripts/quality_gate_module.py'): quality,
            Path('scripts/export_module.py'): export,
            Path('scripts/manual_override_ui_module.py'): manual,
            Path('scripts/rule_engine_diagnostic_phase6a.py'): diagnostic,
        }
        original = {}
        for rel, text in files.items():
            write_crlf(root / rel, text)
            original[rel] = (root / rel).read_bytes()
            installer.EXPECTED_LF_BLOBS[rel] = installer.git_blob_sha(installer.lf_bytes(original[rel]))

        assert installer.dry_run(root) == 0
        for rel, raw in original.items():
            assert (root / rel).read_bytes() == raw, rel

        assert installer.apply(root) == 0
        assert installer.verify(root) == 0
        for rel in installer.ALL_FILES:
            raw = (root / rel).read_bytes()
            if rel in files:
                assert b'\r\n' in raw, rel
        assert installer.apply(root) == 0
        assert installer.rollback(root) == 0
        for rel, raw in original.items():
            assert (root / rel).read_bytes() == raw, rel
        for rel in installer.NEW_FILES:
            assert not (root / rel).exists(), rel

    print('OK: Installer-Dry-Run, Apply, CRLF, Idempotenz und Rollback erfolgreich.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
