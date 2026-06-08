"""
Netzentgelt MVP - Operator UI fuer eine selbsterklaerende Bedienung
=================================================================

Diese UI-Schicht uebersetzt technische Prüftabellen in eine einfache
Arbeitsoberflaeche. Die fachliche Berechnung bleibt unveraendert in Phase 2.

Ziele:
- sofort erkennen, ob ein Export moeglich ist
- blockierende Ursachen in Klartext sehen
- konkrete naechste Schritte erhalten
- technische Detailtabellen weiterhin auditierbar einsehen koennen
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import streamlit as st


DAU_UX_MARKER = "NETZENTGELT_DAU_UX_PHASE3_V1_20260607"
# NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608


RULE_TEXT = {
    "R001": (
        "Zeitanker der Bewegung fehlt",
        "Zeitangaben und Grenzlogik der Bewegung pruefen.",
    ),
    "R002": (
        "Abfahrtszeit fehlt oder ist ungueltig",
        "ActualDeparture in der Quelldatei kontrollieren.",
    ),
    "R003": (
        "Ankunftszeit fehlt oder ist ungueltig",
        "ActualArrival in der Quelldatei kontrollieren.",
    ),
    "R004": (
        "Zeitraum ist unplausibel: Abfahrt liegt nach Ankunft",
        "Zeitangaben fachlich korrigieren.",
    ),
    "R009": (
        "Nutzendes EVU fehlt",
        "Nutzendes EVU fachlich prüfen und ergänzen.",
    ),
    "R010": (
        "Ortskette ist laenger als 8 Stunden unterbrochen",
        "Fehlende Bewegung oder unplausible Ortskette pruefen.",
    ),
    "R010.5": (
        "Kurze Unterbrechung der Ortskette",
        "Hinweis pruefen. Der Export wird dadurch nicht automatisch gesperrt.",
    ),
    "R011": (
        "Zeitliche Ueberschneidung bei derselben Lok",
        "Ueberlappende Bewegungen vergleichen und fachlich bereinigen.",
    ),
    "R012": (
        "Loknummer fehlt oder technische Dummy-Lok wurde verwendet",
        "Loknummer in der Transportplanung fachlich korrigieren.",
    ),
}


@dataclass(frozen=True)
class GateSummary:
    ready_days: int
    warning_days: int
    blocked_days: int
    global_blockers: int
    excluded_rows: int
    blocking_findings: int
    info_findings: int

    @property
    def export_is_blocked(self) -> bool:
        return self.blocked_days > 0 or self.global_blockers > 0


def _column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    if df is None or df.empty:
        return None

    by_lower = {str(name).lower(): str(name) for name in df.columns}

    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]

    return None


def _normalized(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _count_status(df: pd.DataFrame, expected: str) -> int:
    status_col = _column(df, ["gate_status", "Gate_Status"])

    if not status_col:
        return 0

    return int((_normalized(df[status_col]).str.upper() == expected.upper()).sum())


def _count_severity(findings: pd.DataFrame, expected: Iterable[str]) -> int:
    severity_col = _column(findings, ["severity", "Severity"])

    if not severity_col:
        return 0

    expected_set = {value.upper() for value in expected}
    return int(_normalized(findings[severity_col]).str.upper().isin(expected_set).sum())


def summarize_gate(
    export_gate: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    excluded_export_rows: pd.DataFrame,
    findings: pd.DataFrame,
) -> GateSummary:
    """Kompakte operative Ampel aus den technischen Prüftabellen bilden."""
    return GateSummary(
        ready_days=_count_status(export_gate, "READY"),
        warning_days=_count_status(export_gate, "WARNING"),
        blocked_days=_count_status(export_gate, "BLOCKED"),
        global_blockers=0 if global_export_blockers is None else len(global_export_blockers),
        excluded_rows=0 if excluded_export_rows is None else len(excluded_export_rows),
        blocking_findings=_count_severity(findings, ["ERROR", "MANUAL_REVIEW"]),
        info_findings=_count_severity(findings, ["INFO", "WARNING"]),
    )


def _friendly_gate_reason(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()

    if not text:
        return "Automatische Pruefung ohne detaillierten Klartext. Weitere Details öffnen."

    replacements = {
        "ERROR-Findings=": "Blockierende Fehler: ",
        "MANUAL_REVIEW-Findings=": "Manuelle Pruefungen erforderlich: ",
        "Overlap-Minuten=": "Ueberschneidungsminuten: ",
        "GAPs ueber 8h=": "Unterbrechungen ueber 8 Stunden: ",
        "Nicht exportfaehige Movements=": "Nicht exportfaehige Bewegungen: ",
        "Ungeklaerte GAP-Minuten=": "Ungeklaerte Minuten: ",
        "INFO-Findings=": "Hinweise: ",
        "Movement export_ready=false": "Bewegung ist nicht exportfaehig",
        "Globaler Export-Blocker am Tag vorhanden": "Globales Problem am Tag vorhanden",
    }

    for technical, friendly in replacements.items():
        text = text.replace(technical, friendly)

    return text


def _friendly_rule(rule_id: object, message: object = "") -> tuple[str, str]:
    key = "" if pd.isna(rule_id) else str(rule_id).strip().upper()

    if key in RULE_TEXT:
        return RULE_TEXT[key]

    clean_message = "" if pd.isna(message) else str(message).strip()
    return (
        clean_message or "Prueffall ohne hinterlegte Klartextbeschreibung",
        "Weitere Details prüfen und fachlich bewerten.",
    )


def _format_date_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.strftime("%d.%m.%Y").fillna(_normalized(series))


def _format_datetime_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.strftime("%d.%m.%Y %H:%M").fillna(_normalized(series))


def _friendly_gate_table(export_gate: pd.DataFrame, only_status: str | None = None) -> pd.DataFrame:
    columns = [
        "Status",
        "Loknummer",
        "Datum",
        "Nutzendes EVU",
        "Zeitliche Abdeckung",
        "Ungeklaerte Minuten",
        "Ueberschneidungsminuten",
        "Warum?",
        "Naechster Schritt",
    ]

    if export_gate is None or export_gate.empty:
        return pd.DataFrame(columns=columns)

    work = export_gate.copy()
    status_col = _column(work, ["gate_status"])
    loco_col = _column(work, ["loco_no"])
    date_col = _column(work, ["coverage_date"])
    ru_col = _column(work, ["performing_rus", "performing_ru"])
    coverage_col = _column(work, ["coverage_pct"])
    gap_col = _column(work, ["unresolved_gap_minutes"])
    overlap_col = _column(work, ["overlap_minutes"])
    reason_col = _column(work, ["gate_reason"])

    if only_status and status_col:
        work = work[_normalized(work[status_col]).str.upper() == only_status.upper()].copy()

    if work.empty:
        return pd.DataFrame(columns=columns)

    status = _normalized(work[status_col]) if status_col else pd.Series("", index=work.index)
    reason = work[reason_col].apply(_friendly_gate_reason) if reason_col else pd.Series("", index=work.index)

    result = pd.DataFrame(index=work.index)
    result["Status"] = status.str.upper().map(
        {
            "READY": "✅ Freigegeben",
            "WARNING": "⚠️ Hinweis",
            "BLOCKED": "⛔ Gesperrt",
        }
    ).fillna(status)
    result["Loknummer"] = _normalized(work[loco_col]) if loco_col else ""
    result["Datum"] = _format_date_series(work[date_col]) if date_col else ""
    result["Nutzendes EVU"] = _normalized(work[ru_col]) if ru_col else ""
    result["Zeitliche Abdeckung"] = (
        pd.to_numeric(work[coverage_col], errors="coerce").fillna(0).round(2).astype(str) + " %"
        if coverage_col else ""
    )
    result["Ungeklaerte Minuten"] = pd.to_numeric(work[gap_col], errors="coerce").fillna(0).astype(int) if gap_col else 0
    result["Ueberschneidungsminuten"] = pd.to_numeric(work[overlap_col], errors="coerce").fillna(0).astype(int) if overlap_col else 0
    result["Warum?"] = reason
    result["Naechster Schritt"] = status.str.upper().map(
        {
            "READY": "Keine Aktion erforderlich.",
            "WARNING": "Hinweis vor dem Export fachlich kontrollieren.",
            "BLOCKED": "Lok im Detail pruefen und Ursache bereinigen.",
        }
    ).fillna("Weitere Details prüfen.")

    return result[columns].reset_index(drop=True)


def _friendly_global_blockers(global_export_blockers: pd.DataFrame) -> pd.DataFrame:
    columns = ["Status", "Datum", "Problem", "Transportnummer", "Nutzendes EVU", "Naechster Schritt"]

    if global_export_blockers is None or global_export_blockers.empty:
        return pd.DataFrame(columns=columns)

    work = global_export_blockers.copy()
    date_col = _column(work, ["blocker_date"])
    rule_col = _column(work, ["rule_id"])
    transport_col = _column(work, ["transport_number"])
    ru_col = _column(work, ["performing_ru"])
    message_col = _column(work, ["message"])

    result = pd.DataFrame(index=work.index)
    result["Status"] = "⛔ Export gesperrt"
    result["Datum"] = _format_date_series(work[date_col]) if date_col else ""
    rule_result = [
        _friendly_rule(rule_id, message)
        for rule_id, message in zip(
            work[rule_col] if rule_col else pd.Series("", index=work.index),
            work[message_col] if message_col else pd.Series("", index=work.index),
        )
    ]
    result["Problem"] = [item[0] for item in rule_result]
    result["Transportnummer"] = _normalized(work[transport_col]) if transport_col else ""
    result["Nutzendes EVU"] = _normalized(work[ru_col]) if ru_col else ""
    result["Naechster Schritt"] = [item[1] for item in rule_result]
    return result[columns].reset_index(drop=True)


def _friendly_findings(findings: pd.DataFrame, include_info: bool = True) -> pd.DataFrame:
    columns = [
        "Prioritaet",
        "Problem",
        "Loknummer",
        "Transportnummer",
        "Nutzendes EVU",
        "Von",
        "Bis",
        "Auswirkung",
        "Naechster Schritt",
        "Regel",
    ]

    if findings is None or findings.empty:
        return pd.DataFrame(columns=columns)

    work = findings.copy()
    severity_col = _column(work, ["severity"])
    rule_col = _column(work, ["rule_id", "rule"])
    loco_col = _column(work, ["loco_no"])
    transport_col = _column(work, ["transport_number"])
    ru_col = _column(work, ["performing_ru"])
    from_col = _column(work, ["period_start_utc"])
    to_col = _column(work, ["period_end_utc"])
    message_col = _column(work, ["message"])

    severity = _normalized(work[severity_col]).str.upper() if severity_col else pd.Series("", index=work.index)

    if not include_info:
        work = work[severity.isin(["ERROR", "MANUAL_REVIEW"])].copy()
        severity = _normalized(work[severity_col]).str.upper() if severity_col else pd.Series("", index=work.index)

    rule_series = work[rule_col] if rule_col else pd.Series("", index=work.index)
    message_series = work[message_col] if message_col else pd.Series("", index=work.index)
    rule_result = [_friendly_rule(rule, message) for rule, message in zip(rule_series, message_series)]

    result = pd.DataFrame(index=work.index)
    result["Prioritaet"] = severity.map(
        {
            "ERROR": "⛔ Blockierend",
            "MANUAL_REVIEW": "⛔ Manuelle Pruefung",
            "WARNING": "⚠️ Hinweis",
            "INFO": "ℹ️ Information",
        }
    ).fillna(severity)
    result["Problem"] = [item[0] for item in rule_result]
    result["Loknummer"] = _normalized(work[loco_col]) if loco_col else ""
    result["Transportnummer"] = _normalized(work[transport_col]) if transport_col else ""
    result["Nutzendes EVU"] = _normalized(work[ru_col]) if ru_col else ""
    result["Von"] = _format_datetime_series(work[from_col]) if from_col else ""
    result["Bis"] = _format_datetime_series(work[to_col]) if to_col else ""
    result["Auswirkung"] = severity.map(
        {
            "ERROR": "Export gesperrt",
            "MANUAL_REVIEW": "Export gesperrt",
            "WARNING": "Export moeglich",
            "INFO": "Keine Sperre",
        }
    ).fillna("Technisch pruefen")
    result["Naechster Schritt"] = [item[1] for item in rule_result]
    result["Regel"] = _normalized(rule_series)
    return result[columns].reset_index(drop=True)


def _render_process_steps(summary: GateSummary) -> None:
    if summary.export_is_blocked:
        task_step = f"⛔ **3. Offene Aufgaben bearbeiten:** {summary.blocked_days + summary.global_blockers} Sperrfaelle"
        export_step = "🔒 **5. Exporte erstellen:** derzeit gesperrt"
    elif summary.warning_days > 0:
        task_step = f"⚠️ **3. Hinweise kontrollieren:** {summary.warning_days} Lok-Tage mit Hinweis"
        export_step = "✅ **5. Exporte erstellen:** möglich, nach fachlicher Kontrolle"
    else:
        task_step = "✅ **3. Offene Aufgaben:** keine blockierenden Probleme"
        export_step = "✅ **5. Exporte erstellen:** freigegeben"

    st.markdown(
        "  \n".join(
            [
                "✅ **1. Daten aktualisieren:** letzter vollstaendiger Import vorhanden",
                "✅ **2. Automatische Pruefung:** automatische Prüfung wurde durchgeführt",
                task_step,
                export_step,
            ]
        )
    )


def render_operator_dashboard(
    export_gate: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    excluded_export_rows: pd.DataFrame,
    findings: pd.DataFrame,
    operational_kpis: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> None:
    """DAU-taugliche Tagespruefung auf der Startseite rendern."""
    st.subheader("Tagespruefung: Darf exportiert werden?")

    summary = summarize_gate(
        export_gate=export_gate,
        global_export_blockers=global_export_blockers,
        excluded_export_rows=excluded_export_rows,
        findings=findings,
    )

    if export_gate is None or export_gate.empty:
        st.info(
            "Die Qualitaetspruefung wurde noch nicht berechnet. "
            "Fuehre zuerst 'Daten aktualisieren und neu pruefen' aus."
        )
        return

    if summary.export_is_blocked:
        st.error(
            "⛔ Export derzeit gesperrt. "
            "Bearbeite zuerst die blockierenden Probleme im Tab '2. Offene Aufgaben'."
        )
    elif summary.warning_days > 0:
        st.warning(
            "⚠️ Export moeglich, aber fachliche Kontrolle empfohlen. "
            "Pruefe die Hinweise vor dem Download."
        )
    else:
        st.success(
            "✅ Export moeglich. Die automatische Pruefung hat keine blockierenden Probleme erkannt."
        )

    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric("Freigegebene Lok-Tage", summary.ready_days)
    col_2.metric("Lok-Tage mit Hinweis", summary.warning_days)
    col_3.metric("Gesperrte Lok-Tage", summary.blocked_days)
    col_4.metric("Globale Export-Sperren", summary.global_blockers)

    st.markdown("#### Empfohlener Ablauf")
    _render_process_steps(summary)

    blocked_days = _friendly_gate_table(export_gate, only_status="BLOCKED")

    if not blocked_days.empty:
        st.markdown("#### Warum sind Lok-Tage gesperrt?")
        st.caption(
            "Diese Probleme verhindern den Export. Nutze die Loknummer im Tab '4. Lok prüfen', "
            "um die zugehoerige Zeitachse zu kontrollieren."
        )
        st.dataframe(blocked_days.head(100), use_container_width=True, hide_index=True)

    global_table = _friendly_global_blockers(global_export_blockers)

    if not global_table.empty:
        st.markdown("#### Globale Export-Sperren")
        st.caption(
            "Diese Probleme koennen keiner eindeutigen Lok-Zeitachse zugeordnet werden, "
            "beispielsweise fehlende Loknummern oder Dummy-Loks."
        )
        st.dataframe(global_table.head(100), use_container_width=True, hide_index=True)

    with st.expander("Technische Kennzahlen und Vollstaendigkeitspruefung anzeigen", expanded=False):
        st.caption(
            "Dieser Bereich dient der Nachvollziehbarkeit und Fehlersuche. "
            "Fuer die taegliche Bedienung reichen die Ampel und der Tab 'Offene Aufgaben'."
        )

        if operational_kpis is not None and not operational_kpis.empty:
            st.markdown("**Operative Kennzahlen**")
            st.dataframe(operational_kpis, use_container_width=True, hide_index=True)

        if reconciliation is not None and not reconciliation.empty:
            st.markdown("**Vollstaendigkeitspruefung der Datenmengen**")
            st.dataframe(reconciliation, use_container_width=True, hide_index=True)

        st.write(f"Bewusst ausgeschlossene Exportzeilen: **{summary.excluded_rows}**")
        st.write(f"Blockierende Einzelprueffaelle: **{summary.blocking_findings}**")
        st.write(f"Nicht blockierende Hinweise: **{summary.info_findings}**")


def render_open_tasks(
    export_gate: pd.DataFrame,
    global_export_blockers: pd.DataFrame,
    findings: pd.DataFrame,
) -> None:
    """Verstaendliche Arbeitsliste fuer Fachanwender rendern."""
    st.subheader("Offene Aufgaben")
    st.caption(
        "Bearbeite zuerst alle blockierenden Probleme. Hinweise koennen anschliessend kontrolliert werden. "
        "Regelnummern sind nur fuer die technische Nachvollziehbarkeit eingeblendet."
    )

    blocking_gate = _friendly_gate_table(export_gate, only_status="BLOCKED")
    warning_gate = _friendly_gate_table(export_gate, only_status="WARNING")
    blockers = _friendly_global_blockers(global_export_blockers)
    finding_table = _friendly_findings(findings, include_info=True)

    blocking_findings = finding_table[
        finding_table["Auswirkung"].eq("Export gesperrt")
    ].copy() if not finding_table.empty else finding_table

    hints = finding_table[
        ~finding_table["Auswirkung"].eq("Export gesperrt")
    ].copy() if not finding_table.empty else finding_table

    tab_blocked, tab_global, tab_hints, tab_rules = st.tabs(
        [
            f"⛔ Gesperrte Lok-Tage ({len(blocking_gate)})",
            f"⛔ Globale Sperren ({len(blockers)})",
            f"⚠️ Hinweise ({len(warning_gate) + len(hints)})",
            f"Technische Einzelprueffaelle ({len(finding_table)})",
        ]
    )

    with tab_blocked:
        if blocking_gate.empty:
            st.success("Keine gesperrten Lok-Tage vorhanden.")
        else:
            st.dataframe(blocking_gate, use_container_width=True, hide_index=True)
            _render_loco_shortcut(blocking_gate)

        if not blocking_findings.empty:
            with st.expander("Zugehoerige blockierende Einzelprueffaelle anzeigen", expanded=False):
                st.dataframe(blocking_findings, use_container_width=True, hide_index=True)

    with tab_global:
        if blockers.empty:
            st.success("Keine globalen Export-Sperren vorhanden.")
        else:
            st.dataframe(blockers, use_container_width=True, hide_index=True)

    with tab_hints:
        if warning_gate.empty and hints.empty:
            st.success("Keine Hinweise vorhanden.")
        else:
            if not warning_gate.empty:
                st.markdown("**Lok-Tage mit Hinweis**")
                st.dataframe(warning_gate, use_container_width=True, hide_index=True)
                _render_loco_shortcut(warning_gate, key_suffix="warning")

            if not hints.empty:
                st.markdown("**Weitere Hinweise aus dem Regelwerk**")
                st.dataframe(hints, use_container_width=True, hide_index=True)

    with tab_rules:
        st.caption(
            "Technische Detailansicht. Im normalen Betrieb zuerst die drei vorherigen Reiter verwenden."
        )
        if finding_table.empty:
            st.info("Keine Einzelprueffaelle vorhanden.")
        else:
            st.dataframe(finding_table, use_container_width=True, hide_index=True)
            csv = finding_table.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Arbeitsliste als CSV herunterladen",
                data=csv,
                file_name="offene_aufgaben.csv",
                mime="text/csv",
                key="download_operator_tasks_csv",
            )


def _render_loco_shortcut(table: pd.DataFrame, key_suffix: str = "blocked") -> None:
    """Lok aus der Arbeitsliste fuer den vorhandenen Timeline-Tab vormerken."""
    if table.empty or "Loknummer" not in table.columns:
        return

    locos = sorted(
        {
            value
            for value in _normalized(table["Loknummer"]).tolist()
            if value
        }
    )

    if not locos:
        return

    st.markdown("**Lok direkt fuer die Detailpruefung vormerken**")
    col_select, col_button = st.columns([3, 1])

    with col_select:
        selected_loco = st.selectbox(
            "Loknummer",
            locos,
            key=f"operator_shortcut_loco_{key_suffix}",
        )

    with col_button:
        st.write("")
        st.write("")
        if st.button(
            "Lok vormerken",
            key=f"operator_shortcut_button_{key_suffix}",
            use_container_width=True,
        ):
            st.session_state["timeline_preview_loco"] = selected_loco
            st.success(
                f"Lok {selected_loco} wurde vorgemerkt. Öffne jetzt den Tab '4. Lok prüfen'."
            )
