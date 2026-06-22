from __future__ import annotations


def _table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _update_gate_table(con, table_name: str) -> None:
    if not _table_exists(con, table_name):
        return

    con.execute(
        f"""
        update {_qident(table_name)} as gate
        set
            manual_review_findings = greatest(coalesce(gate.manual_review_findings, 0), 1),
            gate_status = 'BLOCKED',
            gate_reason = concat_ws(
                ' | ',
                nullif(trim(coalesce(gate.gate_reason, '')), ''),
                case
                    when position('Manual Reviews=' in coalesce(gate.gate_reason, '')) = 0
                        then 'Manual Reviews=1'
                    else null
                end,
                case
                    when position('R016' in coalesce(gate.gate_reason, '')) = 0
                        then 'R016'
                    else null
                end
            )
        from (
            select distinct
                loco_no,
                cast(period_start_utc as date) as coverage_date
            from dq_findings
            where rule_id = 'R016'
              and nullif(trim(loco_no), '') is not null
              and period_start_utc is not null
        ) r016
        where r016.loco_no = gate.loco_no
          and r016.coverage_date = gate.coverage_date
        """
    )


def apply_r016_to_quality_gate_tables(con) -> int:
    if not _table_exists(con, "dq_findings"):
        return 0

    r016_count = int(
        con.execute("select count(*) from dq_findings where rule_id = 'R016'").fetchone()[0]
        or 0
    )

    if r016_count <= 0:
        return 0

    if _table_exists(con, "core_loco_day_coverage"):
        con.execute(
            """
            update core_loco_day_coverage as gate
            set
                manual_review_findings = greatest(coalesce(gate.manual_review_findings, 0), 1),
                finding_rule_ids = concat_ws(
                    ', ',
                    nullif(trim(coalesce(gate.finding_rule_ids, '')), ''),
                    case
                        when position('R016' in coalesce(gate.finding_rule_ids, '')) = 0
                            then 'R016'
                        else null
                    end
                ),
                gate_status = 'BLOCKED',
                gate_reason = concat_ws(
                    ' | ',
                    nullif(trim(coalesce(gate.gate_reason, '')), ''),
                    case
                        when position('Manual Reviews=' in coalesce(gate.gate_reason, '')) = 0
                            then 'Manual Reviews=1'
                        else null
                    end,
                    case
                        when position('R016' in coalesce(gate.gate_reason, '')) = 0
                            then 'R016'
                        else null
                    end
                )
            from (
                select distinct
                    loco_no,
                    cast(period_start_utc as date) as coverage_date
                from dq_findings
                where rule_id = 'R016'
                  and nullif(trim(loco_no), '') is not null
                  and period_start_utc is not null
            ) r016
            where r016.loco_no = gate.loco_no
              and r016.coverage_date = gate.coverage_date
            """
        )

    _update_gate_table(con, "dq_export_gate")
    _update_gate_table(con, "dq_export_gate_ru")

    print(f"R016 inkrementell in Quality-Gate-Tabellen markiert: {r016_count}")
    return r016_count
