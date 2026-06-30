from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from zuordnungen_export_module import _fetch_holding_assignment_segments  # noqa: E402
from zuordnungen_preview_module import build_zuordnungen_holding_preview  # noqa: E402


def _prepare_holding_filter_db(db_path: Path) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            create table core_usage_assignment_segments (
                usage_segment_id varchar,
                loco_no varchar,
                segment_start_utc timestamp,
                segment_end_utc timestamp,
                performing_ru varchar,
                movement_count integer,
                user_vens varchar,
                holder_market_partner_id varchar,
                holder_name varchar,
                export_blocking_movement_rows integer
            )
            """
        )
        con.execute(
            """
            create table core_usage_assignment_segment_movements (
                usage_segment_id varchar,
                actual_departure_ts timestamp
            )
            """
        )
        con.execute(
            """
            create table dq_export_gate_ru (
                loco_no varchar,
                performing_ru varchar,
                coverage_date date,
                gate_status varchar
            )
            """
        )
        con.execute(
            """
            create table dq_global_export_blockers (
                blocker_date date,
                rule_id varchar,
                gate_status varchar
            )
            """
        )

        con.executemany(
            """
            insert into core_usage_assignment_segments values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "seg-holding-id",
                    "918000000001",
                    "2026-06-01 08:00:00",
                    "2026-06-01 10:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100300393",
                    "",
                    0,
                ),
                (
                    "seg-holding-name",
                    "918000000002",
                    "2026-06-01 11:00:00",
                    "2026-06-01 12:00:00",
                    "LTE NL - LTE Netherlands B.V.",
                    1,
                    "VENS-NL",
                    "",
                    "LTE Logistik- und Transport-GmbH (Holding)",
                    0,
                ),
                (
                    "seg-other-holder",
                    "918000000003",
                    "2026-06-01 13:00:00",
                    "2026-06-01 14:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100999999",
                    "Fremder Halter GmbH",
                    0,
                ),
                (
                    "seg-holding-blocked-row",
                    "918000000004",
                    "2026-06-01 15:00:00",
                    "2026-06-01 16:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100400391",
                    "LTE Logistik- und Transport-GmbH",
                    1,
                ),
            ],
        )
        con.executemany(
            """
            insert into core_usage_assignment_segment_movements values (?, ?)
            """,
            [
                ("seg-holding-id", "2026-06-01 08:30:00"),
                ("seg-holding-name", "2026-06-01 11:30:00"),
                ("seg-other-holder", "2026-06-01 13:30:00"),
                ("seg-holding-blocked-row", "2026-06-01 15:30:00"),
            ],
        )
    finally:
        con.close()


def test_holding_assignment_export_contains_only_lte_holding_holder(tmp_path):
    db_path = tmp_path / "holding_filter.duckdb"
    _prepare_holding_filter_db(db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        rows = _fetch_holding_assignment_segments(
            con=con,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 1),
        )
    finally:
        con.close()

    assert [row["locomotive_no"] for row in rows] == [
        "918000000001",
        "918000000002",
    ]
    assert {row["holder_market_partner_id"] for row in rows} == {
        "1900100300393",
        "LTE Logistik- und Transport-GmbH (Holding)",
    }


def test_holding_assignment_preview_contains_only_lte_holding_holder(tmp_path):
    db_path = tmp_path / "holding_preview_filter.duckdb"
    _prepare_holding_filter_db(db_path)

    preview = build_zuordnungen_holding_preview(
        db_path=db_path,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 1),
    )

    assert preview["TfzE oder tEns*"].astype(str).tolist() == [
        "918000000001",
        "918000000002",
        "918000000004",
    ]
    assert "918000000003" not in preview["TfzE oder tEns*"].astype(str).tolist()
    assert preview.loc[
        preview["TfzE oder tEns*"].astype(str).eq("918000000004"),
        "Exportstatus",
    ].item() == "BLOCKIERT"
