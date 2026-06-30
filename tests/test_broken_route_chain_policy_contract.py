from __future__ import annotations

from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from broken_route_chain_policy_module import (  # noqa: E402
    DISABLED_BROKEN_CHAIN_RULE_IDS,
    disable_broken_route_chain_rules,
    neutralize_broken_route_chain_quality_gate,
)


def test_broken_route_chain_rules_are_removed_from_findings_and_catalog_disabled():
    con = duckdb.connect(":memory:")
    con.execute("create table dq_findings (rule_id varchar, severity varchar)")
    con.execute(
        "insert into dq_findings values "
        "('R010', 'ERROR'), ('R010.5', 'INFO'), ('R016', 'MANUAL_REVIEW'), ('R011', 'ERROR')"
    )
    con.execute(
        """
        create table cfg_dq_rule_catalog (
            rule_id varchar,
            rule_group varchar,
            severity_policy varchar,
            description varchar,
            active_flag boolean
        )
        """
    )
    con.execute(
        "insert into cfg_dq_rule_catalog values "
        "('R010', 'TIMELINE', 'ERROR', 'Alt aktiv', true), "
        "('R010.5', 'TIMELINE', 'INFO', 'Alt aktiv', true), "
        "('R016', 'TIMELINE', 'MANUAL_REVIEW', 'Alt aktiv', true), "
        "('R011', 'TIMELINE', 'ERROR', 'Overlap', true)"
    )

    disable_broken_route_chain_rules(con)

    remaining_rules = {
        row[0]
        for row in con.execute("select rule_id from dq_findings order by rule_id").fetchall()
    }
    assert remaining_rules == {"R011"}

    catalog_rows = con.execute(
        """
        select rule_id, severity_policy, active_flag
        from cfg_dq_rule_catalog
        where rule_id in ('R010', 'R010.5', 'R016')
        order by rule_id
        """
    ).fetchall()
    assert [row[0] for row in catalog_rows] == sorted(DISABLED_BROKEN_CHAIN_RULE_IDS)
    assert all(row[1] == "DISABLED" for row in catalog_rows)
    assert all(row[2] is False for row in catalog_rows)


def test_gap_only_quality_gate_is_neutralized_without_hiding_other_blockers():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        create table dq_export_gate (
            loco_no varchar,
            gate_status varchar,
            gate_reason varchar,
            relevant_gap_slot_count bigint,
            unresolved_gap_minutes bigint,
            relevant_gap_rows bigint,
            long_gap_rows bigint,
            max_gap_minutes bigint,
            error_findings bigint,
            manual_review_findings bigint,
            warning_findings bigint,
            info_findings bigint,
            overlap_slot_count bigint,
            not_export_ready_movement_rows bigint
        )
        """
    )
    con.execute(
        "insert into dq_export_gate values "
        "('GAP_ONLY', 'BLOCKED', 'GAP only', 96, 1440, 1, 1, 1440, 0, 0, 0, 0, 0, 0), "
        "('REAL_BLOCKER', 'BLOCKED', 'Real blocker', 96, 1440, 1, 1, 1440, 1, 0, 0, 0, 0, 0)"
    )

    neutralize_broken_route_chain_quality_gate(con)

    rows = con.execute(
        """
        select
            loco_no,
            gate_status,
            gate_reason,
            relevant_gap_slot_count,
            unresolved_gap_minutes,
            relevant_gap_rows,
            long_gap_rows,
            max_gap_minutes
        from dq_export_gate
        order by loco_no
        """
    ).fetchall()

    assert rows[0] == ("GAP_ONLY", "READY", "", 0, 0, 0, 0, 0)
    assert rows[1][0] == "REAL_BLOCKER"
    assert rows[1][1] == "BLOCKED"
    assert rows[1][2] == "ERROR-Findings=1"
    assert rows[1][3:] == (0, 0, 0, 0, 0)
