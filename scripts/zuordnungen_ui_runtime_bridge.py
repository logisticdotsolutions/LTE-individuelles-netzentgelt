from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Sequence

import pandas as pd
import streamlit as st

from compact_export_grid_runtime_module import (
    install_compact_export_grid_runtime,
    restore_compact_export_grid_runtime,
)
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
EXPORT_DIR = ROOT / "data" / "03_exports"
EXPORT_TAB_LABEL = "5. Exporte erstellen"
GUIDED_EXPORT_OVERVIEW_MARKER = "NETZENTGELT_EXPORT_COCKPIT_SOFT_COPY_PHASE14D_V1_20260624"
_COMPACT_EXPORT_GRID_RUN_PATH = None


def _as_date(value: object, fallback: date) -> date:
    """Streamlit-Session-Wert defensiv als Datum übernehmen."""
    return value if isinstance(value, date) else fallback


def _read_export_csv(path: Path) -> pd.DataFrame:
    """Export-CSV robust lesen, ohne die UI bei fehlerhaften Dateien zu brechen."""
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception:
            return pd.DataFrame()


def _count_blocked_rows(source_df: pd.DataFrame) -> int:
    if source_df.empty:
        return 0

    for column in ["gate_status", "GateStatus", "status", "Status"]:
        if column in source_df.columns:
            return int(
                source_df[column]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
                .eq("BLOCKED")
                .sum()
            )

    return 0


def _count_relevant_findings(findings_df: pd.DataFrame) -> int:
    if findings_df.empty or "severity" not in findings_df.columns:
        return int(len(findings_df))

    relevant_levels = {"ERROR", "MANUAL_REVIEW"}
    return int(
        findings_df["severity"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(relevant_levels)
        .sum()
    )


def _render_export_guidance_card(title: str, body: str) -> None:
    st.markdown(f"**{title}**")
    st.caption(body)


def render_guided_export_overview() -> None:
    """Fachlich geführten Einstieg in den Exportreiter anzeigen."""
    st.subheader("Export-Cockpit")
    st.caption("Oben stehen die Arbeitsdateien. Details und Technik bleiben eingeklappt.")

    if not DB_PATH.exists():
        st.info("Noch keine berechneten Daten gefunden. Bitte zuerst die Tagesprüfung ausführen.")
        return

    zuordnungen_df = _read_export_csv(EXPORT_DIR / "export_zuordnungen.csv")
    nutzungsmeldung_df = _read_export_csv(EXPORT_DIR / "export_nutzungsmeldung.csv")
    export_gate_ru_df = _read_export_csv(EXPORT_DIR / "dq_export_gate_ru.csv")
    global_blockers_df = _read_export_csv(EXPORT_DIR / "dq_global_export_blockers.csv")
    findings_df = _read_export_csv(EXPORT_DIR / "dq_findings.csv")

    blocked_count = _count_blocked_rows(export_gate_ru_df) + _count_blocked_rows(global_blockers_df)
    finding_count = _count_relevant_findings(findings_df)

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        st.metric("Nutzungszeilen", int(len(nutzungsmeldung_df)))
    with metric_2:
        st.metric("Zuordnungszeilen", int(len(zuordnungen_df)))
    with metric_3:
        st.metric("Noch offen", blocked_count)
    with metric_4:
        st.metric("Prüffälle", finding_count)

    if blocked_count > 0 or finding_count > 0:
        st.info(
            "Hier ist noch etwas offen. Bitte die Fälle im Reiter '2. Offene Aufgaben' prüfen. "
            "Exportfähige Dateien können weiterhin heruntergeladen werden."
        )
    else:
        st.success("Alles bereit für die fachlichen Exporte.")

    st.info(
        "Empfohlene Reihenfolge: zuerst Nutzungs- und Aufenthaltsdateien laden, "
        "danach Zuordnungen prüfen, anschließend bei Bedarf Kontrolllisten öffnen."
    )

    card_1, card_2, card_3 = st.columns(3)
    with card_1:
        _render_export_guidance_card(
            "1. Fachliche Exporte",
            "Nutzung und Aufenthalt je nutzendem EVU.",
        )
    with card_2:
        _render_export_guidance_card(
            "2. Zuordnungen",
            "Holding-Zuordnungen für die interne Prüfung.",
        )
    with card_3:
        _render_export_guidance_card(
            "3. Kontrolllisten",
            "Nur für Audit, Kontrolle und Fehleranalyse.",
        )

    st.divider()


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
    """Holding-Vorschau inklusive offener Zeilen bis zur DB-Änderung cachen."""
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
    with st.expander("Vorschau anzeigen", expanded=False):
        try:
            preview_df = build_zuordnungen_holding_preview_cached(
                db_path_text=str(DB_PATH),
                db_mtime_ns=DB_PATH.stat().st_mtime_ns,
                date_from_iso=date_from_value.isoformat(),
                date_to_iso=date_to_value.isoformat(),
            )
        except Exception as error:
            st.info("Vorschau konnte noch nicht vorbereitet werden. Bitte Fall prüfen.")
            with st.expander("Technische Ursache anzeigen", expanded=False):
                st.code(str(error))
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

        metric_all, metric_ready, metric_open = st.columns(3)
        with metric_all:
            st.metric("Vorschauzeilen", len(preview_df))
        with metric_ready:
            st.metric("Exportfähig", exportable_count)
        with metric_open:
            st.metric("Noch offen", blocked_count)

        if blocked_count > 0:
            st.info(f"Hier ist noch etwas offen: {blocked_count} Zeilen bitte prüfen.")

        st.dataframe(
            preview_df,
            use_container_width=True,
            hide_index=True,
            height=360,
        )

        st.download_button(
            label="Vorschau XLSX",
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
    st.markdown(f"**{holding_market_partner_id}**")

    try:
        result = build_zuordnungen_holding_download_cached(
            db_path_text=str(DB_PATH),
            db_mtime_ns=DB_PATH.stat().st_mtime_ns,
            holding_market_partner_id=holding_market_partner_id,
            date_from_iso=date_from_value.isoformat(),
            date_to_iso=date_to_value.isoformat(),
        )
    except Exception as error:
        st.info("Zuordnungen konnten noch nicht vorbereitet werden. Bitte Fall prüfen.")
        with st.expander("Technische Ursache anzeigen", expanded=False):
            st.code(str(error))
        return

    st.metric("Zeilen", result.row_count)

    if result.missing_required_field_count > 0:
        st.info(
            f"Hier ist noch etwas offen: {result.missing_required_field_count} Zeilen "
            "haben noch fehlende Pflichtfelder. Bitte Fall prüfen."
        )

    st.download_button(
        label="Zuordnungen XLSX",
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
    with st.expander("Zuordnungen LTE Holding", expanded=False):
        st.caption(
            f"Halter: {LTE_HOLDING_MARKET_PARTNER_NAME}. Die beiden Downloads enthalten "
            "denselben Datenumfang und unterscheiden sich nur durch die Marktpartner-ID im Kopf."
        )

        if not DB_PATH.exists():
            st.info("Noch keine berechneten Daten gefunden. Bitte zuerst die Tagesprüfung ausführen.")
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

        st.markdown("#### Downloads")
        holding_columns = st.columns(len(LTE_HOLDING_MARKET_PARTNER_IDS), gap="large")
        for holding_column, holding_market_partner_id in zip(
            holding_columns,
            LTE_HOLDING_MARKET_PARTNER_IDS,
        ):
            with holding_column:
                _render_holding_download(
                    holding_market_partner_id=holding_market_partner_id,
                    date_from_value=date_from_value,
                    date_to_value=date_to_value,
                )


class _InjectedExportTab:
    """Proxy, der den bestehenden Exportreiter fachlich führt und erweitert."""

    def __init__(self, wrapped_tab) -> None:
        self._wrapped_tab = wrapped_tab

    def __enter__(self):
        result = self._wrapped_tab.__enter__()
        render_guided_export_overview()
        return result

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            render_zuordnungen_export_extension()

        return self._wrapped_tab.__exit__(exc_type, exc_value, traceback)


def install_zuordnungen_export_tab_extension():
    """Streamlit-Tabs so erweitern, dass Reiter 5 den Holding-Z01-Bereich erhält."""
    global _COMPACT_EXPORT_GRID_RUN_PATH

    if _COMPACT_EXPORT_GRID_RUN_PATH is None:
        _COMPACT_EXPORT_GRID_RUN_PATH = install_compact_export_grid_runtime(
            ROOT / "app" / "app.py"
        )

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
        existing = rendered_tabs[export_tab_index]
        if not isinstance(existing, _InjectedExportTab):
            rendered_tabs[export_tab_index] = _InjectedExportTab(existing)
        return rendered_tabs

    patched_tabs._zuordnungen_extension_installed = True
    st.tabs = patched_tabs
    return original_tabs


def restore_zuordnungen_export_tab_extension(original_tabs) -> None:
    """Originale Streamlit-Tabs nach Ende der Legacy-App wiederherstellen."""
    global _COMPACT_EXPORT_GRID_RUN_PATH

    if _COMPACT_EXPORT_GRID_RUN_PATH is not None:
        restore_compact_export_grid_runtime(_COMPACT_EXPORT_GRID_RUN_PATH)
        _COMPACT_EXPORT_GRID_RUN_PATH = None

    st.tabs = original_tabs
