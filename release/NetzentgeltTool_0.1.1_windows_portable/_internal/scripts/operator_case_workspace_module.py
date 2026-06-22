"""Integrated operator case workspace for the Netzentgelt MVP.

This module is intentionally UI-only. It reads the already generated CSV exports,
does not mutate the fachliche pipeline and reuses the existing audited exception
state when an operator explicitly documents an export exception.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from export_exception_query_module import list_required_export_blockers
from export_exception_state_module import create_exception, evaluate_release_status
from local_auth_module import DEFAULT_DB_PATH, LocalAuthError, UserContext


PHASE10A_CASE_WORKSPACE_MARKER = "NETZENTGELT_OPERATOR_CASE_WORKSPACE_PHASE10A_V1_20260611"
ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "data" / "03_exports"
DUCKDB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"

SESSION_CASE_LOCO_KEY = "operator_case_loco"
SESSION_CASE_DAY_FROM_KEY = "operator_case_day_from"
SESSION_CASE_DAY_TO_KEY = "operator_case_day_to"

TIMELINE_VISIBLE_COLUMNS = (
    "loco_no",
    "row_type",
    "de_event_label",
    "transport_number",
    "train_no",
    "period_start_utc",
    "period_end_utc",
    "sequence_ts",
    "gap_duration_text",
    "gap_message",
    "holder_name",
    "performing_ru",
    "country",
    "origin_name",
    "destination_name",
    "cal_route_type_home",
    "needs_manual_review",
)
TIMELINE_RENAME_MAP = {
    "loco_no": "Loknummer",
    "row_type": "Typ",
    "de_event_label": "Ereignis",
    "transport_number": "Transportnummer",
    "train_no": "Zugnummer",
    "period_start_utc": "Von UTC",
    "period_end_utc": "Bis UTC",
    "sequence_ts": "Grenzzeit UTC",
    "gap_duration_text": "GAP-Dauer",
    "gap_message": "Hinweis",
    "holder_name": "Halter",
    "performing_ru": "Nutzendes EVU",
    "country": "Land",
    "origin_name": "Startort",
    "destination_name": "Zielort",
    "cal_route_type_home": "Routentyp",
    "needs_manual_review": "Prüffall",
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        match = by_lower.get(str(candidate).lower())
        if match:
            return match
    return None


def _truthy(value: object) -> bool:
    return _clean(value).lower() in {"true", "1", "yes", "y", "ja"}


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for kwargs in (
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": None, "engine": "python", "encoding": "utf-8-sig"},
    ):
        try:
            return pd.read_csv(path, **kwargs)
        except Exception:
            continue
    return pd.DataFrame()


def sort_operator_table(table: pd.DataFrame) -> pd.DataFrame:
    """Return a stable operator order: locomotive first, then day and period."""
    if table is None or table.empty:
        return table.copy() if isinstance(table, pd.DataFrame) else pd.DataFrame()
    result = table.copy()
    preferred = [
        column
        for column in ("Loknummer", "Datum", "Von", "Bis", "Transportnummer")
        if column in result.columns
    ]
    if not preferred:
        return result.reset_index(drop=True)
    return result.sort_values(preferred, kind="stable", na_position="last").reset_index(drop=True)


def filter_loco_rows(data: pd.DataFrame, loco_no: str) -> pd.DataFrame:
    """Filter a dataframe defensively by its locomotive column."""
    if data is None or data.empty or not _clean(loco_no):
        return pd.DataFrame(columns=[] if data is None else data.columns)
    loco_col = _column(data, ["loco_no", "Loknummer", "LocomotiveNo", "locomotive_no"])
    if not loco_col:
        return pd.DataFrame(columns=data.columns)
    return data[data[loco_col].fillna("").astype(str).str.strip().eq(_clean(loco_no))].copy()


def _display_timeline(timeline: pd.DataFrame, loco_no: str) -> pd.DataFrame:
    rows = filter_loco_rows(timeline, loco_no)
    if rows.empty:
        return pd.DataFrame()
    sort_columns = [
        column for column in ("period_start_utc", "period_end_utc", "transport_number")
        if column in rows.columns
    ]
    if sort_columns:
        rows = rows.sort_values(sort_columns, kind="stable", na_position="last")
    visible = [column for column in TIMELINE_VISIBLE_COLUMNS if column in rows.columns]
    return rows[visible].rename(columns=TIMELINE_RENAME_MAP).reset_index(drop=True)


def build_gap_view(timeline: pd.DataFrame, loco_no: str) -> pd.DataFrame:
    rows = filter_loco_rows(timeline, loco_no)
    if rows.empty or "row_type" not in rows.columns:
        return pd.DataFrame()
    rows = rows[rows["row_type"].fillna("").astype(str).str.strip().str.upper().eq("GAP")].copy()
    if rows.empty:
        return pd.DataFrame()
    start = pd.to_datetime(rows.get("period_start_utc"), errors="coerce")
    end = pd.to_datetime(rows.get("period_end_utc"), errors="coerce")
    minutes = ((end - start).dt.total_seconds() / 60).round().astype("Int64")
    result = pd.DataFrame(index=rows.index)
    result["Loknummer"] = rows.get("loco_no", "")
    result["Von UTC"] = rows.get("period_start_utc", "")
    result["Bis UTC"] = rows.get("period_end_utc", "")
    result["Dauer (Minuten)"] = minutes
    result["DE-relevant"] = rows.get("gap_relevant_de", "").apply(_truthy) if "gap_relevant_de" in rows.columns else ""
    result["Nutzendes EVU"] = rows.get("performing_ru", "")
    result["Transport davor"] = rows.get("transport_number", "")
    result["Hinweis"] = rows.get("gap_message", rows.get("dq_message", ""))
    return result.reset_index(drop=True)


def build_border_crossing_view(timeline: pd.DataFrame, loco_no: str) -> pd.DataFrame:
    rows = filter_loco_rows(timeline, loco_no)
    if rows.empty or "de_event_label" not in rows.columns:
        return pd.DataFrame()
    event_text = rows["de_event_label"].fillna("").astype(str).str.strip()
    mask = event_text.str.upper().str.contains("EINFAHRT|AUSFAHRT", regex=True)
    rows = rows[mask].copy()
    if rows.empty:
        return pd.DataFrame()
    result = pd.DataFrame(index=rows.index)
    result["Loknummer"] = rows.get("loco_no", "")
    result["Grenzzeit UTC"] = rows.get("sequence_ts", rows.get("period_start_utc", ""))
    result["Ereignis"] = rows.get("de_event_label", "")
    result["Startort"] = rows.get("origin_name", "")
    result["Zielort"] = rows.get("destination_name", "")
    result["Zugnummer"] = rows.get("train_no", "")
    result["Transportnummer"] = rows.get("transport_number", "")
    result["Nutzendes EVU"] = rows.get("performing_ru", "")
    return result.reset_index(drop=True)


def build_finding_view(findings: pd.DataFrame, loco_no: str) -> pd.DataFrame:
    rows = filter_loco_rows(findings, loco_no)
    if rows.empty:
        return pd.DataFrame()
    visible = [
        column for column in (
            "severity", "rule_id", "message", "transport_number",
            "period_start_utc", "period_end_utc", "performing_ru",
        )
        if column in rows.columns
    ]
    rename = {
        "severity": "Priorität",
        "rule_id": "Regel",
        "message": "Fehlerbeschreibung",
        "transport_number": "Transportnummer",
        "period_start_utc": "Von UTC",
        "period_end_utc": "Bis UTC",
        "performing_ru": "Nutzendes EVU",
    }
    result = rows[visible].rename(columns=rename)
    preferred = [column for column in ("Priorität", "Von UTC", "Transportnummer") if column in result.columns]
    return result.sort_values(preferred, kind="stable", na_position="last").reset_index(drop=True) if preferred else result.reset_index(drop=True)


def _date_bounds_from_findings(findings: pd.DataFrame, loco_no: str) -> tuple[date, date] | None:
    rows = filter_loco_rows(findings, loco_no)
    if rows.empty:
        return None
    candidates = []
    for column in ("period_start_utc", "period_end_utc"):
        if column in rows.columns:
            candidates.append(pd.to_datetime(rows[column], errors="coerce").dropna())
    if not candidates:
        return None
    values = pd.concat(candidates, ignore_index=True).dropna()
    if values.empty:
        return None
    return values.min().date(), values.max().date()


def _performing_rus_for_loco(timeline: pd.DataFrame, findings: pd.DataFrame, loco_no: str) -> tuple[str, ...]:
    values: list[str] = []
    for source in (filter_loco_rows(timeline, loco_no), filter_loco_rows(findings, loco_no)):
        ru_col = _column(source, ["performing_ru", "Nutzendes EVU", "PerformingRU"]) if not source.empty else None
        if ru_col:
            values.extend(_clean(value) for value in source[ru_col].tolist())
    return tuple(dict.fromkeys(value for value in values if value))


def _render_case_exception_area(*, user: UserContext, timeline: pd.DataFrame, findings: pd.DataFrame, loco_no: str) -> None:
    with st.expander("⚠️ Export-Sperre begründet umgehen", expanded=False):
        st.caption(
            "Die fachliche Auffälligkeit bleibt sichtbar. Mit einer dokumentierten Ausnahme "
            "wird ausschließlich die Export-Sperre für den aktuellen Pipeline-Lauf aufgehoben."
        )
        if not DUCKDB_PATH.exists():
            st.info("DuckDB-Datei fehlt. Bitte zuerst die Pipeline ausführen.")
            return
        performing_rus = _performing_rus_for_loco(timeline, findings, loco_no)
        bounds = _date_bounds_from_findings(findings, loco_no)
        if not performing_rus or not bounds:
            st.info("Für diesen Fall konnten Exportgruppe oder Zeitraum nicht eindeutig abgeleitet werden.")
            return
        try:
            blockers = list_required_export_blockers(
                db_path=DUCKDB_PATH,
                performing_ru_values=performing_rus,
                date_from=bounds[0],
                date_to=bounds[1],
            )
            blockers = [item for item in blockers if _clean(item.loco_no) == _clean(loco_no)]
            status = evaluate_release_status(blockers, DEFAULT_DB_PATH)
        except Exception as error:
            st.error(f"Export-Ausnahmen konnten nicht ermittelt werden: {error}")
            return
        if not status.required_blockers:
            st.success("Für diese Lok besteht aktuell keine blockierende Export-Sperre.")
            return
        st.write(
            f"Root-Fehler: **{len(status.required_blockers)}** · "
            f"noch offen: **{len(status.missing_blockers)}**"
        )
        if not status.missing_blockers:
            st.success("Alle Root-Fehler dieser Lok besitzen bereits eine dokumentierte Ausnahme.")
            return
        selected_fingerprint = st.selectbox(
            "Bewegung oder Root-Fehler auswählen",
            [item.fingerprint for item in status.missing_blockers],
            format_func=lambda fingerprint: next(
                item.label() for item in status.missing_blockers if item.fingerprint == fingerprint
            ),
            key=f"operator_case_exception_{loco_no}",
        )
        selected = next(item for item in status.missing_blockers if item.fingerprint == selected_fingerprint)
        st.info(selected.message or "Keine zusätzliche Fehlerbeschreibung vorhanden.")
        comment = st.text_area(
            "Fachliche Begründung *",
            placeholder="Warum darf dieser konkrete Root-Fehler für den Export bewusst freigegeben werden?",
            key=f"operator_case_exception_comment_{loco_no}",
        )
        if st.button(
            "Ausnahme dokumentieren und Export-Sperre umgehen",
            type="primary",
            key=f"operator_case_exception_save_{loco_no}",
        ):
            try:
                create_exception(actor=user, blocker=selected, comment=comment, db_path=DEFAULT_DB_PATH)
            except LocalAuthError as error:
                st.error(str(error))
            else:
                st.success("Ausnahme wurde auditierbar dokumentiert.")
                st.rerun()


def render_case_workspace(*, user: UserContext, findings: pd.DataFrame | None = None, timeline: pd.DataFrame | None = None, compact: bool = False) -> None:
    """Render the focused case view selected from open tasks or correction cockpit."""
    loco_no = _clean(st.session_state.get(SESSION_CASE_LOCO_KEY))
    if not loco_no:
        return
    source_timeline = timeline if isinstance(timeline, pd.DataFrame) and not timeline.empty else _read_csv_safe(EXPORT_DIR / "core_loco_timeline.csv")
    source_findings = findings if isinstance(findings, pd.DataFrame) else _read_csv_safe(EXPORT_DIR / "dq_findings.csv")
    loco_timeline = _display_timeline(source_timeline, loco_no)
    gaps = build_gap_view(source_timeline, loco_no)
    crossings = build_border_crossing_view(source_timeline, loco_no)
    loco_findings = build_finding_view(source_findings, loco_no)

    st.divider()
    st.subheader(f"🔎 Fall prüfen: Lok {loco_no}")
    st.caption(
        "Hier liegen Zeitachse, Grenzübertritte, Unterbrechungen, mögliche Stehzeiten "
        "und Export-Ausnahmen in einem Arbeitsbereich zusammen."
    )
    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric("Bewegungen", len(loco_timeline))
    col_2.metric("GAPs / Stehzeiten", len(gaps))
    col_3.metric("Grenzübertritte", len(crossings))
    col_4.metric("Prüffälle", len(loco_findings))

    if compact:
        with st.expander("Fallkontext aufklappen", expanded=True):
            if loco_findings.empty:
                st.success("Für diese Lok sind keine Einzelprüffälle vorhanden.")
            else:
                st.markdown("##### Fehler und Hinweise")
                st.dataframe(loco_findings, use_container_width=True, hide_index=True)
            st.markdown("##### Zeitachse")
            if loco_timeline.empty:
                st.info("Keine Zeitachse für diese Lok vorhanden.")
            else:
                st.dataframe(loco_timeline, use_container_width=True, hide_index=True)
            st.markdown("##### Grenzübertritte")
            if crossings.empty:
                st.info("Keine Grenzübertritte für diese Lok vorhanden.")
            else:
                st.dataframe(crossings, use_container_width=True, hide_index=True)
            st.markdown("##### Unterbrechungen und mögliche Stehzeiten")
            if gaps.empty:
                st.success("Keine GAPs oder möglichen Stehzeiten für diese Lok vorhanden.")
            else:
                st.dataframe(gaps, use_container_width=True, hide_index=True)
                st.info(
                    "Eine plausible kalte Abstellung wird unten als Klassifikation "
                    "'Mögliche kalte Abstellung' dokumentiert."
                )
        return

    tab_summary, tab_timeline, tab_border, tab_gaps, tab_release = st.tabs(
        ["Übersicht", "Zeitachse", "Grenzübertritte", "Stehzeiten & GAPs", "Export-Ausnahme"]
    )
    with tab_summary:
        if loco_findings.empty:
            st.success("Für diese Lok sind keine Einzelprüffälle vorhanden.")
        else:
            st.dataframe(loco_findings, use_container_width=True, hide_index=True)
    with tab_timeline:
        if loco_timeline.empty:
            st.info("Keine Zeitachse für diese Lok vorhanden.")
        else:
            st.dataframe(loco_timeline, use_container_width=True, hide_index=True)
    with tab_border:
        if crossings.empty:
            st.info("Keine Grenzübertritte für diese Lok vorhanden.")
        else:
            st.dataframe(crossings, use_container_width=True, hide_index=True)
    with tab_gaps:
        if gaps.empty:
            st.success("Keine GAPs oder möglichen Stehzeiten für diese Lok vorhanden.")
        else:
            st.dataframe(gaps, use_container_width=True, hide_index=True)
            st.info(
                "Eine plausible kalte Abstellung wird unter 'Fall bearbeiten' als "
                "Unterbrechung fachlich klassifiziert. Wähle dort die Klassifikation "
                "'Mögliche kalte Abstellung'."
            )
    with tab_release:
        _render_case_exception_area(user=user, timeline=source_timeline, findings=source_findings, loco_no=loco_no)
