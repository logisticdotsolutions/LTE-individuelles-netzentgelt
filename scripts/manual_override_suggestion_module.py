"""
Netzentgelt MVP - regelbasierte Vorschlags-Engine für manuelle Overrides
=======================================================================

Phase 5B ergänzt ausschließlich nachvollziehbare Vorschläge. Empfehlungen werden
niemals automatisch als Override gespeichert und verändern weder Rohdaten noch
Quality Gate. Ein Fachanwender muss jeden Vorschlag im Cockpit ausdrücklich
prüfen und übernehmen.

GAP-Vorschläge werden bewusst als eindeutige Prioritätenlogik gebildet:
pro GAP entsteht höchstens ein primärer fachlicher Vorschlag. Damit werden
widersprüchliche Doppelklassifikationen wie EVU-Übernahme plus Kaltabstellung
oder Ortssprung plus Kaltabstellung vermieden.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path
import re
from typing import Iterable

import duckdb
import pandas as pd


PHASE5B_SUGGESTION_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_SUGGESTIONS_V1_20260607"
PHASE5D_SUGGESTION_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"
COLD_STAND_MIN_MINUTES = 480
BORDER_SLOT_MINUTES = 15
PERFORMING_RU_NEIGHBOUR_WINDOW_HOURS = 48
GAP_SHORT_CONTINUITY_MAX_MINUTES = 120
NO_LTE_ASSIGNMENT_CLASSIFICATION = "NO_LTE_ASSIGNMENT"
NO_LTE_ASSIGNMENT_VALUE = "Keine LTE-Zuweisung / nicht im Report"

SUGGESTION_COLUMNS = (
    "suggestion_id",
    "suggestion_type",
    "override_type",
    "classification_code",
    "confidence",
    "suggested_value",
    "transport_number",
    "loco_no",
    "period_start_utc",
    "period_end_utc",
    "source_table",
    "source_row_id",
    "reason",
    "evidence",
    "automation_policy",
)

CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@dataclass(frozen=True)
class Suggestion:
    suggestion_id: str
    suggestion_type: str
    override_type: str
    classification_code: str
    confidence: str
    suggested_value: str
    transport_number: str
    loco_no: str
    period_start_utc: str
    period_end_utc: str
    source_table: str
    source_row_id: str
    reason: str
    evidence: str
    automation_policy: str = "MANUAL_CONFIRMATION_REQUIRED"

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


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


def _columns(con, table_name: str) -> list[str]:
    return [row[0] for row in con.execute(f"describe {_quote_identifier(table_name)}").fetchall()]


def _pick(available_columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in available_columns}
    for candidate in candidates:
        if str(candidate).lower() in by_lower:
            return by_lower[str(candidate).lower()]
    return None


def _valid_loco(value: object) -> bool:
    text = _clean(value)
    return bool(text and text != "00000000000-0" and "dummy" not in text.lower())


def _parse_timestamp(value: object) -> pd.Timestamp | None:
    text = _clean(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed)


def _timestamp_text(value: object) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return ""
    return parsed.strftime("%Y-%m-%dT%H:%M:%S")


def _location_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(value).lower())


def _stable_id(*parts: object) -> str:
    payload = "|".join(_clean(part) for part in parts)
    return "SUG_" + sha1(payload.encode("utf-8")).hexdigest()[:14].upper()


def _new_suggestion(
    *,
    suggestion_type: str,
    override_type: str,
    classification_code: str = "",
    confidence: str,
    suggested_value: str = "",
    transport_number: str = "",
    loco_no: str = "",
    period_start_utc: str = "",
    period_end_utc: str = "",
    source_table: str = "",
    source_row_id: str = "",
    reason: str,
    evidence: str,
) -> Suggestion:
    suggestion_id = _stable_id(
        suggestion_type,
        override_type,
        classification_code,
        suggested_value,
        transport_number,
        loco_no,
        period_start_utc,
        period_end_utc,
        source_table,
        source_row_id,
    )
    return Suggestion(
        suggestion_id=suggestion_id,
        suggestion_type=suggestion_type,
        override_type=override_type,
        classification_code=classification_code,
        confidence=confidence.upper(),
        suggested_value=suggested_value,
        transport_number=transport_number,
        loco_no=loco_no,
        period_start_utc=period_start_utc,
        period_end_utc=period_end_utc,
        source_table=source_table,
        source_row_id=source_row_id,
        reason=reason,
        evidence=evidence,
    )


def _suggest_performing_ru(
    con,
    *,
    loco_no: str,
    period_start_utc: str,
    transport_number: str = "",
    source_table: str = "",
    source_row_id: str = "",
) -> Suggestion:
    if not loco_no or not period_start_utc or not _table_exists(con, "core_loco_timeline"):
        return _new_suggestion(
            suggestion_type="PERFORMING_RU_REVIEW",
            override_type="SET_PERFORMING_RU",
            confidence="LOW",
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Kein belastbarer PerformingRU-Vorschlag ableitbar.",
            evidence="Loknummer, Zeitanker oder Timeline fehlen.",
        )

    rows = con.execute(
        """
        with candidates as (
            select
                trim(cast(performing_ru as varchar)) as performing_ru,
                period_start_utc,
                case
                    when period_start_utc < try_cast(? as timestamp) then 'PREVIOUS'
                    else 'NEXT'
                end as neighbour_side,
                abs(epoch(period_start_utc - try_cast(? as timestamp))) as seconds_distance
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and loco_no = ?
              and period_start_utc is not null
              and nullif(trim(cast(performing_ru as varchar)), '') is not null
        )
        select performing_ru, neighbour_side, seconds_distance, period_start_utc
        from candidates
        where seconds_distance <= ?
        order by seconds_distance asc, period_start_utc asc
        limit 12
        """,
        [
            period_start_utc,
            period_start_utc,
            loco_no,
            PERFORMING_RU_NEIGHBOUR_WINDOW_HOURS * 3600,
        ],
    ).fetchall()

    if not rows:
        return _new_suggestion(
            suggestion_type="PERFORMING_RU_REVIEW",
            override_type="SET_PERFORMING_RU",
            confidence="LOW",
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Keine angrenzende PerformingRU gefunden.",
            evidence=f"Suchfenster: ±{PERFORMING_RU_NEIGHBOUR_WINDOW_HOURS} Stunden.",
        )

    nearest_by_side: dict[str, tuple[str, float, object]] = {}
    values: list[str] = []
    for value, side, distance, timestamp in rows:
        cleaned = _clean(value)
        if cleaned and cleaned not in values:
            values.append(cleaned)
        if side not in nearest_by_side:
            nearest_by_side[side] = (cleaned, float(distance or 0), timestamp)

    previous = nearest_by_side.get("PREVIOUS")
    following = nearest_by_side.get("NEXT")

    if previous and following and previous[0] == following[0]:
        return _new_suggestion(
            suggestion_type="PERFORMING_RU_FROM_BOTH_NEIGHBOURS",
            override_type="SET_PERFORMING_RU",
            confidence="HIGH",
            suggested_value=previous[0],
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Vorherige und nachfolgende Bewegung derselben Lok zeigen dieselbe PerformingRU.",
            evidence=(
                f"Vorherige Bewegung: {_timestamp_text(previous[2])}; "
                f"nachfolgende Bewegung: {_timestamp_text(following[2])}."
            ),
        )

    if len(values) == 1:
        return _new_suggestion(
            suggestion_type="PERFORMING_RU_FROM_NEIGHBOURHOOD",
            override_type="SET_PERFORMING_RU",
            confidence="MEDIUM",
            suggested_value=values[0],
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Die erreichbaren angrenzenden Bewegungen derselben Lok zeigen eindeutig dieselbe PerformingRU.",
            evidence=f"Eindeutiger Wert im Suchfenster: {values[0]}.",
        )

    return _new_suggestion(
        suggestion_type="PERFORMING_RU_CONFLICT",
        override_type="SET_PERFORMING_RU",
        confidence="LOW",
        transport_number=transport_number,
        loco_no=loco_no,
        period_start_utc=period_start_utc,
        source_table=source_table,
        source_row_id=source_row_id,
        reason="Angrenzende Bewegungen enthalten unterschiedliche PerformingRUs. Keine Vorauswahl.",
        evidence="Gefundene Werte: " + " | ".join(values),
    )


def _collect_loco_candidates(con, transport_number: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for table_name, loco_candidates in [
        ("raw_transportdetail", ["FirstLocomotiveNo"]),
        ("raw_locomotivemovement", ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]),
    ]:
        if not _table_exists(con, table_name):
            continue
        table_columns = _columns(con, table_name)
        transport_column = _pick(table_columns, ["TransportNumber", "TransportNo", "TransportId", "TransportID"])
        loco_column = _pick(table_columns, loco_candidates)
        if not transport_column or not loco_column:
            continue
        rows = con.execute(
            f"""
            select distinct nullif(trim(cast({_quote_identifier(loco_column)} as varchar)), '')
            from {_quote_identifier(table_name)}
            where nullif(trim(cast({_quote_identifier(transport_column)} as varchar)), '') = ?
            """,
            [transport_number],
        ).fetchall()
        for (value,) in rows:
            cleaned = _clean(value)
            if _valid_loco(cleaned):
                result.setdefault(cleaned, set()).add(table_name)
    return result


def _suggest_loco_no(
    con,
    *,
    transport_number: str,
    loco_no: str = "",
    period_start_utc: str = "",
    source_table: str = "",
    source_row_id: str = "",
) -> Suggestion:
    if not transport_number:
        return _new_suggestion(
            suggestion_type="LOCO_NO_REVIEW",
            override_type="SET_LOCO_NO",
            confidence="LOW",
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Keine Transportnummer vorhanden. Loknummer kann nicht sicher vorgeschlagen werden.",
            evidence="Mindestens die Transportnummer ist erforderlich.",
        )

    candidates = _collect_loco_candidates(con, transport_number)
    if len(candidates) == 1:
        candidate, sources = next(iter(candidates.items()))
        confidence = "HIGH" if len(sources) >= 2 else "MEDIUM"
        return _new_suggestion(
            suggestion_type="LOCO_NO_FROM_TRANSPORT",
            override_type="SET_LOCO_NO",
            confidence=confidence,
            suggested_value=candidate,
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Für den Transport wurde genau eine plausible Loknummer gefunden.",
            evidence="Fundstellen: " + " | ".join(sorted(sources)),
        )
    if len(candidates) > 1:
        return _new_suggestion(
            suggestion_type="LOCO_NO_CONFLICT",
            override_type="SET_LOCO_NO",
            confidence="LOW",
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Mehrere plausible Loknummern gefunden. Keine Vorauswahl.",
            evidence="Gefundene Werte: " + " | ".join(sorted(candidates)),
        )
    return _new_suggestion(
        suggestion_type="LOCO_NO_REVIEW",
        override_type="SET_LOCO_NO",
        confidence="LOW",
        transport_number=transport_number,
        loco_no=loco_no,
        period_start_utc=period_start_utc,
        source_table=source_table,
        source_row_id=source_row_id,
        reason="Keine plausible Loknummer in den vorhandenen Transportdaten gefunden.",
        evidence="TransportDetail und LocomotiveMovement wurden geprüft.",
    )


def _derive_sequence_candidate(row: dict[str, object]) -> tuple[str, str, str]:
    clean_dir = _clean(row.get("clean_dir")).upper()
    faulty_dir = _clean(row.get("faulty_dir")).upper()
    departure = _timestamp_text(row.get("actual_departure_ts"))
    arrival = _timestamp_text(row.get("actual_arrival_ts"))

    if faulty_dir == "E" and arrival:
        return arrival, "MEDIUM", "FaultyDir=E: Einfahrt wird fachlich bei ActualArrival verankert."
    if faulty_dir == "A" and departure:
        return departure, "MEDIUM", "FaultyDir=A: Ausfahrt wird fachlich bei ActualDeparture verankert."
    if clean_dir in {"E", "E/A"} and departure:
        return departure, "MEDIUM", f"CleanDir={clean_dir}: Einfahrt wird fachlich bei ActualDeparture verankert."
    if clean_dir == "A" and arrival:
        return arrival, "MEDIUM", "CleanDir=A: Ausfahrt wird fachlich bei ActualArrival verankert."
    if departure:
        return departure, "LOW", "Keine eindeutige Grenzrichtung; ActualDeparture wird nur als Prüfvorschlag angezeigt."
    if arrival:
        return arrival, "LOW", "ActualDeparture fehlt; ActualArrival wird nur als Prüfvorschlag angezeigt."
    return "", "LOW", "Kein Zeitwert für einen Grenzzeitanker-Vorschlag vorhanden."


def _suggest_sequence_ts(
    con,
    *,
    transport_number: str,
    loco_no: str,
    period_start_utc: str,
    period_end_utc: str = "",
    source_table: str = "",
    source_row_id: str = "",
) -> Suggestion:
    if not _table_exists(con, "core_loco_timeline"):
        candidate, confidence, reason = period_start_utc, "LOW", "Timeline fehlt; vorhandener Startwert wird nur als Prüfvorschlag angezeigt."
        return _new_suggestion(
            suggestion_type="SEQUENCE_TS_REVIEW",
            override_type="SET_SEQUENCE_TS",
            confidence=confidence,
            suggested_value=candidate,
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason=reason,
            evidence="Keine Timeline-Auswertung verfügbar.",
        )

    conditions = ["row_type = 'MOVEMENT'"]
    params: list[object] = []
    if transport_number:
        conditions.append("nullif(trim(cast(transport_number as varchar)), '') = ?")
        params.append(transport_number)
    if loco_no:
        conditions.append("nullif(trim(cast(loco_no as varchar)), '') = ?")
        params.append(loco_no)
    if source_row_id:
        conditions.append("source_row_id = try_cast(? as bigint)")
        params.append(source_row_id)
    elif period_start_utc:
        conditions.append("period_start_utc = try_cast(? as timestamp)")
        params.append(period_start_utc)

    rows = con.execute(
        """
        select
            clean_dir,
            faulty_dir,
            actual_departure_ts,
            actual_arrival_ts,
            sequence_ts,
            source_table,
            source_row_id
        from core_loco_timeline
        where """ + " and ".join(conditions) + " limit 2",
        params,
    ).fetchall()

    if len(rows) != 1:
        return _new_suggestion(
            suggestion_type="SEQUENCE_TS_REVIEW",
            override_type="SET_SEQUENCE_TS",
            confidence="LOW",
            suggested_value=period_start_utc,
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Grenzzeitanker kann nicht eindeutig auf eine Movement-Zeile zurückgeführt werden.",
            evidence=f"Treffer in core_loco_timeline: {len(rows)}.",
        )

    row = {
        "clean_dir": rows[0][0],
        "faulty_dir": rows[0][1],
        "actual_departure_ts": rows[0][2],
        "actual_arrival_ts": rows[0][3],
        "sequence_ts": rows[0][4],
    }
    candidate, confidence, reason = _derive_sequence_candidate(row)
    return _new_suggestion(
        suggestion_type="SEQUENCE_TS_FROM_DIRECTION",
        override_type="SET_SEQUENCE_TS",
        confidence=confidence,
        suggested_value=candidate,
        transport_number=transport_number,
        loco_no=loco_no,
        period_start_utc=period_start_utc,
        period_end_utc=period_end_utc,
        source_table=source_table or _clean(rows[0][5]),
        source_row_id=source_row_id or _clean(rows[0][6]),
        reason=reason,
        evidence=(
            f"CleanDir={_clean(rows[0][0]) or '-'}; FaultyDir={_clean(rows[0][1]) or '-'}; "
            f"ActualDeparture={_timestamp_text(rows[0][2]) or '-'}; ActualArrival={_timestamp_text(rows[0][3]) or '-'}; "
            f"bisheriger Sequence-Zeitanker={_timestamp_text(rows[0][4]) or '-'}"
        ),
    )


def _round_to_slot(value: object, minutes: int = BORDER_SLOT_MINUTES) -> tuple[str, int]:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "", 0
    base = parsed.to_pydatetime().replace(second=0, microsecond=0)
    midnight = base.replace(hour=0, minute=0)
    minutes_since_midnight = int((base - midnight).total_seconds() // 60)
    rounded_minutes = int(round(minutes_since_midnight / minutes) * minutes)
    rounded = midnight + timedelta(minutes=rounded_minutes)
    delta = int(abs((rounded - base).total_seconds()) // 60)
    return rounded.strftime("%Y-%m-%dT%H:%M:%S"), delta


def _movement_rows(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return pd.DataFrame()
    result = timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("MOVEMENT")
    ].copy()
    if result.empty:
        return result
    result["_sort_ts"] = pd.to_datetime(
        result.get("sequence_ts", result.get("period_start_utc", "")),
        errors="coerce",
    )
    return result.sort_values(["loco_no", "_sort_ts", "source_row_id"], na_position="last")


def _gap_rows(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return pd.DataFrame()
    return timeline[
        timeline["row_type"].fillna("").astype(str).str.strip().str.upper().eq("GAP")
    ].copy()


def _bool_flag(value: object) -> bool:
    return _clean(value).lower() in {"true", "1", "yes", "y", "ja"}


def _timeline_with_sort_columns(timeline: pd.DataFrame) -> pd.DataFrame:
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return pd.DataFrame()
    work = timeline.copy()
    work["_gap_policy_sort_sequence"] = pd.to_numeric(
        work.get("sort_sequence", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )
    work["_gap_policy_sort_ts"] = pd.to_datetime(
        work.get("period_start_utc", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )
    work["_gap_policy_source_row_id"] = pd.to_numeric(
        work.get("source_row_id", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )
    return work


def _duration_minutes(row: pd.Series) -> float | None:
    explicit = pd.to_numeric(row.get("gap_duration_minutes"), errors="coerce")
    if not pd.isna(explicit):
        return float(explicit)
    start = _parse_timestamp(row.get("period_start_utc"))
    end = _parse_timestamp(row.get("period_end_utc"))
    if start is None or end is None or end < start:
        return None
    return float((end - start).total_seconds() / 60.0)


def _nearest_movements(ordered: pd.DataFrame, index: int) -> tuple[pd.Series | None, pd.Series | None]:
    previous = None
    for previous_index in range(index - 1, -1, -1):
        candidate = ordered.iloc[previous_index]
        if _clean(candidate.get("row_type")).upper() == "MOVEMENT":
            previous = candidate
            break

    following = None
    for following_index in range(index + 1, len(ordered)):
        candidate = ordered.iloc[following_index]
        if _clean(candidate.get("row_type")).upper() == "MOVEMENT":
            following = candidate
            break

    return previous, following


def _location_context(
    gap: pd.Series,
    previous: pd.Series | None,
    following: pd.Series | None,
) -> tuple[str, str]:
    before = _clean(gap.get("origin_name"))
    after = _clean(gap.get("destination_name"))
    if not before and previous is not None:
        before = _clean(previous.get("destination_name")) or _clean(previous.get("origin_name"))
    if not after and following is not None:
        after = _clean(following.get("origin_name")) or _clean(following.get("destination_name"))
    return before, after


def _has_location_jump(before_location: str, after_location: str) -> bool:
    if not before_location or not after_location:
        return False
    return _location_key(before_location) != _location_key(after_location)


def _same_performing_ru(previous: pd.Series | None, following: pd.Series | None) -> str:
    if previous is None or following is None:
        return ""
    previous_ru = _clean(previous.get("performing_ru"))
    following_ru = _clean(following.get("performing_ru"))
    if previous_ru and previous_ru == following_ru:
        return previous_ru
    return ""


def _gap_common_fields(gap: pd.Series, previous: pd.Series | None = None) -> dict[str, str]:
    return {
        "loco_no": _clean(gap.get("loco_no")),
        "transport_number": _clean(gap.get("transport_number")) or (_clean(previous.get("transport_number")) if previous is not None else ""),
        "period_start_utc": _timestamp_text(gap.get("period_start_utc")),
        "period_end_utc": _timestamp_text(gap.get("period_end_utc")),
        "source_table": _clean(gap.get("source_table")),
        "source_row_id": _clean(gap.get("source_row_id")),
    }


def _duration_text(duration_minutes: float | None) -> str:
    if duration_minutes is None:
        return "unbekannt"
    return f"{duration_minutes:.0f} Minuten"


def _suggest_gap_decisions(timeline: pd.DataFrame) -> list[Suggestion]:
    """Build exactly one primary suggestion per relevant GAP according to the operator policy."""
    work = _timeline_with_sort_columns(timeline)
    if work.empty:
        return []

    suggestions: list[Suggestion] = []
    for loco_no, group in work.groupby("loco_no", dropna=False):
        ordered = group.sort_values(
            ["_gap_policy_sort_sequence", "_gap_policy_sort_ts", "_gap_policy_source_row_id"],
            na_position="last",
        ).reset_index(drop=True)

        for index, gap in ordered.iterrows():
            if _clean(gap.get("row_type")).upper() != "GAP":
                continue
            if not _bool_flag(gap.get("gap_relevant_de")):
                continue

            previous, following = _nearest_movements(ordered, index)
            duration = _duration_minutes(gap)
            before_location, after_location = _location_context(gap, previous, following)
            has_jump = _has_location_jump(before_location, after_location)
            same_ru = _same_performing_ru(previous, following)
            open_end = following is None
            common = _gap_common_fields(gap, previous)
            evidence_base = (
                f"GAP-Dauer: {_duration_text(duration)}; "
                f"Ort davor: {before_location or '-'}; Ort danach: {after_location or '-'}; "
                f"PerformingRU davor/danach: {same_ru or '-'}; "
                f"offenes Ende: {'ja' if open_end else 'nein'}."
            )

            # Priorität 1: Ortssprung bedeutet fachlich keine LTE-Zuweisung im Report.
            if has_jump:
                suggestions.append(
                    _new_suggestion(
                        suggestion_type="GAP_NO_LTE_ASSIGNMENT",
                        override_type="CLASSIFY_GAP",
                        classification_code=NO_LTE_ASSIGNMENT_CLASSIFICATION,
                        confidence="MEDIUM",
                        suggested_value=NO_LTE_ASSIGNMENT_VALUE,
                        reason=(
                            "Ortssprung zwischen vorheriger und nachfolgender Bewegung erkannt. "
                            "Die Unterbrechung wird als keine LTE-Zuweisung / nicht im Report vorgeschlagen."
                        ),
                        evidence=evidence_base,
                        **common,
                    )
                )
                continue

            # Priorität 2: offene lange Standzeit bis zum letzten Datenstand wird nicht LTE zugeordnet.
            if open_end and (duration is None or duration > GAP_SHORT_CONTINUITY_MAX_MINUTES):
                suggestions.append(
                    _new_suggestion(
                        suggestion_type="GAP_NO_LTE_ASSIGNMENT",
                        override_type="CLASSIFY_GAP",
                        classification_code=NO_LTE_ASSIGNMENT_CLASSIFICATION,
                        confidence="MEDIUM",
                        suggested_value=NO_LTE_ASSIGNMENT_VALUE,
                        reason=(
                            "Längere offene Standzeit ohne nachfolgende Bewegung erkannt. "
                            "Bis zum letzten Datenstand steht die Lok weiterhin; Vorschlag: keine LTE-Zuweisung / nicht im Report."
                        ),
                        evidence=evidence_base,
                        **common,
                    )
                )
                continue

            # Priorität 3: kurze GAP unter 120 Minuten mit identischem EVU davor/danach -> EVU übernehmen.
            if duration is not None and duration < GAP_SHORT_CONTINUITY_MAX_MINUTES and same_ru:
                suggestions.append(
                    _new_suggestion(
                        suggestion_type="GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS",
                        override_type="CLASSIFY_GAP",
                        classification_code="SAME_RU_CONTINUITY",
                        confidence="HIGH",
                        suggested_value=same_ru,
                        reason=(
                            "GAP ist kürzer als 120 Minuten und direkt davor sowie danach ist dasselbe nutzende EVU vorhanden. "
                            "Vorschlag: EVU für diese Unterbrechung übernehmen."
                        ),
                        evidence=evidence_base,
                        **common,
                    )
                )
                continue

            # Priorität 4: lange GAP über 120 Minuten, kein Ortssprung, identisches EVU -> Kaltabstellung prüfen.
            if duration is not None and duration > GAP_SHORT_CONTINUITY_MAX_MINUTES and same_ru:
                suggestions.append(
                    _new_suggestion(
                        suggestion_type="POSSIBLE_COLD_STAND_SAME_LOCATION",
                        override_type="CLASSIFY_GAP",
                        classification_code="COLD_STAND",
                        confidence="MEDIUM",
                        suggested_value="Mögliche kalte Abstellung",
                        reason=(
                            "GAP ist länger als 120 Minuten, es liegt kein Ortssprung vor und direkt davor sowie danach ist dasselbe EVU vorhanden. "
                            "Vorschlag: mögliche kalte Abstellung fachlich bestätigen."
                        ),
                        evidence=evidence_base,
                        **common,
                    )
                )

    return suggestions


def _suggest_cold_stands(timeline: pd.DataFrame) -> list[Suggestion]:
    """Backward-compatible cold-stand suggester; build_suggestion_table uses the unified GAP policy."""
    return [
        suggestion
        for suggestion in _suggest_gap_decisions(timeline)
        if suggestion.suggestion_type == "POSSIBLE_COLD_STAND_SAME_LOCATION"
    ]


def _suggest_gap_performing_ru_from_neighbours(timeline: pd.DataFrame) -> list[Suggestion]:
    """Backward-compatible same-RU GAP suggester; build_suggestion_table uses the unified GAP policy."""
    return [
        suggestion
        for suggestion in _suggest_gap_decisions(timeline)
        if suggestion.suggestion_type == "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS"
    ]


def _suggest_broken_chain_gaps(timeline: pd.DataFrame) -> list[Suggestion]:
    """Backward-compatible location-jump suggester; location jumps now become no-LTE proposals."""
    return [
        suggestion
        for suggestion in _suggest_gap_decisions(timeline)
        if suggestion.suggestion_type == "GAP_NO_LTE_ASSIGNMENT"
    ]


def _suggest_border_slot_reviews(timeline: pd.DataFrame) -> list[Suggestion]:
    movements = _movement_rows(timeline)
    if movements.empty:
        return []
    suggestions: list[Suggestion] = []
    for _, row in movements.iterrows():
        clean_dir = _clean(row.get("clean_dir")).upper()
        faulty_dir = _clean(row.get("faulty_dir")).upper()
        if clean_dir not in {"E", "A", "E/A"} and faulty_dir not in {"E", "A"}:
            continue
        current = row.get("sequence_ts") or row.get("period_start_utc")
        rounded, delta = _round_to_slot(current)
        current_text = _timestamp_text(current)
        if not rounded or not current_text or delta == 0:
            continue
        suggestions.append(
            _new_suggestion(
                suggestion_type="BORDER_QUARTER_HOUR_REVIEW",
                override_type="SET_SEQUENCE_TS",
                confidence="LOW",
                suggested_value=rounded,
                loco_no=_clean(row.get("loco_no")),
                transport_number=_clean(row.get("transport_number")),
                period_start_utc=_timestamp_text(row.get("period_start_utc")),
                period_end_utc=_timestamp_text(row.get("period_end_utc")),
                source_table=_clean(row.get("source_table")),
                source_row_id=_clean(row.get("source_row_id")),
                reason="Grenzereignis liegt nicht exakt auf dem Viertelstundenraster. Rundung nur fachlich prüfen.",
                evidence=(
                    f"Bisheriger Zeitanker: {current_text}; nächster Viertelstundenwert: {rounded}; "
                    f"Abweichung: {delta} Minuten. GPS-Grenzpunktdaten liegen im Tool derzeit nicht vor."
                ),
            )
        )
    return suggestions


def _suggest_from_findings(con, findings: pd.DataFrame) -> list[Suggestion]:
    if findings is None or findings.empty:
        return []
    suggestions: list[Suggestion] = []
    for _, row in findings.iterrows():
        rule_id = _clean(row.get("rule_id")).upper()
        common = {
            "transport_number": _clean(row.get("transport_number")),
            "loco_no": _clean(row.get("loco_no")),
            "period_start_utc": _timestamp_text(row.get("period_start_utc")) or _clean(row.get("period_start_utc")),
            "source_table": _clean(row.get("source_table")),
            "source_row_id": _clean(row.get("source_row_id")),
        }
        if rule_id == "R009":
            suggestions.append(_suggest_performing_ru(con, **common))
        elif rule_id == "R012":
            suggestions.append(_suggest_loco_no(con, **common))
        elif rule_id == "R001":
            suggestions.append(
                _suggest_sequence_ts(
                    con,
                    period_end_utc=_timestamp_text(row.get("period_end_utc")) or _clean(row.get("period_end_utc")),
                    **common,
                )
            )
    return suggestions


def _deduplicate(suggestions: Iterable[Suggestion]) -> list[Suggestion]:
    result: dict[str, Suggestion] = {}
    for suggestion in suggestions:
        existing = result.get(suggestion.suggestion_id)
        if existing is None or CONFIDENCE_ORDER.get(suggestion.confidence, 99) < CONFIDENCE_ORDER.get(existing.confidence, 99):
            result[suggestion.suggestion_id] = suggestion
    return sorted(
        result.values(),
        key=lambda item: (
            CONFIDENCE_ORDER.get(item.confidence, 99),
            item.suggestion_type,
            item.loco_no,
            item.period_start_utc,
            item.transport_number,
        ),
    )


def build_suggestion_table(
    *,
    db_path: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> pd.DataFrame:
    """Aktuelle Vorschläge aus produktiver DuckDB, Findings und Timeline bilden."""
    suggestions: list[Suggestion] = []
    db_path = Path(db_path)
    if db_path.exists():
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            suggestions.extend(_suggest_from_findings(con, findings))
        finally:
            con.close()
    suggestions.extend(_suggest_gap_decisions(timeline))
    suggestions.extend(_suggest_border_slot_reviews(timeline))

    rows = [suggestion.to_dict() for suggestion in _deduplicate(suggestions)]
    return pd.DataFrame(rows, columns=SUGGESTION_COLUMNS)


def suggestion_for_case(
    *,
    db_path: Path,
    override_type: str,
    transport_number: str,
    loco_no: str,
    period_start_utc: str,
    period_end_utc: str = "",
    source_table: str = "",
    source_row_id: str = "",
) -> Suggestion:
    """Einzelvorschlag für das manuelle Formular ableiten."""
    override_type = _clean(override_type).upper()
    db_path = Path(db_path)
    if not db_path.exists():
        return _new_suggestion(
            suggestion_type="MANUAL_REVIEW",
            override_type=override_type,
            confidence="LOW",
            suggested_value=period_start_utc if override_type in {"SET_SEQUENCE_TS", "SET_ACTUAL_DEPARTURE"} else "",
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Produktive DuckDB fehlt. Nur manuelle Erfassung möglich.",
            evidence="Keine Datenbankverbindung verfügbar.",
        )

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        common = {
            "transport_number": transport_number,
            "loco_no": loco_no,
            "period_start_utc": period_start_utc,
            "source_table": source_table,
            "source_row_id": source_row_id,
        }
        if override_type == "SET_PERFORMING_RU":
            return _suggest_performing_ru(con, **common)
        if override_type == "SET_LOCO_NO":
            return _suggest_loco_no(con, **common)
        if override_type == "SET_SEQUENCE_TS":
            return _suggest_sequence_ts(con, period_end_utc=period_end_utc, **common)
    finally:
        con.close()

    if override_type == "SET_ACTUAL_DEPARTURE":
        return _new_suggestion(
            suggestion_type="ACTUAL_DEPARTURE_REVIEW",
            override_type=override_type,
            confidence="LOW",
            suggested_value=period_start_utc,
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Bisherige Abfahrtszeit wird als Startwert angezeigt. Fachliche Korrektur erforderlich.",
            evidence="Keine automatische Änderung.",
        )
    if override_type == "SET_ACTUAL_ARRIVAL":
        return _new_suggestion(
            suggestion_type="ACTUAL_ARRIVAL_REVIEW",
            override_type=override_type,
            confidence="LOW",
            suggested_value=period_end_utc,
            transport_number=transport_number,
            loco_no=loco_no,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            source_table=source_table,
            source_row_id=source_row_id,
            reason="Bisherige Ankunftszeit wird als Startwert angezeigt. Fachliche Korrektur erforderlich.",
            evidence="Keine automatische Änderung.",
        )
    return _new_suggestion(
        suggestion_type="DOCUMENTATION_REVIEW",
        override_type=override_type,
        confidence="LOW",
        transport_number=transport_number,
        loco_no=loco_no,
        period_start_utc=period_start_utc,
        period_end_utc=period_end_utc,
        source_table=source_table,
        source_row_id=source_row_id,
        reason="Dokumentationsfall ohne automatische fachliche Wirkung.",
        evidence="Klassifikation und Kommentar durch Fachanwender erforderlich.",
    )
