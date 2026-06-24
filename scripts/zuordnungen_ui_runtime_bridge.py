from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd
import streamlit as st

from compact_export_grid_runtime_module import (
    install_compact_export_grid_runtime,
    restore_compact_export_grid_runtime,
)
from rest_export_module import PRIMARY_EXPORT_GROUPS


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
EXPORT_DIR = ROOT / "data" / "03_exports"
EXPORT_TAB_LABEL = "5. Exporte erstellen"
GUIDED_EXPORT_OVERVIEW_MARKER = "NETZENTGELT_EXPORT_COCKPIT_GROUPED_OVERVIEW_PHASE14G_V1_20260624"
_COMPACT_EXPORT_GRID_RUN_PATH = None


PERFORMING_RU_COLUMNS = [
    "performing_ru",
    "PerformingRU",
    "performing_ru_value",
    "current_contractant",
    "CurrentContractant",
    "RailwayUndertaking",
]
STATUS_COLUMNS = ["gate_status", "GateStatus", "status", "Status"]
SEVERITY_COLUMNS = ["severity", "Severity"]


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


def _first_existing_column(source_df: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    if source_df.empty:
        return None

    by_lower = {str(column).lower(): column for column in source_df.columns}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    return None


def _normalized_series(source_df: pd.DataFrame, column: str | None) -> pd.Series:
    if not column or column not in source_df.columns:
        return pd.Series("", index=source_df.index, dtype="object")

    return (
        source_df[column]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
    )


def _primary_ru_sets() -> dict[str, set[str]]:
    return {
        group_key: {
            str(value).strip().casefold()
            for value in group_config.get("performing_ru_values", ())
            if str(value).strip()
        }
        for group_key, group_config in PRIMARY_EXPORT_GROUPS.items()
    }


def _technical_blocked_count(source_df: pd.DataFrame) -> int:
    if source_df.empty:
        return 0

    status_col = _first_existing_column(source_df, STATUS_COLUMNS)
    if status_col:
        return int(
            source_df[status_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .eq("BLOCKED")
            .sum()
        )

    return 0


def _technical_finding_count(findings_df: pd.DataFrame) -> int:
    if findings_df.empty:
        return 0

    severity_col = _first_existing_column(findings_df, SEVERITY_COLUMNS)
    if not severity_col:
        return int(len(findings_df))

    return int(
        findings_df[severity_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .isin(["ERROR", "MANUAL_REVIEW"])
        .sum()
    )


def _filter_open_rows(source_df: pd.DataFrame) -> pd.DataFrame:
    if source_df.empty:
        return source_df

    status_col = _first_existing_column(source_df, STATUS_COLUMNS)
    severity_col = _first_existing_column(source_df, SEVERITY_COLUMNS)

    masks: list[pd.Series] = []
    if status_col:
        masks.append(
            source_df[status_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(["BLOCKED", "ERROR", "MANUAL_REVIEW"])
        )

    if severity_col:
        masks.append(
            source_df[severity_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
            .isin(["ERROR", "MANUAL_REVIEW"])
        )

    if not masks:
        return source_df.copy()

    combined = masks[0]
    for mask in masks[1:]:
        combined = combined | mask
    return source_df.loc[combined].copy()


def _count_open_by_ru_group(source_df: pd.DataFrame) -> dict[str, int]:
    counts = {"LTE_DE": 0, "LTE_NL": 0, "REST": 0, "UNGROUPED": 0}
    open_rows = _filter_open_rows(source_df)
    if open_rows.empty:
        return counts

    performing_col = _first_existing_column(open_rows, PERFORMING_RU_COLUMNS)
    if not performing_col:
        counts["UNGROUPED"] = int(len(open_rows))
        return counts

    ru_values = _normalized_series(open_rows, performing_col)
    primary_sets = _primary_ru_sets()
    assigned_mask = pd.Series(False, index=open_rows.index, dtype=bool)

    for group_key in ["LTE_DE", "LTE_NL"]:
        group_mask = ru_values.isin(primary_sets.get(group_key, set()))
        counts[group_key] += int(group_mask.sum())
        assigned_mask = assigned_mask | group_mask

    has_ru = ru_values.ne("")
    counts["REST"] += int((has_ru & ~assigned_mask).sum())
    counts["UNGROUPED"] += int((~has_ru).sum())
    return counts


def _build_export_overview_counts(
    *,
    export_gate_ru_df: pd.DataFrame,
    global_blockers_df: pd.DataFrame,
    findings_df: pd.DataFrame,
) -> dict[str, int]:
    gate_counts = _count_open_by_ru_group(export_gate_ru_df)
    finding_counts = _count_open_by_ru_group(findings_df)

    holding_open = (
        _technical_blocked_count(global_blockers_df)
        + gate_counts["UNGROUPED"]
        + finding_counts["UNGROUPED"]
    )

    return {
        "lte_de_open": gate_counts["LTE_DE"] + finding_counts["LTE_DE"],
        "lte_nl_open": gate_counts["LTE_NL"] + finding_counts["LTE_NL"],
        "rest_open": gate_counts["REST"] + finding_counts["REST"],
        "holding_open": holding_open,
        "technical_blocked": _technical_blocked_count(export_gate_ru_df)
        + _technical_blocked_count(global_blockers_df),
        "technical_findings": _technical_finding_count(findings_df),
    }


def _render_export_guidance_card(title: str, body: str) -> None:
    st.markdown(f"**{title}**")
    st.caption(body)


def render_guided_export_overview() -> None:
    """Fachlich gruppierten Einstieg in den Exportreiter anzeigen."""
    st.subheader("Export-Cockpit")
    st.caption(
        "Oben stehen nur fachliche Arbeitsbereiche. Technische Gesamtsummen sind eingeklappt."
    )

    if not DB_PATH.exists():
        st.info("Noch keine berechneten Daten gefunden. Bitte zuerst die Tagesprüfung ausführen.")
        return

    export_gate_ru_df = _read_export_csv(EXPORT_DIR / "dq_export_gate_ru.csv")
    global_blockers_df = _read_export_csv(EXPORT_DIR / "dq_global_export_blockers.csv")
    findings_df = _read_export_csv(EXPORT_DIR / "dq_findings.csv")

    counts = _build_export_overview_counts(
        export_gate_ru_df=export_gate_ru_df,
        global_blockers_df=global_blockers_df,
        findings_df=findings_df,
    )

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    with metric_1:
        st.metric("LTE DE offen", counts["lte_de_open"])
    with metric_2:
        st.metric("LTE NL offen", counts["lte_nl_open"])
    with metric_3:
        st.metric("Restliche EVUs offen", counts["rest_open"])
    with metric_4:
        st.metric("Holding-Zuordnung offen", counts["holding_open"])

    if any(
        counts[key] > 0
        for key in ["lte_de_open", "lte_nl_open", "rest_open", "holding_open"]
    ):
        st.info(
            "Hier ist noch etwas offen. Bitte die betroffenen Fälle im jeweiligen Abschnitt "
            "oder im Reiter '2. Offene Aufgaben' prüfen."
        )
    else:
        st.success("Alles bereit für die fachlichen Exporte.")

    with st.expander("Technische Gesamtsummen anzeigen", expanded=False):
        st.caption(
            "Diese Werte dienen nur zur Kontrolle und Fehleranalyse. Sie sind keine fachliche Export-Ampel."
        )
        tech_1, tech_2 = st.columns(2)
        with tech_1:
            st.metric("Blockierte Prüfzeilen", counts["technical_blocked"])
        with tech_2:
            st.metric("Prüffall-Zeilen", counts["technical_findings"])

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
            "Holding-Zuordnungen für LTE-Gesellschaften mit DE-Bezug.",
        )
    with card_3:
        _render_export_guidance_card(
            "3. Kontrolllisten",
            "Nur für Audit, Kontrolle und Fehleranalyse.",
        )

    st.divider()


def render_zuordnungen_export_extension() -> None:
    """Legacy-Hook bleibt aus Kompatibilitätsgründen erhalten.

    Die Holding-Zuordnungen werden inzwischen als eigener Hauptabschnitt im
    dedizierten Export-Cockpit gerendert.
    """
    return None


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
    """Streamlit-Tabs so erweitern, dass Reiter 5 den Export-Cockpit-Bereich erhält."""
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
