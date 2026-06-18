from __future__ import annotations

import builtins


_ORIGINAL_IMPORT = builtins.__import__
_PATCHED = False


def _table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            "select count(*) from information_schema.tables where lower(table_name) = lower(?)",
            [table_name],
        ).fetchone()[0]
        > 0
    )


def _rebuild_exact_overlap_diff_ru(con, run_id: str) -> None:
    if not _table_exists(con, "core_usage_assignment_segment_movements") or not _table_exists(con, "dq_run_metadata"):
        return
    con.execute(
        """
        create or replace table dq_phase6d_exact_overlap_days as
        with intervals as (
            select
                row_number() over (order by loco_no, de_period_start_utc, de_period_end_utc, source_row_id) as interval_id,
                loco_no,
                nullif(trim(performing_ru), '') as performing_ru,
                de_period_start_utc as interval_start_utc,
                de_period_end_utc as interval_end_utc
            from core_usage_assignment_segment_movements
            where nullif(trim(loco_no), '') is not null
              and de_period_start_utc is not null
              and de_period_end_utc is not null
              and de_period_end_utc > de_period_start_utc
              and de_period_start_utc <= (select max(error_cutoff_utc) from dq_run_metadata)
        ), overlap_pairs as (
            select
                a.loco_no,
                greatest(a.interval_start_utc, b.interval_start_utc) as overlap_start_utc,
                least(a.interval_end_utc, b.interval_end_utc) as overlap_end_utc
            from intervals a
            join intervals b
              on b.loco_no = a.loco_no
             and b.interval_id > a.interval_id
             and a.interval_start_utc < b.interval_end_utc
             and b.interval_start_utc < a.interval_end_utc
             and coalesce(a.performing_ru, '#') <> coalesce(b.performing_ru, '#')
        ), day_spans as (
            select
                o.loco_no,
                cast(days.day_start_utc as date) as coverage_date,
                greatest(o.overlap_start_utc, days.day_start_utc) as overlap_start_utc,
                least(o.overlap_end_utc, days.day_start_utc + interval '1 day') as overlap_end_utc
            from overlap_pairs o
            cross join unnest(
                generate_series(
                    date_trunc('day', o.overlap_start_utc),
                    date_trunc('day', o.overlap_end_utc - interval '1 microsecond'),
                    interval '1 day'
                )
            ) as days(day_start_utc)
            where o.overlap_end_utc > o.overlap_start_utc
        )
        select
            ?::varchar as run_id,
            loco_no,
            coverage_date,
            sum(date_diff('second', overlap_start_utc, overlap_end_utc))::bigint as exact_overlap_seconds,
            round(sum(date_diff('second', overlap_start_utc, overlap_end_utc)) / 60.0, 2) as exact_overlap_minutes,
            count(*)::bigint as overlap_span_count
        from day_spans
        where overlap_end_utc > overlap_start_utc
        group by loco_no, coverage_date
        order by coverage_date desc, loco_no
        """,
        [str(run_id)],
    )


def _patch_phase6d(module) -> None:
    if getattr(module, "_PHASE11I_FEEDBACK_PATCHED", False):
        return
    original_finalize = module.finalize_quality_gate_phase6d

    def patched_finalize_quality_gate_phase6d(con, run_id: str) -> None:
        original_finalize(con, run_id)
        _rebuild_exact_overlap_diff_ru(con, run_id)
        from feedback_rule_adjustments_module import apply_feedback_rule_adjustments_phase11i

        apply_feedback_rule_adjustments_phase11i(con, run_id)

    module.finalize_quality_gate_phase6d = patched_finalize_quality_gate_phase6d
    module._PHASE11I_FEEDBACK_PATCHED = True


def _import_hook(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    target = None
    if name == "rule_engine_hardening_phase6d":
        target = module
    elif fromlist:
        try:
            imported = _ORIGINAL_IMPORT("rule_engine_hardening_phase6d", globals, locals, [], 0)
            target = imported
        except Exception:
            target = None
    if target is not None:
        try:
            _patch_phase6d(target)
        except Exception:
            pass
    return module


if not _PATCHED:
    builtins.__import__ = _import_hook
    _PATCHED = True
