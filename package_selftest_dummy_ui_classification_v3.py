from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("installer", ROOT / "apply_dummy_ui_classification_v3.py")
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        write(
            project / "scripts/dummy_locomotive_module.py",
            """from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable
ROOT = Path(__file__).resolve().parents[1]
DUMMY_MAPPING_PATH = ROOT / "data" / "01_mapping" / "dummy_locomotives.csv"
MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_HARDENING_V1_20260608"
DEFAULT_DUMMY_LOCOMOTIVES = (
    "00000000001-8",
)
def _ensure_mapping_csv() -> None:
    pass

def _read_mapping_rows() -> list[dict[str, str]]:
    return []
""",
        )
        write(
            project / "scripts/manual_override_ui_module.py",
            """from __future__ import annotations
import getpass
from datetime import datetime
from pathlib import Path
from manual_override_batch_module import (
    PHASE5D_BATCH_MARKER,
    create_overrides_from_selected_suggestions,
)
PHASE5D_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"
OVERRIDE_TYPE_LABELS = {
    "CASE_NOTE": "Bearbeitungsnotiz hinterlegen",
}
def _clean(value):
    return str(value or "").strip()
def demo():
    prefill = {}
    selected_label = "x"
    override_type = "CASE_NOTE"
    form_key = f"manual_override_form_{override_type}_{abs(hash(selected_label))}_{_clean(prefill.get('suggestion_id'))}"
    with st.form(form_key):
        save_only = st.form_submit_button("Override speichern")
        save_and_rebuild = st.form_submit_button("Speichern und neu prüfen", type="primary")
    if not (save_only or save_and_rebuild):
        return
    comment = "x"
    target_loco_no = "x"
    created_by = "x"
    if override_type not in {"CLASSIFY_GAP", "CASE_NOTE"} and not override_value.strip():
        return
    if CHANGE_LOG_PATH.exists():
        pass
""",
        )
        write(
            project / "tests/test_installer_phase6b.py",
            """from __future__ import annotations
import importlib.util
from pathlib import Path
PKG = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', PKG / 'apply_rule_engine_hardening_phase6b.py')
installer = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(installer)
def main() -> int:
    return 0
""",
        )
        write(
            project / "tests/test_installer_phase6c.py",
            """from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", ROOT / "apply_rule_engine_hardening_phase6c.py")
installer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(installer)
def main() -> int:
    return 0
""",
        )
        original_csv = "loco_no;reason;active_flag\nLOCAL-EXTRA;Local entry must survive;Y\n"
        write(project / "data/01_mapping/dummy_locomotives.csv", original_csv)
        original = {
            path.relative_to(project): path.read_bytes()
            for path in project.rglob("*")
            if path.is_file()
        }
        installer.dry_run(project, True)
        assert (project / "data/01_mapping/dummy_locomotives.csv").read_bytes() == original[
            Path("data/01_mapping/dummy_locomotives.csv")
        ]
        installer.apply(project, True)
        installer.verify(project)
        csv_text = (project / "data/01_mapping/dummy_locomotives.csv").read_text(encoding="utf-8-sig")
        assert "LOCAL-EXTRA;Local entry must survive;Y" in csv_text
        assert csv_text.count("91806189000-3;") == 1
        installer.apply(project, True)
        installer.rollback(project)
        for rel, raw in original.items():
            assert (project / rel).read_bytes() == raw, rel
        assert not (project / "scripts/test_dummy_locomotive_ui_classification.py").exists()
        assert not (project / "scripts/verify_dummy_locomotive_ui_classification.py").exists()
    print("OK: Mutable Dummy-Katalog bleibt erhalten; Dry-Run, Apply, Idempotenz und Rollback erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
