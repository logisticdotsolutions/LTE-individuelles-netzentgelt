from __future__ import annotations

"""Controller-Ansichten fuer die nachrangigen Phase-6D-Prueflisten."""

from typing import Iterable

import pandas as pd
import streamlit as st


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _col(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in df.columns}
    for candidate in candidates:
        value = by_lower.get(str(candidate).lower())
        if value:
            return value
    return None


def _format_datetime_series(series: pd.Series) -> pd.Series:
    values = pd.to_datetime(series, errors="coerce")
    return values.dt.strftime("%d.%m.%Y %H:%M").fillna("")


def _prepare_stands(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = pd.DataFrame()
    result["Loknummer"] = df.get("loco_no", "")
    result["Ort"] = df.get("location_name", "")
    if "stand_from_utc" in df.columns:
        result["Von"] = _format_datetime_series(df["stand_from_utc"])
    if "stand_to_utc" in df.columns:
        result["Bis"] = _format_datetime_series(df["stand_to_utc"])
    if "stand_duration_minutes" in df.columns:
        minutes = pd.to_numeric(df["stand_duration_minutes"], errors="coerce")
        result["Standzeit (Stunden)"] = (minutes / 60.0).round(1)
    result["Nutzendes EVU"] = df.get("performing_ru", "")
    result["Transport davor"] = df.get("transport_number", "")
    result["Transport danach"] = df.get("next_transport_number", "")
    result["Nächster Schritt"] = df.get("suggested_action", "")
    return result


def _prepare_gap_context(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = pd.DataFrame()
    result["Loknummer"] = df.get("loco_no", "")
    result["Transport davor"] = df.get("transport_number", "")
    result["Transport danach"] = df.get("next_transport_number", "")
    result["Zielort davor"] = df.get("destination_name", "")
    result["Startort danach"] = df.get("next_origin_name", "")
    if "actual_arrival_ts" in df.columns:
        result["Ankunft davor"] = _format_datetime_series(df["actual_arrival_ts"])
    if "next_actual_departure_ts" in df.columns:
        result["Abfahrt danach"] = _format_datetime_series(df["next_actual_departure_ts"])
    result["Dauer (Minuten)"] = pd.to_numeric(df.get("actual_gap_minutes", ""), errors="coerce")
    result["Kontext"] = df.get("gap_context_class", "")
    return result


def _prepare_uncertain_gaps(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    result = pd.DataFrame()
    result["Loknummer"] = df.get("loco_no", "")
    result["Transport davor"] = df.get("transport_number", "")
    result["Transport danach"] = df.get("next_transport_number", "")
    result["Zielort davor"] = df.get("destination_name", "")
    result["Startort danach"] = df.get("next_origin_name", "")
    if "approximate_gap_start_utc" in df.columns:
        result["Ungefähr von"] = _format_datetime_series(df["approximate_gap_start_utc"])
    if "approximate_gap_end_utc" in df.columns:
        result["Ungefähr bis"] = _format_datetime_series(df["approximate_gap_end_utc"])
    result["Kontext"] = df.get("gap_context_class", "")
    return result


def _download(df: pd.DataFrame, *, label: str, file_name: str, key: str) -> None:
    if df.empty:
        return
    st.download_button(
        label,
        data=df.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=file_name,
        mime="text/csv",
        key=key,
    )


def render_phase6d_review_lists(
    *,
    stand_candidates: pd.DataFrame,
    gap_context_review: pd.DataFrame,
    uncertain_gaps: pd.DataFrame,
) -> None:
    st.subheader("Weitere fachliche Prüfungen")
    st.caption(
        "Diese Listen unterstützen die fachliche Sichtung. Sie erzeugen nicht automatisch "
        "eine Meldung und verändern keine Daten in RailCube."
    )

    tab_stands, tab_border, tab_uncertain = st.tabs([
        "Mögliche kalte Abstellungen",
        "Grenzkontext prüfen",
        "Unsichere Unterbrechungen",
    ])

    with tab_stands:
        st.markdown("#### Mögliche kalte Abstellungen")
        st.caption(
            "Die Lok stand länger als acht Stunden am selben Ort. Bitte prüfen, ob eine "
            "kalte Abstellung vorliegt oder ob die Standzeit fachlich anders zu bewerten ist."
        )
        prepared = _prepare_stands(stand_candidates)
        if prepared.empty:
            st.success("Im gewählten Arbeitstag wurden keine möglichen kalten Abstellungen gefunden.")
        else:
            st.info(f"Zu prüfen: {len(prepared)} mögliche kalte Abstellungen")
            st.dataframe(prepared, use_container_width=True, hide_index=True)
            _download(
                prepared,
                label="Liste möglicher kalter Abstellungen herunterladen",
                file_name="moegliche_kalte_abstellungen.csv",
                key="phase6d_download_stands",
            )

    with tab_border:
        st.markdown("#### Grenzkontext prüfen")
        st.caption(
            "Diese Ortsketten berühren Deutschland oder einen Grenzübergang, sind aber nicht "
            "eindeutig als interne Unterbrechung klassifizierbar. Bitte nur bei fachlichem Bedarf prüfen."
        )
        prepared = _prepare_gap_context(gap_context_review)
        if prepared.empty:
            st.success("Im gewählten Arbeitstag wurden keine Grenzkontext-Fälle gefunden.")
        else:
            st.info(f"Zur Sichtung: {len(prepared)} Grenzkontext-Fälle")
            st.dataframe(prepared, use_container_width=True, hide_index=True)
            _download(
                prepared,
                label="Grenzkontext-Liste herunterladen",
                file_name="grenzkontext_pruefen.csv",
                key="phase6d_download_border_context",
            )

    with tab_uncertain:
        st.markdown("#### Unsichere Unterbrechungen")
        st.caption(
            "Bei diesen Fällen fehlt mindestens eine belastbare Zeitgrenze. Die Dauer wird "
            "bewusst nicht automatisch berechnet. R015 bleibt als nachvollziehbarer Prüffall sichtbar."
        )
        prepared = _prepare_uncertain_gaps(uncertain_gaps)
        if prepared.empty:
            st.success("Im gewählten Arbeitstag wurden keine unsicheren Unterbrechungen gefunden.")
        else:
            st.warning(f"Zu prüfen: {len(prepared)} Unterbrechungen ohne belastbare Dauer")
            st.dataframe(prepared, use_container_width=True, hide_index=True)
            _download(
                prepared,
                label="Unsichere Unterbrechungen herunterladen",
                file_name="unsichere_unterbrechungen.csv",
                key="phase6d_download_uncertain_gaps",
            )
