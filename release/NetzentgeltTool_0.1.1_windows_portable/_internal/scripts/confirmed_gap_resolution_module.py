from __future__ import annotations


RESOLUTION_MARKER = "NETZENTGELT_CONFIRMED_GAP_RESOLUTION_V1_20260618"
GAP_RULES = "('R010', 'R010.5', 'R015', 'R016')"
GAP_CODES = "('SAME_RU_CONTINUITY', 'COLD_STAND', 'NO_LTE_ASSIGNMENT')"


def table_exists(con, table_name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
        [table_name],
    ).fetchone()[0] > 0


def apply_confirmed_gap_resolution(con, run_id: str) -> None:
    """Confirmed GAP classifications close the technical GAP for gates/findings."""
    if not table_exists(con, "cfg_manual_overrides_effective"):
        return
    if not table_exists(con, "dq_findings"):
        return

    con.execute(
        f"""
        create or replace temp table tmp_confirmed_gap_resolution as
        select
            nullif(trim(target_loco_no), '') as loco_no,
            try_cast(nullif(trim(target_actual_departure_utc), '') as timestamp) as period_start_utc,
            try_cast(nullif(trim(target_actual_arrival_utc), '') as timestamp) as period_end_utc,
            nullif(trim(target_source_table), '') as source_table,
            try_cast(nullif(trim(target_source_row_id), '') as bigint) as source_row_id,
            upper(trim(coalesce(classification_code, ''))) as classification_code,
            override_id
        from cfg_manual_overrides_effective
        where upper(trim(coalesce(active_flag, 'Y'))) not in ('N', 'NO', 'FALSE', '0')
          and upper(trim(coalesce(override_type, ''))) = 'CLASSIFY_GAP'
          and upper(trim(coalesce(classification_code, ''))) in {GAP_CODES}
        """
    )

    confirmed = con.execute("select count(*) from tmp_confirmed_gap_resolution").fetchone()[0]
    if not confirmed:
        return

    before = con.execute(f"select count(*) from dq_findings where rule_id in {GAP_RULES}").fetchone()[0]
    con.execute(
        f"""
        delete from dq_findings as f
        where f.rule_id in {GAP_RULES}
          and exists (
                select 1
                from tmp_confirmed_gap_resolution c
                where (
                        c.source_table is not null
                    and c.source_row_id is not null
                    and f.source_table is not distinct from c.source_table
                    and f.source_row_id is not distinct from c.source_row_id
                )
                   or (
                        c.loco_no is not null
                    and f.loco_no is not distinct from c.loco_no
                    and c.period_start_utc is not null
                    and f.period_start_utc is not distinct from c.period_start_utc
                    and (c.period_end_utc is null or f.period_end_utc is not distinct from c.period_end_utc)
                )
                   or (
                        f.rule_id = 'R016'
                    and c.loco_no is not null
                    and f.loco_no is not distinct from c.loco_no
                    and c.period_start_utc is not null
                    and cast(f.period_start_utc as date) = cast(c.period_start_utc as date)
                )
          )
        """
    )
    after = con.execute(f"select count(*) from dq_findings where rule_id in {GAP_RULES}").fetchone()[0]

    if table_exists(con, "core_loco_timeline"):
        con.execute(
            """
            update core_loco_timeline as g
            set
                gap_relevant_de = false,
                needs_manual_review = false,
                dq_severity = 'INFO',
                dq_message = concat_ws(' ', 'GAP fachlich bestätigt.', 'Keine blockierende GAP-Prüfung mehr.', 'Klassifikation:', c.classification_code)
            from tmp_confirmed_gap_resolution c
            where g.row_type = 'GAP'
              and (
                    (c.source_table is not null and c.source_row_id is not null and g.source_table is not distinct from c.source_table and g.source_row_id is not distinct from c.source_row_id)
                 or (c.loco_no is not null and g.loco_no is not distinct from c.loco_no and c.period_start_utc is not null and g.period_start_utc is not distinct from c.period_start_utc and (c.period_end_utc is null or g.period_end_utc is not distinct from c.period_end_utc))
              )
            """
        )

    if table_exists(con, "dq_feedback_rule_adjustments_audit"):
        con.execute(
            """
            insert into dq_feedback_rule_adjustments_audit values (?, ?, ?, ?, current_timestamp, ?)
            """,
            [RESOLUTION_MARKER, str(run_id), "confirmed_gap_findings_removed", int(before - after), "Bestaetigte GAP-Klassifikationen entfernen blockierende GAP-Findings."],
        )
