"""Resolve multi-day timeline gaps to one stable export-exception root blocker."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from export_exception_state_module import ExportBlocker, make_blocker


PHASE9C_GAP_ROOT_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_GAP_ROOT_PHASE9C_V1_20260610"


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def list_gap_root_blockers(con, *, loco_no: str, performing_ru: str, day: date) -> list[ExportBlocker]:
    """Return full timeline GAP intervals crossing one blocked locomotive day."""
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    rows = con.execute(
        """
        select
            coalesce(cast(period_start_utc as varchar), ''),
            coalesce(cast(period_end_utc as varchar), ''),
            coalesce(cast(gap_duration_minutes as varchar), ''),
            coalesce(dq_message, '')
        from core_loco_timeline
        where row_type = 'GAP'
          and trim(coalesce(loco_no, '')) = ?
          and coalesce(gap_relevant_de, false) = true
          and coalesce(gap_time_basis_safe, true) = true
          and period_start_utc < ?
          and period_end_utc > ?
        order by period_start_utc, period_end_utc
        """,
        [loco_no, end, start],
    ).fetchall()

    result: list[ExportBlocker] = []
    for period_start, period_end, duration, message in rows:
        details = _clean(message) or "Relevante Unterbrechung der Lok-Zeitachse"
        if _clean(duration):
            details += f" | GAP-Minuten={_clean(duration)}"
        result.append(
            make_blocker(
                blocker_type="ROOT_GAP",
                rule_id="R010",
                loco_no=loco_no,
                performing_ru=performing_ru,
                period_start_utc=_clean(period_start),
                period_end_utc=_clean(period_end),
                message=details,
            )
        )
    return result
