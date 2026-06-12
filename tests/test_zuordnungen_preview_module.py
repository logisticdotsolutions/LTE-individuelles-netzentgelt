from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import zuordnungen_preview_module as module  # noqa: E402


def _create_preview_fixture(db_path: Path) -> None:
    con = duckdb.connect(str(db_path))
    try:
        con.execute(
            """
            create table core_usage_assignment_segments (
                usage_segment_id integer,
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
                usage_segment_id integer,
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

        con.execute(
            """
            insert into core_usage_assignment_segments values
                (1, '91801234567-8', '2026-06-09 08:00:00', '2026-06-09 10:00:00',
                 'LTE DE - LTE Germany GmbH', 1, '1900100300001', '1900100300393',
                 'LTE Logistik- und Transport-GmbH', 0),
                (2, '91807654321-0', '2026-06-09 11:00:00', '2026-06-09 13:00:00',
                 'LTE NL - LTE Netherlands B.V.', 1, '1900100300002', '1900100300393',
                 'LTE Logistik- und Transport-GmbH', 0)
            """
        )
        con.execute(
            """
            insert into core_usage_assignment_segment_movements values
                (1, '2026-06-09 08:15:00'),
                (2, '2026-06-09 11:15:00')
            """
        )
        con.execute(
            """
            insert into dq_export_gate_ru values
                ('91807654321-0', 'LTE NL - LTE Netherlands B.V.', '2026-06-09', 'BLOCKED')
            """
        )
    finally:
        con.close()


def test_preview_keeps_blocked_rows_visible(tmp_path: Path) -> None:
    db_path = tmp_path / "netzentgelt.duckdb"
    _create_preview_fixture(db_path)

    preview = module.build_zuordnungen_holding_preview(
        db_path=db_path,
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )

    assert len(preview) == 2
    assert preview["Exportstatus"].tolist() == ["EXPORTFÄHIG", "BLOCKIERT"]
    assert "blockierende Prüffälle" in preview.iloc[1]["Hinweis"]


def test_preview_can_be_downloaded_as_xlsx(tmp_path: Path) -> None:
    db_path = tmp_path / "netzentgelt.duckdb"
    _create_preview_fixture(db_path)

    preview = module.build_zuordnungen_holding_preview(
        db_path=db_path,
        date_from=date(2026, 6, 9),
        date_to=date(2026, 6, 9),
    )

    content = module.preview_to_xlsx_bytes(preview)

    assert content.startswith(b"PK")
    assert len(content) > 1000
