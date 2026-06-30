from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from holder_grouped_export_runtime_module import (  # noqa: E402
    UNRESOLVED_HOLDER_KEY,
    list_holder_export_groups,
)


def test_list_holder_export_groups_splits_lte_group_by_holder(tmp_path):
    db_path = tmp_path / "holder_export.duckdb"
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

        con.executemany(
            """
            insert into core_usage_assignment_segments values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "seg-1",
                    "918012345678",
                    "2026-06-01 08:00:00",
                    "2026-06-01 10:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100300393",
                    "LTE Logistik- und Transport-GmbH",
                    0,
                ),
                (
                    "seg-2",
                    "918087654321",
                    "2026-06-01 11:00:00",
                    "2026-06-01 12:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100400391",
                    "LTE Germany GmbH",
                    0,
                ),
                (
                    "seg-3",
                    "918000000003",
                    "2026-06-01 13:00:00",
                    "2026-06-01 14:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "",
                    "",
                    0,
                ),
                (
                    "seg-4",
                    "918000000004",
                    "2026-06-01 15:00:00",
                    "2026-06-01 16:00:00",
                    "LTE NL - LTE Netherlands B.V.",
                    1,
                    "VENS-NL",
                    "1900100999999",
                    "LTE NL",
                    0,
                ),
                (
                    "seg-5",
                    "918000000005",
                    "2026-06-02 15:00:00",
                    "2026-06-02 16:00:00",
                    "LTE DE - LTE Germany GmbH",
                    1,
                    "VENS-DE",
                    "1900100300393",
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
                ("seg-1", "2026-06-01 08:30:00"),
                ("seg-2", "2026-06-01 11:30:00"),
                ("seg-3", "2026-06-01 13:30:00"),
                ("seg-4", "2026-06-01 15:30:00"),
                ("seg-5", "2026-06-02 15:30:00"),
            ],
        )
    finally:
        con.close()

    groups = list_holder_export_groups(
        db_path=db_path,
        performing_ru_values=("LTE DE - LTE Germany GmbH",),
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 1),
    )

    assert [group.holder_key for group in groups] == [
        "1900100400391",
        "1900100300393",
        UNRESOLVED_HOLDER_KEY,
    ]
    assert [group.row_count for group in groups] == [1, 1, 1]
    assert groups[0].holder_label == "LTE Germany GmbH (1900100400391)"
    assert groups[2].holder_label == "Halter offen / nicht zugeordnet"
