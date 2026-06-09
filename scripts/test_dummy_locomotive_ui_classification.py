from __future__ import annotations

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dummy_locomotive_module as mod

MARKER = "NETZENTGELT_DUMMY_UI_CLASSIFICATION_TEST_V2_20260609"


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_mapping = mod.DUMMY_MAPPING_PATH
        original_log = mod.DUMMY_CHANGE_LOG_PATH
        original_backup = mod.DUMMY_MAPPING_BACKUP_DIR
        try:
            mod.DUMMY_MAPPING_PATH = root / "dummy_locomotives.csv"
            mod.DUMMY_CHANGE_LOG_PATH = root / "dummy_locomotive_change_log.csv"
            mod.DUMMY_MAPPING_BACKUP_DIR = root / "backups"
            mod.DUMMY_MAPPING_PATH.write_text(
                "loco_no;reason;active_flag\n91806189000-3;Old reason;N\n",
                encoding="utf-8",
            )
            action = mod.upsert_dummy_locomotive_mapping(
                loco_no="91806189000-3",
                reason="Planungslok laut Controller",
                changed_by="tester",
            )
            assert action == "REACTIVATE", action
            content = mod.DUMMY_MAPPING_PATH.read_text(encoding="utf-8-sig")
            assert "91806189000-3;Planungslok laut Controller;Y" in content
            assert content.count("91806189000-3;") == 1
            action = mod.upsert_dummy_locomotive_mapping(
                loco_no="91806189000-3",
                reason="Planungslok laut Controller",
                changed_by="tester",
            )
            assert action == "ALREADY_ACTIVE", action
            assert mod.DUMMY_CHANGE_LOG_PATH.exists()
        finally:
            mod.DUMMY_MAPPING_PATH = original_mapping
            mod.DUMMY_CHANGE_LOG_PATH = original_log
            mod.DUMMY_MAPPING_BACKUP_DIR = original_backup
    print("OK: Dummy-UI-Upsert, Reaktivierung, Deduplizierung und Audit-Log erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
