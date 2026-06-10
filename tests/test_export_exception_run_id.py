from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_exception_state_module import (  # noqa: E402
    create_exception,
    evaluate_release_status,
    make_blocker,
)
from local_auth_module import bootstrap_admin  # noqa: E402


def _password(seed: str) -> str:
    return f"Aa1!{seed}SecurePilot"


def _blocker(run_id: str):
    return make_blocker(
        blocker_type="ROOT_GAP",
        rule_id="R010",
        loco_no="91806189201-7",
        period_start_utc="2026-06-06 16:00:00",
        period_end_utc="2026-06-08 11:00:00",
        message="Relevante Unterbrechung der Lok-Zeitachse",
        run_id=run_id,
    )


def test_old_exception_does_not_unlock_new_pipeline_run(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )

    blocker_run_1 = _blocker("RUN_20260610_080000")
    blocker_run_2 = _blocker("RUN_20260610_120000")

    assert blocker_run_1.fingerprint != blocker_run_2.fingerprint

    create_exception(
        actor=admin,
        blocker=blocker_run_1,
        comment="Fachlich geprüfte Ausnahme für den ersten Datenstand.",
        db_path=db_path,
    )

    assert evaluate_release_status([blocker_run_1], db_path).released
    assert not evaluate_release_status([blocker_run_2], db_path).released
