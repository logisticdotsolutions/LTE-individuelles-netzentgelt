from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping
import re


@dataclass(frozen=True)
class PreflightIssue:
    """Ein lokal erkannter UKL-Uploadfehler oder Hinweis."""

    code: str
    message: str
    row_number: int | None = None
    blocking: bool = True


MP_ID_PATTERN = re.compile(r"^\d{13}$")


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _is_quarter_hour(value: datetime | None) -> bool:
    return bool(
        value is not None
        and value.minute in {0, 15, 30, 45}
        and value.second == 0
        and value.microsecond == 0
    )


def _row_issue(
    *,
    code: str,
    message: str,
    row_number: int,
    blocking: bool = True,
) -> PreflightIssue:
    return PreflightIssue(
        code=code,
        message=message,
        row_number=row_number,
        blocking=blocking,
    )


def _validate_assignment_time_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    require_end: bool,
    prefix: str,
) -> list[PreflightIssue]:
    """Gemeinsame UKL-Zeitregeln für Z01- und N01-Zeilen prüfen."""
    prepared_rows = list(rows)
    issues: list[PreflightIssue] = []
    intervals_by_loco: dict[str, list[tuple[datetime, datetime | None, int]]] = {}

    for index, row in enumerate(prepared_rows, start=1):
        loco = _clean(row.get("locomotive_no"))
        start = _as_datetime(row.get("usage_start"))
        end = _as_datetime(row.get("usage_end"))

        if not loco:
            issues.append(
                _row_issue(
                    code=f"{prefix}_TFZE_REQUIRED",
                    message="TfzE oder tEns fehlt.",
                    row_number=index,
                )
            )

        if start is None:
            issues.append(
                _row_issue(
                    code=f"{prefix}_BEGIN_REQUIRED",
                    message="Beginn fehlt oder ist nicht als Datum-Zeit interpretierbar.",
                    row_number=index,
                )
            )

        if require_end and end is None:
            issues.append(
                _row_issue(
                    code=f"{prefix}_END_REQUIRED",
                    message="Ende fehlt oder ist nicht als Datum-Zeit interpretierbar.",
                    row_number=index,
                )
            )

        if start is not None and not _is_quarter_hour(start):
            issues.append(
                _row_issue(
                    code=f"{prefix}_BEGIN_NOT_QUARTER_HOUR",
                    message="Beginn liegt nicht auf dem Viertelstundenraster 00/15/30/45.",
                    row_number=index,
                )
            )

        if end is not None and not _is_quarter_hour(end):
            issues.append(
                _row_issue(
                    code=f"{prefix}_END_NOT_QUARTER_HOUR",
                    message="Ende liegt nicht auf dem Viertelstundenraster 00/15/30/45.",
                    row_number=index,
                )
            )

        if start is not None and end is not None:
            duration_minutes = (end - start).total_seconds() / 60.0

            if duration_minutes <= 0:
                issues.append(
                    _row_issue(
                        code=f"{prefix}_INVALID_PERIOD_ORDER",
                        message="Beginn muss zeitlich vor Ende liegen.",
                        row_number=index,
                    )
                )
            elif duration_minutes < 15:
                issues.append(
                    _row_issue(
                        code=f"{prefix}_PERIOD_TOO_SHORT",
                        message="Der Zeitraum ist kürzer als 15 Minuten.",
                        row_number=index,
                    )
                )

        if loco and start is not None:
            intervals_by_loco.setdefault(loco, []).append((start, end, index))

    for loco, intervals in intervals_by_loco.items():
        ordered = sorted(intervals, key=lambda item: item[0])

        for previous, current in zip(ordered, ordered[1:]):
            previous_start, previous_end, previous_index = previous
            current_start, _current_end, current_index = current

            if previous_end is None or current_start < previous_end:
                issues.append(
                    _row_issue(
                        code=f"{prefix}_OVERLAP",
                        message=(
                            f"Zeitraum überschneidet sich für Lok {loco} mit Zeile "
                            f"{previous_index}."
                        ),
                        row_number=current_index,
                    )
                )

    return issues


def _validate_vens_rows(
    rows: Iterable[Mapping[str, object]],
    *,
    prefix: str,
) -> list[PreflightIssue]:
    """Verhindern, dass ein PerformingRU-Firmenname als vEns exportiert wird."""
    issues: list[PreflightIssue] = []

    for index, row in enumerate(rows, start=1):
        user_vens = _clean(row.get("user_vens"))
        performing_ru = _clean(row.get("performing_ru"))

        if not user_vens:
            issues.append(
                _row_issue(
                    code=f"{prefix}_VENS_REQUIRED",
                    message="Nutzer-vEns fehlt.",
                    row_number=index,
                )
            )
        elif performing_ru and user_vens.casefold() == performing_ru.casefold():
            issues.append(
                _row_issue(
                    code=f"{prefix}_VENS_COMPANY_NAME_FALLBACK",
                    message=(
                        "Nutzer-vEns wurde nur durch den PerformingRU-Firmennamen ersetzt. "
                        "Vor dem Upload ist ein gültiges vEns-Mapping erforderlich."
                    ),
                    row_number=index,
                )
            )

    return issues


def validate_z01_rows(rows: Iterable[Mapping[str, object]]) -> list[PreflightIssue]:
    """UKL-Z01-Zuordnungen lokal nach den dokumentierten Portalregeln prüfen."""
    prepared_rows = list(rows)
    return [
        *_validate_assignment_time_rows(
            prepared_rows,
            require_end=False,
            prefix="Z01",
        ),
        *_validate_vens_rows(
            prepared_rows,
            prefix="Z01",
        ),
    ]


def validate_n01_rows(rows: Iterable[Mapping[str, object]]) -> list[PreflightIssue]:
    """UKL-N01-Nutzungsmeldungen lokal auf Pflichtfelder und Kernregeln prüfen."""
    prepared_rows = list(rows)
    issues = [
        *_validate_assignment_time_rows(
            prepared_rows,
            require_end=False,
            prefix="N01",
        ),
        *_validate_vens_rows(
            prepared_rows,
            prefix="N01",
        ),
    ]

    for index, row in enumerate(prepared_rows, start=1):
        recipient_mp_id = _clean(row.get("holder_market_partner_id"))

        if not recipient_mp_id:
            issues.append(
                _row_issue(
                    code="N01_RECIPIENT_MP_ID_REQUIRED",
                    message="Marktpartner-ID für Nutzungsüberlassung fehlt.",
                    row_number=index,
                )
            )
        elif not MP_ID_PATTERN.fullmatch(recipient_mp_id):
            issues.append(
                _row_issue(
                    code="N01_RECIPIENT_MP_ID_INVALID",
                    message="Marktpartner-ID für Nutzungsüberlassung muss aus 13 Ziffern bestehen.",
                    row_number=index,
                )
            )

    return issues


def validate_ae01_rows(rows: Iterable[Mapping[str, object]]) -> list[PreflightIssue]:
    """AE01-Aufenthaltsereignisse gegen Pflichtfelder und Netzstatus prüfen."""
    issues: list[PreflightIssue] = []
    allowed_status = {"netzintern", "netzextern", "einfahrend", "ausfahrend"}

    for index, row in enumerate(rows, start=1):
        loco = _clean(row.get("locomotive_no"))
        user_vens = _clean(row.get("user_vens"))
        performing_ru = _clean(row.get("performing_ru"))
        event_location = _clean(row.get("event_location"))
        event_ts = _as_datetime(row.get("event_ts"))
        network_status = _clean(row.get("network_status")).lower()

        if not loco:
            issues.append(_row_issue(code="AE01_TFZE_REQUIRED", message="TfzE oder tEns fehlt.", row_number=index))
        if not user_vens:
            issues.append(_row_issue(code="AE01_VENS_REQUIRED", message="vEns fehlt.", row_number=index))
        elif performing_ru and user_vens.casefold() == performing_ru.casefold():
            issues.append(
                _row_issue(
                    code="AE01_VENS_COMPANY_NAME_FALLBACK",
                    message="vEns wurde durch den PerformingRU-Firmennamen ersetzt. Gültiges vEns-Mapping erforderlich.",
                    row_number=index,
                )
            )
        if not event_location:
            issues.append(_row_issue(code="AE01_LOCATION_REQUIRED", message="Ort fehlt.", row_number=index))
        if event_ts is None:
            issues.append(_row_issue(code="AE01_TIMESTAMP_REQUIRED", message="Zeitpunkt fehlt oder ist ungültig.", row_number=index))
        if network_status not in allowed_status:
            issues.append(_row_issue(code="AE01_NETWORK_STATUS_INVALID", message="Netzstatus ist ungültig.", row_number=index))

    return issues


def raise_if_blocking_issues(
    issues: Iterable[PreflightIssue],
    *,
    export_name: str,
) -> None:
    """Produktiven Download bei lokal erkannten UKL-Uploadfehlern blockieren."""
    blocking = [issue for issue in issues if issue.blocking]

    if not blocking:
        return

    examples = " | ".join(
        f"{issue.code} Zeile {issue.row_number or '-'}: {issue.message}"
        for issue in blocking[:8]
    )

    suffix = "" if len(blocking) <= 8 else f" | weitere Fehler: {len(blocking) - 8}"

    raise RuntimeError(
        f"{export_name} ist durch die UKL-Preflight-Prüfung gesperrt. "
        f"Erkannte Fehler: {len(blocking)}. {examples}{suffix}"
    )


def summarize_issues_by_row(
    issues: Iterable[PreflightIssue],
) -> dict[int, str]:
    """Preflight-Gründe für die eingebettete Vorschau je Datenzeile bündeln."""
    result: dict[int, list[str]] = {}

    for issue in issues:
        if issue.row_number is None:
            continue
        result.setdefault(issue.row_number, []).append(
            f"{issue.code}: {issue.message}"
        )

    return {
        row_number: " | ".join(messages)
        for row_number, messages in result.items()
    }
