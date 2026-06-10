"""Resolve DuckDB export gates to stable exception blockers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

import duckdb

from export_exception_gap_query_helper import list_gap_root_blockers
from export_exception_state_module import ExportBlocker, make_blocker

PHASE9C_EXCEPTION_QUERY_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_QUERY_PHASE9C_V3_20260610"
_GAP_FINDING_RULES = {"R010", "R010.5", "R016", "GATE_DAY"}


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _rus(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_clean(value) for value in values if _clean(value)))


def _marks(values: tuple[str, ...]) -> str:
    if not values:
        raise ValueError("Mindestens eine PerformingRU ist erforderlich.")
    return ", ".join("?" for _ in values)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _table_exists(con, table_name: str) -> bool:
    return bool(
        con.execute(
            """
            select count(*) > 0
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
    )


def _current_run_id(con) -> str:
    """Read the current pipeline run id defensively for legacy fixtures."""
    if not _table_exists(con, "dq_run_metadata"):
        return ""
    columns = {
        str(row[0]).lower()
        for row in con.execute("describe dq_run_metadata").fetchall()
    }
    if "run_id" not in columns:
        return ""
    row = con.execute(
        "select coalesce(cast(run_id as varchar), '') from dq_run_metadata limit 1"
    ).fetchone()
    return _clean(row[0]) if row else ""


def _root_findings(con, loco_no: str, performing_ru: str, day: date, run_id: str) -> list[ExportBlocker]:
    start, end = _day_bounds(day)
    rows = con.execute(
        """
        select coalesce(rule_id, ''), coalesce(loco_no, ''),
               coalesce(performing_ru, ''),
               coalesce(cast(period_start_utc as varchar), ''),
               coalesce(cast(period_end_utc as varchar), ''),
               coalesce(message, '')
        from dq_findings
        where severity in ('ERROR', 'MANUAL_REVIEW')
          and trim(coalesce(loco_no, '')) = ?
          and coalesce(period_start_utc, period_end_utc) < ?
          and coalesce(period_end_utc, period_start_utc) >= ?
        order by rule_id, period_start_utc, period_end_utc
        """,
        [loco_no, end, start],
    ).fetchall()
    return [
        make_blocker(
            blocker_type="ROOT_FINDING",
            rule_id=_clean(row[0]), loco_no=_clean(row[1]) or loco_no,
            performing_ru=_clean(row[2]) or performing_ru,
            period_start_utc=_clean(row[3]), period_end_utc=_clean(row[4]),
            message=_clean(row[5]), run_id=run_id,
        )
        for row in rows
    ]


def _local_blockers(con, ru_values: tuple[str, ...], date_from: date, date_to: date, run_id: str) -> list[ExportBlocker]:
    rows = con.execute(
        f"""
        select coalesce(loco_no, ''), coalesce(performing_ru, ''),
               coverage_date, coalesce(gate_reason, '')
        from dq_export_gate_ru
        where performing_ru in ({_marks(ru_values)})
          and coverage_date between ? and ?
          and gate_status = 'BLOCKED'
        order by coverage_date, loco_no, performing_ru
        """,
        [*ru_values, date_from, date_to],
    ).fetchall()
    result: list[ExportBlocker] = []
    for loco_no, performing_ru, day, reason in rows:
        loco = _clean(loco_no)
        ru = _clean(performing_ru)
        findings = _root_findings(con, loco, ru, day, run_id)
        gaps = list_gap_root_blockers(
            con,
            loco_no=loco,
            performing_ru=ru,
            day=day,
            run_id=run_id,
        )
        if gaps:
            result.extend(gaps)
            result.extend(item for item in findings if item.rule_id not in _GAP_FINDING_RULES)
        elif findings:
            result.extend(findings)
        else:
            start, end = _day_bounds(day)
            result.append(make_blocker(
                blocker_type="LOCAL_GATE_DAY", rule_id="GATE_DAY",
                loco_no=loco, performing_ru=ru,
                period_start_utc=start.isoformat(sep=" "),
                period_end_utc=end.isoformat(sep=" "),
                message=_clean(reason) or "Lok-Tag ist im Quality Gate gesperrt.",
                run_id=run_id,
            ))
    return result


def _global_blockers(con, date_from: date, date_to: date, run_id: str) -> list[ExportBlocker]:
    rows = con.execute(
        """
        select blocker_date, coalesce(rule_id, ''),
               coalesce(transport_number, ''), coalesce(performing_ru, ''),
               coalesce(message, '')
        from dq_global_export_blockers
        where blocker_date between ? and ? and gate_status = 'BLOCKED'
        order by blocker_date, rule_id, transport_number
        """,
        [date_from, date_to],
    ).fetchall()
    result: list[ExportBlocker] = []
    for day, rule_id, transport, performing_ru, message in rows:
        start, end = _day_bounds(day)
        text = _clean(message) or "Globaler Export-Blocker"
        if _clean(transport):
            text += f" | Transport {_clean(transport)}"
        result.append(make_blocker(
            blocker_type="GLOBAL_GATE", rule_id=_clean(rule_id) or "GLOBAL_GATE",
            performing_ru=_clean(performing_ru),
            period_start_utc=start.isoformat(sep=" "),
            period_end_utc=end.isoformat(sep=" "), message=text,
            run_id=run_id,
        ))
    return result


def list_required_export_blockers_from_connection(*, con, performing_ru_values: Iterable[str], date_from: date, date_to: date) -> list[ExportBlocker]:
    """Return deduplicated root blockers from an existing read connection."""
    values = _rus(performing_ru_values)
    run_id = _current_run_id(con)
    blockers = [
        *_local_blockers(con, values, date_from, date_to, run_id),
        *_global_blockers(con, date_from, date_to, run_id),
    ]
    return sorted({item.fingerprint: item for item in blockers}.values(), key=lambda item: (item.rule_id, item.loco_no, item.period_start_utc))


def list_required_export_blockers(*, db_path: Path, performing_ru_values: Iterable[str], date_from: date, date_to: date) -> list[ExportBlocker]:
    """Return deduplicated root blockers for one XLSX export request."""
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DuckDB-Datei fehlt: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return list_required_export_blockers_from_connection(
            con=con,
            performing_ru_values=performing_ru_values,
            date_from=date_from,
            date_to=date_to,
        )
    finally:
        con.close()
