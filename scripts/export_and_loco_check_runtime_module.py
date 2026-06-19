from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

import pandas as pd


EXPORT_AND_LOCO_CHECK_RUNTIME_MARKER = "NETZENTGELT_EXPORT_AND_LOCO_CHECK_UI_PHASE11T_V1_20260619"


def _extract_int(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def summarize_export_error_message(message: object) -> str | None:
    """Turn verbose technical export exceptions into a compact operator message."""
    text = str(message or "")
    if "XLSX-" not in text:
        return None
    if "Export ist gesperrt" not in text and "Export ist noch gesperrt" not in text:
        return None

    missing_exceptions = _extract_int(r"Fehlende Ausnahmen:\s*(\d+)", text)
    blocked_loco_days = _extract_int(r"Blockierte Lok-Tage[^:]*:\s*(\d+)", text)
    global_blockers = _extract_int(r"Globale Blocker[^:]*:\s*(\d+)", text)

    known_counts = [value for value in [missing_exceptions, blocked_loco_days, global_blockers] if value is not None]
    total_open = missing_exceptions if missing_exceptions is not None else sum(known_counts)

    rules = Counter(re.findall(r"\bR\d+(?:\.\d+)?\b", text))
    rule_text = ""
    if rules:
        top_rules = ", ".join(f"{rule}: {count}" for rule, count in rules.most_common(4))
        rule_text = f"\n- Häufigste Regeln in den Beispielen: {top_rules}"

    lines = [
        "Export noch gesperrt.",
        f"- Offene Prüffälle: {total_open if total_open is not None else 'nicht eindeutig ermittelbar'}",
    ]
    if blocked_loco_days is not None:
        lines.append(f"- Blockierte Lok-Tage: {blocked_loco_days}")
    if global_blockers is not None:
        lines.append(f"- Globale Blocker: {global_blockers}")
    lines.append("- Nächster Schritt: Reiter '2. Offene Aufgaben' öffnen und die Fälle dort bearbeiten oder fachlich ausnehmen.")
    if rule_text:
        lines.append(rule_text)
    return "\n".join(lines)


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()


def _column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    return None


def _normalize(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _hide_non_relevant_gaps(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "row_type" not in df.columns or "gap_relevant_de" not in df.columns:
        return df
    is_gap = _normalize(df["row_type"]).str.upper().eq("GAP")
    relevant = _normalize(df["gap_relevant_de"]).str.lower().isin(["true", "1", "yes", "y", "ja"])
    return df.loc[~is_gap | relevant].copy()


def _display_columns(df: pd.DataFrame) -> pd.DataFrame:
    preferred = [
        "row_type",
        "transport_number",
        "performing_ru",
        "period_start_utc",
        "period_end_utc",
        "actual_departure_ts",
        "actual_arrival_ts",
        "origin_name",
        "origin_location",
        "destination_name",
        "destination_location",
        "gap_minutes",
        "gap_duration_minutes",
        "gap_relevant_de",
        "dq_messages",
        "decision_reason",
    ]
    columns = [column for column in preferred if column in df.columns]
    if not columns:
        return df
    result = df[columns].copy()
    return result.rename(
        columns={
            "row_type": "Typ",
            "transport_number": "Transportnummer",
            "performing_ru": "Nutzendes EVU",
            "period_start_utc": "Von",
            "period_end_utc": "Bis",
            "actual_departure_ts": "Abfahrt",
            "actual_arrival_ts": "Ankunft",
            "origin_name": "Startort",
            "origin_location": "Startort",
            "destination_name": "Zielort",
            "destination_location": "Zielort",
            "gap_minutes": "GAP Minuten",
            "gap_duration_minutes": "GAP Minuten",
            "gap_relevant_de": "DE-relevante GAP",
            "dq_messages": "Hinweise",
            "decision_reason": "Begründung",
        }
    )


def render_loco_check_fallback(st_module) -> None:
    base_dir = Path(__file__).resolve().parents[1]
    timeline_path = base_dir / "data" / "03_exports" / "core_loco_timeline.csv"
    timeline = _hide_non_relevant_gaps(_read_csv_safe(timeline_path))

    st_module.subheader("Lok prüfen")
    st_module.caption(
        "Detailansicht je Lok. Die Anzeige kommt direkt aus der berechneten Lok-Zeitachse."
    )

    if timeline.empty:
        st_module.info("Noch keine Lok-Zeitachse gefunden. Bitte zuerst die Daten aktualisieren und neu prüfen.")
        return

    loco_col = _column(timeline, ["loco_no", "LocomotiveNo", "locomotive_no"])
    if not loco_col:
        st_module.warning("Die Lok-Zeitachse enthält keine erkennbare Loknummern-Spalte.")
        st_module.dataframe(timeline.head(200), use_container_width=True, hide_index=True)
        return

    locos = sorted({value for value in _normalize(timeline[loco_col]).tolist() if value})
    if not locos:
        st_module.info("Keine Loknummern in der aktuellen Zeitachse vorhanden.")
        return

    preselected = str(st_module.session_state.get("timeline_detail_loco", "")).strip()
    default_index = locos.index(preselected) if preselected in locos else 0
    selected_loco = st_module.selectbox(
        "Loknummer",
        locos,
        index=default_index,
        key="timeline_detail_loco_fallback",
    )
    st_module.session_state["timeline_detail_loco"] = selected_loco

    work = timeline[_normalize(timeline[loco_col]).eq(selected_loco)].copy()
    for sort_column in ["period_start_utc", "sequence_ts", "actual_departure_ts"]:
        if sort_column in work.columns:
            work["_sort_ts"] = pd.to_datetime(work[sort_column], errors="coerce")
            work = work.sort_values("_sort_ts", na_position="last")
            work = work.drop(columns=["_sort_ts"], errors="ignore")
            break

    st_module.write(f"Zeilen in der Zeitachse: **{len(work)}**")
    st_module.dataframe(_display_columns(work), use_container_width=True, hide_index=True)


def install_export_and_loco_check_runtime() -> None:
    import streamlit as st

    if getattr(st, "_PHASE11T_EXPORT_AND_LOCO_CHECK_PATCHED", False):
        return

    original_error = st.error
    original_warning = st.warning
    original_tabs = st.tabs

    def patched_error(body, *args, **kwargs):
        summary = summarize_export_error_message(body)
        if summary:
            return original_warning(summary)
        return original_error(body, *args, **kwargs)

    def patched_tabs(labels, *args, **kwargs):
        tabs = original_tabs(labels, *args, **kwargs)
        label_texts = [str(label) for label in labels]
        for index, label in enumerate(label_texts):
            if "Lok prüfen" in label and index < len(tabs):
                with tabs[index]:
                    render_loco_check_fallback(st)
                break
        return tabs

    st.error = patched_error
    st.tabs = patched_tabs
    st._PHASE11T_EXPORT_AND_LOCO_CHECK_PATCHED = True
