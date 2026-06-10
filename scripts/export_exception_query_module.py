"""Resolve DuckDB export gates to stable exception blockers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable

import duckdb

from export_exception_state_module import ExportBlocker, make_blocker

PHASE9C_EXCEPTION_QUERY_MARKER = "NETZENTGELT_EXPORT_EXCEPTION_QUERY_PHASE9C_V1_20260610"


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


def _root_findings(con, loco_no: str, performing_ru: str, day: date) -> list[ExportBlocker]:
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
            message=_clean(row[5]),
        )
        for row in rows
    ]


def _local_blockers(con, ru_values: tuple[str, ...], date_from: date, date_to: date) -> list[ExportBlocker]:
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
        findings = _root_findings(con, _clean(loco_no), _clean(performing_ru), day)
        if findings:
            result.extend(findings)
        else:
            start, end = _day_bounds(day)
            result.append(make_blocker(
                blocker_type="LOCAL_GATE_DAY", rule_id="GATE_DAY",
                loco_no=_clean(loco_no), performing_ru=_clean(performing_ru),
                period_start_utc=start.isoformat(sep=" "),
                period_end_utc=end.isoformat(sep=" "),
                message=_clean(reason) or "Lok-Tag ist im Quality Gate gesperrt.",
            ))
    return result


def _global_blockers(con, date_from: date, date_to: date) -> list[ExportBlocker]:
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
        ))
    return result


def list_required_export_blockers(*, db_path: Path, performing_ru_values: Iterable[str], date_from: date, date_to: date) -> list[ExportBlocker]:
    """Return deduplicated root blockers for one XLSX export request."""
    values = _rus(performing_ru_values)
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DuckDB-Datei fehlt: {db_path}")
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        blockers = [*_local_blockers(con, values, date_from, date_to), *_global_blockers(con, date_from, date_to)]
    finally:
        con.close()
    return sorted({item.fingerprint: item for item in blockers}.values(), key=lambda item: (item.rule_id, item.loco_no, item.period_start_utc))
