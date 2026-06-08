from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATCHER = ROOT / "apply_netzentgelt_quality_gate_overlap_hotfix.py"
LOGIC = ROOT / "test_quality_gate_overlap_logic_pure.py"

FIXTURE = '''def build(con):\n''' + '''    con.execute(\n        """\n        create or replace temp table tmp_qg_day_overlap as\n        with duplicate_slots as (\n            select\n                loco_no,\n                coverage_date,\n                slot_start_utc\n            from tmp_qg_movement_slots\n            group by loco_no, coverage_date, slot_start_utc\n            having count(distinct source_table || ':' || cast(source_row_id as varchar)) > 1\n        )\n        select\n            loco_no,\n            coverage_date,\n            count(*) as overlap_slot_count\n        from duplicate_slots\n        group by loco_no, coverage_date\n        """\n    )\n'''


def call(*args, env=None):
    result = subprocess.run([sys.executable, str(PATCHER), *args], cwd=str(ROOT), capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError(f"Fehlgeschlagen: {' '.join(args)}")
    return result


def main():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        target = project / "scripts" / "quality_gate_module.py"
        target.parent.mkdir(parents=True)
        target.write_bytes(FIXTURE.replace("\n", "\r\n").encode("utf-8"))
        before = target.read_bytes()
        env = os.environ.copy()
        env["NETZENTGELT_ALLOW_QG_FIXTURE"] = "1"
        call("dry-run", "--project-root", str(project), env=env)
        assert target.read_bytes() == before
        call("apply", "--project-root", str(project), env=env)
        after = target.read_bytes()
        assert b"\r\n" in after
        assert b"NETZENTGELT_QG_ACTUAL_OVERLAP_HOTFIX_V1_20260608" in after
        call("verify", "--project-root", str(project), env=env)
        call("apply", "--project-root", str(project), env=env)
        call("rollback", "--project-root", str(project), env=env)
        assert target.read_bytes() == before
    logic = subprocess.run([sys.executable, str(LOGIC)], cwd=str(ROOT), capture_output=True, text=True)
    print(logic.stdout)
    if logic.returncode != 0:
        print(logic.stderr)
        raise RuntimeError("Logiktest fehlgeschlagen")
    print("OK: Paket-Selbsttest vollständig erfolgreich.")


if __name__ == "__main__":
    main()
