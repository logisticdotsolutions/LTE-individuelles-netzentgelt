"""Fallback diagnostics for the technical locomotive-number tab.

The legacy raw-data diagnostic is intentionally kept unchanged. This overlay only
replaces the misleading empty-state message when the audited dummy catalogue or
current R012 findings prove that technical locomotive cases exist.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
import streamlit as st

from dummy_locomotive_module import _read_mapping_rows

PHASE10C_TECHNICAL_LOCO_FALLBACK_MARKER = "NETZENTGELT_TECHNICAL_LOCO_FALLBACK_PHASE10C_V1_20260611"
ROOT = Path(__file__).resolve().parents[1]
FINDINGS_PATH = ROOT / "data" / "03_exports" / "dq_findings.csv"
_EMPTY_MESSAGE = "Keine auffälligen Transporte gefunden."


def _clean(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _column(data: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in data.columns}
    for candidate in candidates:
        match = by_lower.get(candidate.lower())
        if match:
            return match
    return None


def _read_findings(path: Path = FINDINGS_PATH) -> pd.DataFrame:
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


def build_technical_loco_fallback(findings_path: Path = FINDINGS_PATH) -> pd.DataFrame:
    """Build an auditable fallback list from R012 findings and active dummy mappings."""
    rows: list[dict[str, str]] = []
    findings = _read_findings(findings_path)
    if not findings.empty:
        rule_col = _column(findings, ("rule_id", "rule"))
        loco_col = _column(findings, ("loco_no", "LocomotiveNo", "locomotive_no"))
        transport_col = _column(findings, ("transport_number", "TransportNumber", "TransportNo"))
        message_col = _column(findings, ("message", "dq_message", "Error Message"))
        severity_col = _column(findings, ("severity", "Severity"))
        if rule_col:
            mask = findings[rule_col].fillna("").astype(str).str.strip().str.upper().eq("R012")
            for _, item in findings.loc[mask].iterrows():
                rows.append(
                    {
                        "Quelle": "Aktuelle Regelqueue",
                        "Regel": "R012",
                        "Loknummer": _clean(item.get(loco_col)) if loco_col else "",
                        "Transportnummer": _clean(item.get(transport_col)) if transport_col else "",
                        "Priorität": _clean(item.get(severity_col)) if severity_col else "ERROR",
                        "Hinweis": _clean(item.get(message_col)) if message_col else "Technische oder fehlende Loknummer",
                    }
                )

    for mapping in _read_mapping_rows():
        rows.append(
            {
                "Quelle": "Aktiver Dummy-Katalog",
                "Regel": "R012",
                "Loknummer": _clean(mapping.get("loco_no")),
                "Transportnummer": "",
                "Priorität": "KATALOG",
                "Hinweis": _clean(mapping.get("reason")) or "Bekannte Planungs-/Dummy-Loknummer",
            }
        )

    result = pd.DataFrame(
        rows,
        columns=["Quelle", "Regel", "Loknummer", "Transportnummer", "Priorität", "Hinweis"],
    )
    if result.empty:
        return result
    return (
        result
        .drop_duplicates()
        .sort_values(["Quelle", "Loknummer", "Transportnummer", "Hinweis"], kind="stable")
        .reset_index(drop=True)
    )


def _render_fallback(original_success, body: object, *args: Any, **kwargs: Any):
    if str(body).strip() != _EMPTY_MESSAGE:
        return original_success(body, *args, **kwargs)
    fallback = build_technical_loco_fallback()
    if fallback.empty:
        return original_success(body, *args, **kwargs)
    st.warning(
        "Die tagegefilterte Rohdatenprüfung enthält keine Treffer. Zusätzlich werden deshalb "
        "aktuelle R012-Findings und aktive Einträge aus dem Dummy-Katalog angezeigt. "
        "Katalogeinträge müssen nicht zwingend im gewählten Tagesfenster vorkommen."
    )
    st.dataframe(fallback, use_container_width=True, hide_index=True)
    st.download_button(
        "Technische Loknummern als CSV herunterladen",
        data=fallback.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="technische_loknummern_fallback.csv",
        mime="text/csv",
        key="download_technical_loco_fallback_csv",
    )
    return None


@contextmanager
def technical_loco_fallback_runtime() -> Iterator[None]:
    """Replace only the misleading empty-state success message during one UI run."""
    original_success = st.success

    def success_with_fallback(body: object, *args: Any, **kwargs: Any):
        return _render_fallback(original_success, body, *args, **kwargs)

    st.success = success_with_fallback
    try:
        yield
    finally:
        st.success = original_success
