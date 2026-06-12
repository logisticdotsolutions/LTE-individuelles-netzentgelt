from __future__ import annotations


PHASE_ID = "NETZENTGELT_MANUAL_GAP_NO_LTE_RELEASE_V1_20260612"
CLASSIFICATION_CODE = "NO_LTE_ASSIGNMENT"
RELEASE_MESSAGE = (
    "Manuell bestätigt: Keine LTE-Zuweisung. "
    "Dieser GAP blockiert den LTE-Export nicht."
)


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
            [table_name],
        ).fetchone()[0]
        > 0
    )


def columns(con, table_name: str) -> list[str]:
    if not table_exists(con, table_name):
        return []
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def _ensure_column(con, table_name: str, column_name: str, data_type: str) -> None:
    if column_name.lower() not in {column.lower() for column in columns(con, table_name)}:
        con.execute(f"alter table {qident(table_name)} add column {qident(column_name)} {data_type}")


def _ensure_audit_table(con) -> None:
    con.execute(
        """
        create table if not exists audit_manual_gap_export_release (
            phase_id varchar,
            run_id varchar,
            override_id varchar,
            loco_no varchar,
            period_start_utc timestamp,
            period_end_utc timestamp,
            source_table varchar,
            source_row_id varchar,
            matched_timeline_rows bigint,
            application_status varchar,
            application_message varchar,
            applied_at_utc timestamp
        )
        """
    )


def _build_matches(con) -> None:
    con.execute(
        """
        create or replace temp table tmp_no_lte_gap_matches as
        with overrides as (
            select
                trim(override_id) as override_id,
                nullif(trim(target_loco_no), '') as loco_no,
                try_cast(nullif(trim(target_actual_departure_utc), '') as timestamp) as period_start_utc,
                try_cast(nullif(trim(target_actual_arrival_utc), '') as timestamp) as period_end_utc,
                nullif(trim(target_source_table), '') as source_table,
                nullif(trim(target_source_row_id), '') as source_row_id
            from cfg_manual_overrides_effective
            where upper(trim(coalesce(override_type, ''))) = 'CLASSIFY_GAP'
              and upper(trim(coalesce(classification_code, ''))) = ?
        )
        select distinct
            o.override_id,
            t.loco_no,
            t.period_start_utc,
            t.period_end_utc,
            t.source_table,
            cast(t.source_row_id as varchar) as source_row_id
        from overrides o
        join core_loco_timeline t
          on upper(trim(coalesce(t.row_type, ''))) = 'GAP'
         and (
                (
                    o.source_table is not null
                    and o.source_row_id is not null
                    and t.source_table is not distinct from o.source_table
                    and nullif(trim(cast(t.source_row_id as varchar)), '') is not distinct from o.source_row_id
                )
                or
                (
                    o.loco_no is not null
                    and o.period_start_utc is not null
                    and o.period_end_utc is not null
                    and t.loco_no is not distinct from o.loco_no
                    and t.period_start_utc is not distinct from o.period_start_utc
                    and t.period_end_utc is not distinct from o.period_end_utc
                )
         )
        """,
        [CLASSIFICATION_CODE],
    )


def _write_audit(con, run_id: str) -> None:
    _ensure_audit_table(con)
    con.execute("delete from audit_manual_gap_export_release where run_id = ?", [str(run_id)])
    con.execute(
        """
        insert into audit_manual_gap_export_release
        select
            ? as phase_id,
            ? as run_id,
            trim(overrides.override_id) as override_id,
            nullif(trim(overrides.target_loco_no), '') as loco_no,
            try_cast(nullif(trim(overrides.target_actual_departure_utc), '') as timestamp) as period_start_utc,
            try_cast(nullif(trim(overrides.target_actual_arrival_utc), '') as timestamp) as period_end_utc,
            nullif(trim(overrides.target_source_table), '') as source_table,
            nullif(trim(overrides.target_source_row_id), '') as source_row_id,
            count(matches.override_id) as matched_timeline_rows,
            case when count(matches.override_id) > 0 then 'APPLIED' else 'NO_MATCH' end,
            case when count(matches.override_id) > 0 then ?
                 else 'Keine passende GAP-Zeile gefunden. Override bleibt auditierbar sichtbar.' end,
            current_timestamp
        from cfg_manual_overrides_effective overrides
        left join tmp_no_lte_gap_matches matches
          on matches.override_id = trim(overrides.override_id)
        where upper(trim(coalesce(overrides.override_type, ''))) = 'CLASSIFY_GAP'
          and upper(trim(coalesce(overrides.classification_code, ''))) = ?
        group by
            overrides.override_id,
            overrides.target_loco_no,
            overrides.target_actual_departure_utc,
            overrides.target_actual_arrival_utc,
            overrides.target_source_table,
            overrides.target_source_row_id
        """,
        [PHASE_ID, str(run_id), RELEASE_MESSAGE, CLASSIFICATION_CODE],
    )


def apply_no_lte_gap_release(con, run_id: str) -> int:
    """Mark exactly those GAPs that were explicitly classified without LTE assignment."""
    _ensure_audit_table(con)
    if not table_exists(con, "cfg_manual_overrides_effective") or not table_exists(con, "core_loco_timeline"):
        return 0
    for column_name, data_type in [
        ("needs_manual_review", "boolean"),
        ("export_blocking", "boolean"),
        ("dq_severity", "varchar"),
        ("dq_message", "varchar"),
        ("gap_export_released", "boolean"),
        ("gap_export_release_reason", "varchar"),
    ]:
        _ensure_column(con, "core_loco_timeline", column_name, data_type)
    _build_matches(con)
    matched = int(con.execute("select count(*) from tmp_no_lte_gap_matches").fetchone()[0])
    if matched:
        con.execute(
            """
            update core_loco_timeline as target
            set
                needs_manual_review = false,
                export_blocking = false,
                dq_severity = 'INFO',
                dq_message = case
                    when position(? in coalesce(target.dq_message, '')) > 0 then target.dq_message
                    else concat_ws(' | ', nullif(trim(coalesce(target.dq_message, '')), ''), ?)
                end,
                gap_export_released = true,
                gap_export_release_reason = ?
            where upper(trim(coalesce(target.row_type, ''))) = 'GAP'
              and exists (
                    select 1 from tmp_no_lte_gap_matches matched
                    where matched.loco_no is not distinct from target.loco_no
                      and matched.period_start_utc is not distinct from target.period_start_utc
                      and matched.period_end_utc is not distinct from target.period_end_utc
                      and matched.source_table is not distinct from target.source_table
                      and matched.source_row_id is not distinct from cast(target.source_row_id as varchar)
              )
            """,
            [RELEASE_MESSAGE, RELEASE_MESSAGE, RELEASE_MESSAGE],
        )
        if table_exists(con, "dq_findings"):
            con.execute(
                """
                update dq_findings as target
                set severity = 'INFO', status = 'info',
                    suggested_action = concat_ws(' | ', nullif(trim(coalesce(target.suggested_action, '')), ''), ?)
                where (
                        upper(trim(coalesce(target.row_type, ''))) = 'GAP'
                        and exists (
                            select 1 from tmp_no_lte_gap_matches matched
                            where matched.loco_no is not distinct from target.loco_no
                              and matched.period_start_utc is not distinct from target.period_start_utc
                              and matched.period_end_utc is not distinct from target.period_end_utc
                              and matched.source_table is not distinct from target.source_table
                              and matched.source_row_id is not distinct from cast(target.source_row_id as varchar)
                        )
                      )
                   or (
                        upper(trim(coalesce(target.rule_id, ''))) = 'R016'
                        and exists (
                            select 1 from tmp_no_lte_gap_matches matched
                            where matched.loco_no is not distinct from target.loco_no
                              and target.period_start_utc < matched.period_end_utc
                              and target.period_end_utc > matched.period_start_utc
                        )
                      )
                """,
                [RELEASE_MESSAGE],
            )
    _write_audit(con, run_id)
    print(f"Manuelle GAP-Freigaben ohne LTE-Zuweisung: {matched}")
    return matched


def suspend_released_gaps_for_quality_gate(con) -> None:
    """Temporarily hide released GAPs from gate aggregation while keeping them visible in the UI."""
    if not table_exists(con, "core_loco_timeline"):
        return
    existing = {column.lower() for column in columns(con, "core_loco_timeline")}
    if "gap_export_released" not in existing or "gap_relevant_de" not in existing:
        return
    con.execute(
        """
        create or replace temp table tmp_no_lte_gap_visibility_backup as
        select loco_no, period_start_utc, period_end_utc, source_table,
               cast(source_row_id as varchar) as source_row_id, gap_relevant_de
        from core_loco_timeline
        where upper(trim(coalesce(row_type, ''))) = 'GAP'
          and coalesce(gap_export_released, false) = true
        """
    )
    con.execute(
        """
        update core_loco_timeline
        set gap_relevant_de = false
        where upper(trim(coalesce(row_type, ''))) = 'GAP'
          and coalesce(gap_export_released, false) = true
        """
    )


def restore_released_gap_visibility(con) -> None:
    """Restore UI visibility after the quality gate snapshot has been built."""
    if not table_exists(con, "tmp_no_lte_gap_visibility_backup"):
        return
    con.execute(
        """
        update core_loco_timeline as target
        set gap_relevant_de = backup.gap_relevant_de
        from tmp_no_lte_gap_visibility_backup backup
        where target.loco_no is not distinct from backup.loco_no
          and target.period_start_utc is not distinct from backup.period_start_utc
          and target.period_end_utc is not distinct from backup.period_end_utc
          and target.source_table is not distinct from backup.source_table
          and cast(target.source_row_id as varchar) is not distinct from backup.source_row_id
        """
    )
