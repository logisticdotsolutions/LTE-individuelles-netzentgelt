"""Runtime overlay for a clearer operator workflow without rewriting the legacy app.

The large Streamlit application stays stable. This bridge temporarily replaces a
few render functions while app/app.py is executed by the secure wrapper.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any, Iterator

import pandas as pd
import streamlit as st

from local_auth_module import UserContext
from operator_case_workspace_module import (
    SESSION_CASE_LOCO_KEY,
    render_case_workspace,
    sort_operator_table,
)


PHASE10A_WORKFLOW_RUNTIME_MARKER = "NETZENTGELT_OPERATOR_WORKFLOW_RUNTIME_PHASE10A_V1_20260611"
_PIPELINE_TAB_LABEL = "⚙️ Technik: Pipeline"


def _non_empty_locos(table: pd.DataFrame) -> list[str]:
    if table is None or table.empty or "Loknummer" not in table.columns:
        return []
    values = {
        str(value).strip()
        for value in table["Loknummer"].fillna("").astype(str).tolist()
        if str(value).strip()
    }
    return sorted(values)


def _render_direct_case_open(table: pd.DataFrame, *, key_suffix: str) -> None:
    """Select one locomotive and open its integrated case workspace directly."""
    locos = _non_empty_locos(table)
    if not locos:
        return
    st.markdown("##### Fall direkt prüfen")
    st.caption("Wähle die betroffene Lok direkt aus der Aufgabenliste. Kopieren oder Merken ist nicht erforderlich.")
    col_select, col_open = st.columns([3, 1])
    with col_select:
        selected_loco = st.selectbox(
            "Loknummer",
            locos,
            key=f"operator_case_open_select_{key_suffix}",
        )
    with col_open:
        st.write("")
        st.write("")
        if st.button(
            "Fall öffnen",
            type="primary",
            use_container_width=True,
            key=f"operator_case_open_button_{key_suffix}",
        ):
            st.session_state[SESSION_CASE_LOCO_KEY] = selected_loco
            st.session_state["timeline_detail_loco"] = selected_loco
            st.session_state["timeline_bookmarked_loco"] = selected_loco
            st.rerun()


def _render_compact_dashboard(*, operator_ui, export_gate, global_export_blockers, excluded_export_rows, findings, operational_kpis, reconciliation) -> None:
    summary = operator_ui.summarize_gate(
        export_gate=export_gate,
        global_export_blockers=global_export_blockers,
        excluded_export_rows=excluded_export_rows,
        findings=findings,
    )
    st.subheader("Tagesprüfung: Ist der Datenstand exportfähig?")
    if export_gate is None or export_gate.empty:
        st.info("Die Qualitätsprüfung wurde noch nicht berechnet. Führe zuerst 'Daten aktualisieren und neu prüfen' aus.")
        return
    if summary.export_is_blocked:
        st.error("⛔ Export derzeit gesperrt. Bearbeite die Fälle im Reiter '2. Offene Aufgaben'.")
    elif summary.warning_days > 0:
        st.warning("⚠️ Export möglich, aber fachliche Kontrolle empfohlen. Prüfe die Hinweise vor dem Download.")
    else:
        st.success("✅ Export möglich. Die automatische Prüfung hat keine blockierenden Probleme erkannt.")

    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric("Freigegebene Lok-Tage", summary.ready_days)
    col_2.metric("Lok-Tage mit Hinweis", summary.warning_days)
    col_3.metric("Gesperrte Lok-Tage", summary.blocked_days)
    col_4.metric("Globale Export-Sperren", summary.global_blockers)

    st.markdown("#### Empfohlener Ablauf")
    st.markdown(
        "  \n".join(
            [
                "✅ **1. Daten aktualisieren:** aktuellen Datenstand laden und prüfen",
                "🔎 **2. Offene Aufgaben:** blockierende Fälle direkt öffnen und bewerten",
                "🛠️ **3. Fall bearbeiten:** Korrektur, Klassifikation oder Ausnahme dokumentieren",
                "📦 **4. Export erstellen:** erst nach erfolgreicher Prüfung herunterladen",
            ]
        )
    )

    with st.expander("Detailtabellen und technische Kennzahlen anzeigen", expanded=False):
        st.caption("Diese Details dienen der Nachvollziehbarkeit. Für den täglichen Ablauf reicht die Aufgabenliste.")
        blocked_days = sort_operator_table(
            operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)
        )
        if not blocked_days.empty:
            st.markdown("##### Gesperrte Lok-Tage")
            st.dataframe(blocked_days, use_container_width=True, hide_index=True)
        global_table = operator_ui._friendly_global_blockers(global_export_blockers)
        if not global_table.empty:
            st.markdown("##### Globale Export-Sperren")
            st.dataframe(global_table, use_container_width=True, hide_index=True)
        if operational_kpis is not None and not operational_kpis.empty:
            st.markdown("##### Operative Kennzahlen")
            st.dataframe(operational_kpis, use_container_width=True, hide_index=True)
        if reconciliation is not None and not reconciliation.empty:
            st.markdown("##### Vollständigkeitsprüfung")
            st.dataframe(reconciliation, use_container_width=True, hide_index=True)
        st.write(f"Bewusst ausgeschlossene Exportzeilen: **{summary.excluded_rows}**")
        st.write(f"Blockierende Einzelprüffälle: **{summary.blocking_findings}**")
        st.write(f"Nicht blockierende Hinweise: **{summary.info_findings}**")


def _render_sorted_open_tasks(*, operator_ui, user: UserContext, export_gate, global_export_blockers, findings) -> None:
    st.subheader("Offene Aufgaben")
    st.caption(
        "Bearbeite zuerst alle blockierenden Probleme. Die Tabellen sind nach Loknummer sortiert. "
        "Öffne einen Fall direkt unterhalb der jeweiligen Liste."
    )
    blocking_gate = sort_operator_table(operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings))
    warning_gate = sort_operator_table(operator_ui._friendly_gate_table(export_gate, only_status="WARNING", findings=findings))
    blockers = sort_operator_table(operator_ui._friendly_global_blockers(global_export_blockers))
    finding_table = sort_operator_table(operator_ui._friendly_findings(findings, include_info=True))
    blocking_findings = finding_table[finding_table["Auswirkung"].eq("Export gesperrt")].copy() if not finding_table.empty else finding_table
    hints = finding_table[~finding_table["Auswirkung"].eq("Export gesperrt")].copy() if not finding_table.empty else finding_table

    tab_blocked, tab_global, tab_hints, tab_rules = st.tabs(
        [
            f"⛔ Gesperrte Lok-Tage ({len(blocking_gate)})",
            f"⛔ Globale Sperren ({len(blockers)})",
            f"⚠️ Hinweise ({len(warning_gate) + len(hints)})",
            f"Technische Einzelprüffälle ({len(finding_table)})",
        ]
    )
    with tab_blocked:
        if blocking_gate.empty:
            st.success("Keine gesperrten Lok-Tage vorhanden.")
        else:
            st.dataframe(blocking_gate, use_container_width=True, hide_index=True)
            _render_direct_case_open(blocking_gate, key_suffix="blocked")
        if not blocking_findings.empty:
            with st.expander("Zugehörige blockierende Einzelprüffälle anzeigen", expanded=False):
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
                st.markdown("##### Lok-Tage mit Hinweis")
                st.dataframe(warning_gate, use_container_width=True, hide_index=True)
                _render_direct_case_open(warning_gate, key_suffix="warning")
            if not hints.empty:
                st.markdown("##### Weitere Hinweise aus dem Regelwerk")
                st.dataframe(hints, use_container_width=True, hide_index=True)
    with tab_rules:
        st.caption("Technische Detailansicht. Im normalen Betrieb zuerst die vorherigen Reiter verwenden.")
        if finding_table.empty:
            st.info("Keine Einzelprüffälle vorhanden.")
        else:
            st.dataframe(finding_table, use_container_width=True, hide_index=True)
            csv = finding_table.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Arbeitsliste als CSV herunterladen",
                data=csv,
                file_name="offene_aufgaben.csv",
                mime="text/csv",
                key="download_operator_tasks_csv_phase10a",
            )
    render_case_workspace(user=user, findings=findings)


def _without_legacy_override_info(original_info):
    def filtered_info(body: object, *args: Any, **kwargs: Any):
        text = str(body)
        if text.startswith("Lokale Korrekturen ändern weder RailCube noch die importierten Original-CSVs"):
            return None
        return original_info(body, *args, **kwargs)
    return filtered_info


@contextmanager
def operator_workflow_runtime(user: UserContext) -> Iterator[None]:
    """Activate compact dashboard, direct case navigation and admin-only pipeline tab."""
    import manual_override_ui_module as override_ui
    import operator_ui_module as operator_ui
    import pipeline_test_ui_module as pipeline_ui

    original_dashboard = operator_ui.render_operator_dashboard
    original_tasks = operator_ui.render_open_tasks
    original_cockpit = override_ui.render_manual_override_cockpit
    original_pipeline = pipeline_ui.render_pipeline_test_controller
    original_tabs = st.tabs

    def compact_dashboard(**kwargs: Any) -> None:
        _render_compact_dashboard(operator_ui=operator_ui, **kwargs)

    def sorted_tasks(**kwargs: Any) -> None:
        _render_sorted_open_tasks(operator_ui=operator_ui, user=user, **kwargs)

    def cockpit(*args: Any, **kwargs: Any):
        original_info = st.info
        st.info = _without_legacy_override_info(original_info)
        try:
            result = original_cockpit(*args, **kwargs)
        finally:
            st.info = original_info
        render_case_workspace(
            user=user,
            findings=kwargs.get("findings"),
            timeline=kwargs.get("timeline"),
            compact=True,
        )
        return result

    def pipeline(*args: Any, **kwargs: Any):
        if not user.is_admin:
            return None
        return original_pipeline(*args, **kwargs)

    def scoped_tabs(labels, *args: Any, **kwargs: Any):
        values = list(labels)
        if not user.is_admin and _PIPELINE_TAB_LABEL in values:
            index = values.index(_PIPELINE_TAB_LABEL)
            visible = values[:index] + values[index + 1 :]
            containers = list(original_tabs(visible, *args, **kwargs))
            containers.insert(index, nullcontext())
            return containers
        return original_tabs(values, *args, **kwargs)

    operator_ui.render_operator_dashboard = compact_dashboard
    operator_ui.render_open_tasks = sorted_tasks
    override_ui.render_manual_override_cockpit = cockpit
    pipeline_ui.render_pipeline_test_controller = pipeline
    st.tabs = scoped_tabs
    try:
        yield
    finally:
        operator_ui.render_operator_dashboard = original_dashboard
        operator_ui.render_open_tasks = original_tasks
        override_ui.render_manual_override_cockpit = original_cockpit
        pipeline_ui.render_pipeline_test_controller = original_pipeline
        st.tabs = original_tabs
