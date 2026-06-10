from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_exception_state_module import list_export_releases  # noqa: E402
from export_release_dedup_module import record_export_release_once  # noqa: E402
from local_auth_module import bootstrap_admin  # noqa: E402


def _password(seed: str) -> str:
    return f"Aa1!{seed}SecurePilot"


def test_identical_prepared_release_is_recorded_once(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    admin = bootstrap_admin(
        username="admin.user",
        display_name="Admin User",
        password=_password("Admin"),
        db_path=db_path,
    )

    common = {
        "actor": admin,
        "export_kind": "NUTZUNGSMELDUNG",
        "export_label": "LTE_DE",
        "date_from": date(2026, 6, 7),
        "date_to": date(2026, 6, 7),
        "file_name": "nutzungsmeldung_lte_de.xlsx",
        "content": b"same-xlsx-payload",
        "exception_ids": ("EXC_TEST",),
        "run_id": "RUN_20260610_080000",
        "db_path": db_path,
    }

    first_id = record_export_release_once(**common)
    second_id = record_export_release_once(**common)

    assert first_id == second_id
    releases = list_export_releases(db_path)
    assert len(releases) == 1
    assert releases[0]["run_id"] == "RUN_20260610_080000"
