from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import streamlit as st

from export_module import list_non_lte_performing_rus, list_unconfigured_lte_performing_rus
from rest_export_module import PRIMARY_EXPORT_GROUPS
from zuordnungen_export_module import build_zuordnungen_xlsx


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXPORT_TAB_LABEL = "5. Exporte erstellen"


def _as_date(value: object, fallback: date) -> date:
    """Streamlit-Session-Wert defensiv als Datum übernehmen."""
    return value if isinstance(value, date) else fallback


@st.cache_data(show_spinner=False)
def build_zuordnungen_download_cached(
    db_path_text: str,
    db_mtime_ns: int,
    performing_ru_values: tuple[str, ...],
    export_label: str,
    date_from_iso: str,
    date_to_iso: str,
):
    """UKL-Zuordnungen bis zur nächsten DuckDB-Änderung cachen."""
    _ = db_mtime_ns

    return build_zuordnungen_xlsx(
        db_path=Path(db_path_text),
        performing_ru_values=performing_ru_values,
        export_label=export_label,
        date_from=date.fromisoformat(date_from_iso),
        date_to=date.fromisoformat(date_to_iso),
    )


def _render_download(
    *,
    title: str,
    export_label: str,
    performing_ru_values: Iterable[str],
    date_from_value: date,
    date_to_value: date,
    key_suffix: str,
) -> None:
    """Einen RU-spezifischen Zuordnungsdownload anzeigen."""
    st.markdown(f"#### {title}")

    try:
        result = build_zuordnungen_download_cached(
            db_path_text=str(DB_PATH),
            db_mtime_ns=DB_PATH.stat().st_mtime_ns,
            performing_ru_values=tuple(performing_ru_values),
            export_label=export_label,
            date_from_iso=date_from_value.isoformat(),
            date_to_iso=date_to_value.isoformat(),
        )
    except Exception as error:
        st.error(f"XLSX-Zuordnungen konnten nicht erzeugt werden: {error}")
        return

    st.caption(
        f"Exportzeilen: {result.row_count}. "
        "UKL-Version: Z01. Sortierung: LocomotiveNo, danach Beginn der Zuordnung."
    )

    if result.missing_required_field_count > 0:
        st.warning(
            f"{result.missing_required_field_count} Exportzeilen enthalten "
            "mindestens ein leeres Pflichtfeld."
        )

    st.download_button(
        label="XLSX-Zuordnungen herunterladen",
        data=result.content,
        file_name=result.file_name,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        key=f"download_zuordnungen_{key_suffix}",
        use_container_width=True,
    )


def render_zuordnungen_export_extension() -> None:
    """Zusätzlichen UKL-Zuordnungsbereich im bestehenden Exportreiter rendern."""
    st.divider()
    st.subheader("XLSX-Zuordnungen je nutzendem EVU")
    st.caption(
        "Der Export basiert auf denselben freigegebenen Nutzungssegmenten wie die "
        "Nutzungsmeldung und erzeugt die UKL-Zuordnungsvorlage in Version Z01."
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

    for group_key, group_config in PRIMARY_EXPORT_GROUPS.items():
        _render_download(
            title=f"Zuordnungen {group_config['title']}",
            export_label=str(group_config["file_label"]),
            performing_ru_values=tuple(group_config["performing_ru_values"]),
            date_from_value=date_from_value,
            date_to_value=date_to_value,
            key_suffix=f"primary_{group_key.lower()}",
        )

    rest_values = sorted(
        set(list_non_lte_performing_rus(DB_PATH))
        | set(list_unconfigured_lte_performing_rus(DB_PATH))
    )

    if not rest_values:
        return

    st.markdown("#### Zuordnungen Rest")
    selected_ru = st.selectbox(
        "Weiteres nutzendes EVU für Zuordnungen",
        rest_values,
        key="zuordnungen_rest_performing_ru",
    )

    _render_download(
        title=f"Zuordnungen {selected_ru}",
        export_label=selected_ru,
        performing_ru_values=(selected_ru,),
        date_from_value=date_from_value,
        date_to_value=date_to_value,
        key_suffix="rest_selected",
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
    """Streamlit-Tabs so erweitern, dass Reiter 5 den UKL-Zuordnungsbereich erhält."""
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
