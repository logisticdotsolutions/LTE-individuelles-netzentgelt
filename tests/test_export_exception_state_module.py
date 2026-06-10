from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_exception_state_module import (  # noqa: E402
    create_exception,
    evaluate_release_status,
    list_exceptions,
    list_export_releases,
    make_blocker,
    record_export_release,
    revoke_exception,
)
from local_auth_module import bootstrap_admin  # noqa: E402


def _password(seed: str) -> str:
    return f"Aa1!{seed}SecurePilot"


def test_exception_unlocks_export_and_can_be_revoked(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )
    blocker = make_blocker(
        blocker_type="ROOT_GAP",
        rule_id="R010",
        loco_no="91806189201-7",
        period_start_utc="2026-06-06 16:00:00",
        period_end_utc="2026-06-08 11:00:00",
        message="Relevante Unterbrechung der Lok-Zeitachse",
    )

    before = evaluate_release_status([blocker], db_path)
    assert not before.released
    assert before.missing_blockers == (blocker,)

    exception_id = create_exception(
        actor=admin,
        blocker=blocker,
        comment="Fachlich geprüfte Ausnahme für den lokalen Pilottest.",
        db_path=db_path,
    )
    after = evaluate_release_status([blocker], db_path)
    assert after.released
    assert exception_id in after.active_exception_ids

    release_id = record_export_release(
        actor=admin,
        export_kind="NUTZUNGSMELDUNG",
        export_label="LTE_DE",
        date_from=date(2026, 6, 7),
        date_to=date(2026, 6, 7),
        file_name="test.xlsx",
        content=b"xlsx-test-content",
        exception_ids=after.active_exception_ids,
        db_path=db_path,
    )
    releases = list_export_releases(db_path)
    assert releases[0]["export_release_id"] == release_id
    assert releases[0]["exception_count"] == 1

    revoke_exception(
        actor=admin,
        exception_id=exception_id,
        comment="Ausnahme wird im Test bewusst wieder widerrufen.",
        db_path=db_path,
    )
    final = evaluate_release_status([blocker], db_path)
    assert not final.released
    exceptions = list_exceptions(active_only=False, db_path=db_path)
    assert exceptions[0]["status"] == "REVOKED"
