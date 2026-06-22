from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import streamlit as st

from zuordnungen_export_module import (
    LTE_HOLDING_MARKET_PARTNER_IDS,
    LTE_HOLDING_MARKET_PARTNER_NAME,
    build_zuordnungen_holding_xlsx,
)
from zuordnungen_preview_module import (
    build_zuordnungen_holding_preview,
    preview_to_xlsx_bytes,
)


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXPORT_TAB_LABEL = "5. Exporte erstellen"


def _as_date(value: object, fallback: date) -> date:
    """Streamlit-Session-Wert defensiv als Datum übernehmen."""
    return value if isinstance(value, date) else fallback


@st.cache_data(show_spinner=False)
def build_zuordnungen_holding_download_cached(
    db_path_text: str,
    db_mtime_ns: int,
    holding_market_partner_id: str,
    date_from_iso: str,
    date_to_iso: str,
):
    """Holding-Zuordnung bis zur nächsten DuckDB-Änderung cachen."""
    _ = db_mtime_ns

    return build_zuordnungen_holding_xlsx(
        db_path=Path(db_path_text),
        holding_market_partner_id=holding_market_partner_id,
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


@st.cache_data(show_spinner=False)
def build_zuordnungen_holding_preview_cached(
    db_path_text: str,
    db_mtime_ns: int,
    date_from_iso: str,
    date_to_iso: str,
):
    """Holding-Vorschau inklusive blockierter Zeilen bis zur DB-Änderung cachen."""
    _ = db_mtime_ns

    return build_zuordnungen_holding_preview(
        db_path=Path(db_path_text),
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


def _render_preview(
    *,
    date_from_value: date,
    date_to_value: date,
) -> None:
    """Embedded-XLSX-nahe Vorschau unabhängig vom Download-Gate anzeigen."""
    st.markdown("#### Vorschau der Holding-Zuordnungen")
    st.caption(
        "Die Vorschau bleibt auch bei blockierenden Fehlern sichtbar. "
        "Blockierte Zeilen werden nicht still entfernt, sondern mit Status und Hinweis angezeigt."
    )

    try:
        preview_df = build_zuordnungen_holding_preview_cached(
            db_path_text=str(DB_PATH),
            db_mtime_ns=DB_PATH.stat().st_mtime_ns,
            date_from_iso=date_from_value.isoformat(),
            date_to_iso=date_to_value.isoformat(),
        )
    except Exception as error:
        st.error(f"Vorschau konnte nicht erzeugt werden: {error}")
        return

    if preview_df.empty:
        st.info("Für den gewählten Zeitraum wurden keine DE-relevanten Zuordnungssegmente gefunden.")
        return

    blocked_count = int(
        preview_df["Exportstatus"]
        .fillna("")
        .astype(str)
        .str.upper()
        .eq("BLOCKIERT")
        .sum()
    )
    exportable_count = int(
        preview_df["Exportstatus"]
        .fillna("")
        .astype(str)
        .str.upper()
        .eq("EXPORTFÄHIG")
        .sum()
    )

    metric_all, metric_ready, metric_blocked = st.columns(3)
    with metric_all:
        st.metric("Vorschauzeilen", len(preview_df))
    with metric_ready:
        st.metric("Exportfähig", exportable_count)
    with metric_blocked:
        st.metric("Blockiert", blocked_count)

    if blocked_count > 0:
        st.warning(
            "Die Vorschau enthält blockierte Zeilen. Die Daten bleiben sichtbar, "
            "der produktive Download bleibt jedoch gesperrt, bis die Prüffälle geklärt sind."
        )

    st.dataframe(
        preview_df,
        use_container_width=True,
        hide_index=True,
        height=420,
    )

    st.download_button(
        label="Vorschau als XLSX herunterladen",
        data=preview_to_xlsx_bytes(preview_df),
        file_name=(
            "Vorschau_Zuordnungen_LTE_Holding_"
            f"{date_from_value.isoformat()}_bis_{date_to_value.isoformat()}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_zuordnungen_holding_preview",
        use_container_width=True,
    )


def _render_holding_download(
    *,
    holding_market_partner_id: str,
    date_from_value: date,
    date_to_value: date,
) -> None:
    """Einen der beiden Holding-Z01-Downloads anzeigen."""
    st.markdown(f"#### Holding-Mandant {holding_market_partner_id}")

    try:
        result = build_zuordnungen_holding_download_cached(
            db_path_text=str(DB_PATH),
            db_mtime_ns=DB_PATH.stat().st_mtime_ns,
            holding_market_partner_id=holding_market_partner_id,
            date_from_iso=date_from_value.isoformat(),
            date_to_iso=date_to_value.isoformat(),
        )
    except Exception as error:
        st.error(f"XLSX-Zuordnungen konnten nicht erzeugt werden: {error}")
        return

    st.caption(
        f"Exportzeilen: {result.row_count}. "
        "UKL-Version: Z01. Inhalt: alle exportfähigen DE-relevanten Lok-Segmente. "
        "Sortierung: LocomotiveNo, danach Beginn der Zuordnung."
    )

    if result.missing_required_field_count > 0:
        st.warning(
            f"{result.missing_required_field_count} Exportzeilen enthalten "
            "mindestens ein leeres Pflichtfeld."
        )

    st.download_button(
        label=f"XLSX-Zuordnungen {holding_market_partner_id} herunterladen",
        data=result.content,
        file_name=result.file_name,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        key=f"download_zuordnungen_holding_{holding_market_partner_id}",
        use_container_width=True,
    )


def render_zuordnungen_export_extension() -> None:
    """Zwei feste LTE-Holding-Z01-Downloads im bestehenden Exportreiter rendern."""
    st.divider()
    st.subheader("XLSX-Zuordnungen LTE Holding")
    st.caption(
        f"Halter: {LTE_HOLDING_MARKET_PARTNER_NAME}. "
        "Die beiden Dateien enthalten denselben DE-relevanten Datenumfang. "
        "Sie unterscheiden sich ausschließlich durch die Marktpartner-ID im Dateikopf."
    )

    if not DB_PATH.exists():
        st.warning("Keine produktive DuckDB gefunden. Bitte zuerst die Pipeline ausführen.")
        return

    today = date.today()
    date_from_value = _as_date(
        st.session_state.get("nutzungsmeldung_export_date_from"),
        today,
    )
    date_to_value = _as_date(
        st.session_state.get("nutzungsmeldung_export_date_to"),
        today,
    )

    _render_preview(
        date_from_value=date_from_value,
        date_to_value=date_to_value,
    )

    st.divider()
    st.markdown("### Produktive Downloads")
    st.caption(
        "Die Download-Buttons respektieren weiterhin die Export-Gates. "
        "Bei blockierenden Fehlern bleibt die Vorschau sichtbar, der Download jedoch gesperrt."
    )

    for holding_market_partner_id in LTE_HOLDING_MARKET_PARTNER_IDS:
        _render_holding_download(
            holding_market_partner_id=holding_market_partner_id,
            date_from_value=date_from_value,
            date_to_value=date_to_value,
        )


class _InjectedExportTab:
    """Proxy, der den Zusatzbereich am Ende des bestehenden Exportreiters rendert."""

    def __init__(self, wrapped_tab) -> None:
        self._wrapped_tab = wrapped_tab

    def __enter__(self):
        return self._wrapped_tab.__enter__()

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            render_zuordnungen_export_extension()

        return self._wrapped_tab.__exit__(exc_type, exc_value, traceback)


def install_zuordnungen_export_tab_extension():
    """Streamlit-Tabs so erweitern, dass Reiter 5 den Holding-Z01-Bereich erhält."""
    original_tabs = st.tabs

    if getattr(original_tabs, "_zuordnungen_extension_installed", False):
        return original_tabs

    def patched_tabs(labels: Sequence[object]):
        rendered_tabs = original_tabs(labels)
        normalized_labels = [str(label) for label in labels]

        if EXPORT_TAB_LABEL not in normalized_labels:
            return rendered_tabs

        export_tab_index = normalized_labels.index(EXPORT_TAB_LABEL)
        rendered_tabs = list(rendered_tabs)
        rendered_tabs[export_tab_index] = _InjectedExportTab(
            rendered_tabs[export_tab_index]
        )
        return rendered_tabs

    patched_tabs._zuordnungen_extension_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_zuordnungen_export_tab_extension(original_tabs) -> None:
    """Originale Streamlit-Tabs nach Ende der Legacy-App wiederherstellen."""
    st.tabs = original_tabs
