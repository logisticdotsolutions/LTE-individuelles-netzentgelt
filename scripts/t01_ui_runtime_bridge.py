from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import streamlit as st

import zuordnungen_ui_runtime_bridge as export_ui
from t01_export_module import build_t01_xlsx
from t01_preview_module import build_t01_preview, preview_to_xlsx_bytes


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"


@dataclass(frozen=True)
class T01UIRuntime:
    original_renderer: object


@st.cache_data(show_spinner=False)
def build_t01_preview_cached(db_path_text: str, db_mtime_ns: int, date_from_iso: str, date_to_iso: str):
    _ = db_mtime_ns
    return build_t01_preview(
        db_path=Path(db_path_text),
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


@st.cache_data(show_spinner=False)
def build_t01_download_cached(
    db_path_text: str,
    db_mtime_ns: int,
    performing_ru: str,
    virtual_extraction_point: str,
    date_from_iso: str,
    date_to_iso: str,
):
    _ = db_mtime_ns
    return build_t01_xlsx(
        db_path=Path(db_path_text),
        performing_ru_values=(performing_ru,),
        virtual_extraction_point=virtual_extraction_point,
        export_label=performing_ru,
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


def _as_date(value: object, fallback: date) -> date:
    return value if isinstance(value, date) else fallback


def render_t01_export_extension() -> None:
    st.divider()
    st.subheader("T01 Traktionsleistungen")
    st.caption(
        "Die Vorschau zeigt alle DE-relevanten Bewegungen. Fehlende vEns, Klassifikationen, "
        "Lokmerkmale oder unplausible Werte bleiben sichtbar und blockieren ausschließlich den produktiven Download."
    )
    if not DB_PATH.exists():
        st.warning("Keine produktive DuckDB gefunden. Bitte zuerst die Pipeline ausführen.")
        return

    today = date.today()
    date_from_value = _as_date(st.session_state.get("nutzungsmeldung_export_date_from"), today)
    date_to_value = _as_date(st.session_state.get("nutzungsmeldung_export_date_to"), today)

    try:
        preview_df = build_t01_preview_cached(
            str(DB_PATH), DB_PATH.stat().st_mtime_ns,
            date_from_value.isoformat(), date_to_value.isoformat(),
        )
    except Exception as error:
        st.error(f"T01-Vorschau konnte nicht erzeugt werden: {error}")
        return

    if preview_df.empty:
        st.info("Für den gewählten Zeitraum wurden keine DE-relevanten Traktionsleistungen gefunden.")
        return

    blocked = int(preview_df["Exportstatus"].astype(str).str.upper().eq("BLOCKIERT").sum())
    ready = int(preview_df["Exportstatus"].astype(str).str.upper().eq("EXPORTFÄHIG").sum())
    all_rows, ready_rows, blocked_rows = st.columns(3)
    with all_rows:
        st.metric("Vorschauzeilen", len(preview_df))
    with ready_rows:
        st.metric("Exportfähig", ready)
    with blocked_rows:
        st.metric("Blockiert", blocked)

    if blocked:
        st.warning("Die T01-Vorschau enthält blockierte Zeilen. Die Gründe stehen direkt in der Spalte Hinweis.")

    st.dataframe(preview_df, use_container_width=True, hide_index=True, height=420)
    st.download_button(
        "T01-Vorschau als XLSX herunterladen",
        data=preview_to_xlsx_bytes(preview_df),
        file_name=f"Vorschau_T01_{date_from_value.isoformat()}_bis_{date_to_value.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_t01_preview",
        use_container_width=True,
    )

    st.markdown("### Produktive T01-Downloads")
    resolved = preview_df[
        preview_df["virtuelle Entnahmestelle"].fillna("").astype(str).str.strip().ne("")
        & preview_df["PerformingRU"].fillna("").astype(str).str.strip().ne("")
    ][["PerformingRU", "virtuelle Entnahmestelle"]].drop_duplicates()

    if resolved.empty:
        st.info("Noch keine produktiven Downloads verfügbar: Es fehlen eindeutige PerformingRU-vEns-Zuordnungen.")
        return

    for _, item in resolved.sort_values(["PerformingRU", "virtuelle Entnahmestelle"]).iterrows():
        performing_ru = str(item["PerformingRU"])
        vens = str(item["virtuelle Entnahmestelle"])
        st.markdown(f"#### {performing_ru} · vEns {vens}")
        try:
            result = build_t01_download_cached(
                str(DB_PATH), DB_PATH.stat().st_mtime_ns,
                performing_ru, vens,
                date_from_value.isoformat(), date_to_value.isoformat(),
            )
        except Exception as error:
            st.error(f"T01-Download gesperrt: {error}")
            continue
        st.caption(f"Exportzeilen: {result.row_count}. UKL-Version: T01.")
        st.download_button(
            "XLSX-Traktionsleistungen herunterladen",
            data=result.content,
            file_name=result.file_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"download_t01_{performing_ru}_{vens}",
            use_container_width=True,
        )


def install_t01_export_ui_extension() -> T01UIRuntime:
    runtime = T01UIRuntime(original_renderer=export_ui.render_zuordnungen_export_extension)

    def renderer() -> None:
        runtime.original_renderer()
        render_t01_export_extension()

    export_ui.render_zuordnungen_export_extension = renderer
    return runtime


def restore_t01_export_ui_extension(runtime: T01UIRuntime) -> None:
    export_ui.render_zuordnungen_export_extension = runtime.original_renderer
