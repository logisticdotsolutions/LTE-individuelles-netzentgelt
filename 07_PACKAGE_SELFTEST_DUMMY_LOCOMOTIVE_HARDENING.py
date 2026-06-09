from __future__ import annotations

from pathlib import Path
import importlib.util
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "installer", ROOT / "apply_dummy_locomotive_hardening.py"
)
installer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(installer)


def crlf(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        (project / "scripts").mkdir(parents=True)
        (project / "data" / "01_mapping").mkdir(parents=True)
        run_all = """from rule_engine_hardening_phase6d import (
    finalize_quality_gate_phase6d,
    insert_gap_only_day_findings_phase6d,
)

def main():
        build_cancelled_transport_exclusions(con)
        build_loco_events(con)
        apply_staging_manual_overrides(con, run_id)
        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)
        harden_findings_and_export_policy(con, run_id)
        for table, name in [
            (\"audit_excluded_cancelled_transports\", \"audit_excluded_cancelled_transports.csv\"),
        ]:
            pass
"""
        ui = """import pandas as pd

def x():
    prefill = {}
    cases = _build_case_table(findings=findings, timeline=timeline)
    if prefill:
        cases = pd.concat([pd.DataFrame([_prefill_case(prefill)]), cases], ignore_index=True)
        st.success(
            \"x\"
        )
"""
        (project / "scripts" / "run_all.py").write_bytes(crlf(run_all))
        (project / "scripts" / "manual_override_ui_module.py").write_bytes(crlf(ui))
        old_root, old_backup = installer.ROOT, installer.BACKUP_ROOT
        old_modified = dict(installer.MODIFIED)
        try:
            installer.ROOT = project
            installer.BACKUP_ROOT = project / ".backups"
            installer.MODIFIED = {
                Path("scripts/run_all.py"): installer.git_blob_sha((project / "scripts/run_all.py").read_bytes()),
                Path("scripts/manual_override_ui_module.py"): installer.git_blob_sha((project / "scripts/manual_override_ui_module.py").read_bytes()),
            }
            installer.dry_run(project)
            installer.apply(project)
            installer.verify(project)
            installer.apply(project)
            installer.rollback(project)
        finally:
            installer.ROOT = old_root
            installer.BACKUP_ROOT = old_backup
            installer.MODIFIED = old_modified
    print("OK: Installer Dry-Run, Apply, Verify, CRLF, Idempotenz und Rollback erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
