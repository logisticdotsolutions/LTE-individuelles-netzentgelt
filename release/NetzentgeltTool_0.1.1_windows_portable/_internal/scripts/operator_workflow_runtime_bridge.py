"""Runtime overlay for a clearer operator workflow without rewriting the legacy app.

The large Streamlit application stays stable. This bridge temporarily replaces a
few render functions while app/app.py is executed by the secure wrapper.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Any, Callable, Iterator

import pandas as pd
import streamlit as st

from case_timeline_context_module import load_case_timeline_context
from local_auth_module import UserContext
from operator_case_workspace_module import (
    SESSION_CASE_LOCO_KEY,
    render_case_workspace,
    sort_operator_table,
)


PHASE11A_WORKFLOW_RUNTIME_MARKER = "NETZENTGELT_OPERATOR_WORKFLOW_RUNTIME_PHASE11A_V1_20260611"
PHASE11Q_TASK_DEDUP_MARKER = "NETZENTGELT_OPERATOR_TASK_DEDUP_PHASE11Q_V1_20260618"
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


def _clean_display_value(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"none", "nan", "nat", "<na>"}:
        return ""
    return text


def _clean_display_table(table: pd.DataFrame) -> pd.DataFrame:
    if table is None or table.empty:
        return table
    result = table.copy()
    for column in result.columns:
        result[column] = result[column].map(_clean_display_value)
    return result


def _normalize_transport_number(value: object) -> str:
    text = _clean_display_value(value)
    if not text:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text.strip()


def _task_problem_key(row: pd.Series) -> str:
    for column in ["Problem", "Regel", "Warum?", "Naechster Schritt"]:
        value = _clean_display_value(row.get(column)).lower()
        if value:
            if "loknummer" in value or "r012" in value or "dummy" in value:
                return "loco_number"
            if "gap" in value or "unterbrech" in value:
                return "gap"
            if "überschneidung" in value or "ueberschneidung" in value or "r011" in value:
                return "overlap"
            return value[:80]
    return ""


def _is_detailed_task(row: pd.Series) -> bool:
    return any(
        _clean_display_value(row.get(column))
        for column in ["Regel", "Prioritaet", "Von", "Bis", "Auswirkung"]
    )


def _task_score(row: pd.Series) -> int:
    score = sum(1 for column in row.index if _clean_display_value(row.get(column)))
    if _clean_display_value(row.get("Regel")):
        score += 50
    if _clean_display_value(row.get("Prioritaet")):
        score += 20
    if _clean_display_value(row.get("Von")) or _clean_display_value(row.get("Bis")):
        score += 15
    if _clean_display_value(row.get("Auswirkung")):
        score += 10
    return score


def _deduplicate_task_table(table: pd.DataFrame) -> pd.DataFrame:
    """Remove UI duplicates caused by mixing day-gate rows with concrete findings.

    A Lok-Tag gate row and an R012 finding row can describe the same missing-loco
    problem. The concrete finding row contains rule, priority and time context and
    must win. This is display-only; no finding or audit record is deleted.
    """
    if table is None or table.empty:
        return pd.DataFrame()

    result = _clean_display_table(table).copy()
    if result.empty:
        return result

    result["_transport_norm"] = result.get("Transportnummer", pd.Series("", index=result.index)).map(_normalize_transport_number)
    result["_problem_norm"] = result.apply(_task_problem_key, axis=1)
    result["_is_detailed"] = result.apply(_is_detailed_task, axis=1)
    result["_score"] = result.apply(_task_score, axis=1)

    detailed_pairs = {
        (row["_transport_norm"], row["_problem_norm"])
        for _, row in result.iterrows()
        if row["_is_detailed"] and row["_transport_norm"] and row["_problem_norm"]
    }
    drop_aggregate_mask = result.apply(
        lambda row: (
            not bool(row["_is_detailed"])
            and bool(row["_transport_norm"])
            and bool(row["_problem_norm"])
            and (row["_transport_norm"], row["_problem_norm"]) in detailed_pairs
        ),
        axis=1,
    )
    result = result[~drop_aggregate_mask].copy()

    # Exact duplicate protection, but keep separate concrete intervals for the same transport.
    for column in ["Regel", "Von", "Bis", "Nutzendes EVU", "Loknummer"]:
        if column not in result.columns:
            result[column] = ""
    result["_exact_key"] = result.apply(
        lambda row: "|".join(
            [
                row["_transport_norm"],
                row["_problem_norm"],
                _clean_display_value(row.get("Regel")),
                _clean_display_value(row.get("Von")),
                _clean_display_value(row.get("Bis")),
                _clean_display_value(row.get("Nutzendes EVU")),
                _clean_display_value(row.get("Loknummer")),
            ]
        ),
        axis=1,
    )
    result = result.sort_values("_score", ascending=False).drop_duplicates("_exact_key", keep="first")
    helper_columns = [column for column in result.columns if column.startswith("_")]
    result = result.drop(columns=helper_columns, errors="ignore")
    return sort_operator_table(result.reset_index(drop=True))


def _loco_number_issue_mask(table: pd.DataFrame) -> pd.Series:
    if table is None or table.empty:
        return pd.Series(False, index=getattr(table, "index", []), dtype=bool)
    mask = pd.Series(False, index=table.index, dtype=bool)
    for column in ["Problem", "Warum?", "Naechster Schritt", "Regel", "Status", "Loknummer"]:
        if column not in table.columns:
            continue
        text = table[column].fillna("").astype(str).str.strip().str.lower()
        mask = mask | text.str.contains("dummy", regex=False)
        mask = mask | text.str.contains("loknummer fehlt", regex=False)
        mask = mask | text.str.contains("r012", regex=False)
        mask = mask | text.eq("00000000000-0")
        if column == "Loknummer":
            mask = mask | text.eq("")
    return mask


def _force_blocking(table: pd.DataFrame) -> pd.DataFrame:
    if table is None or table.empty:
        return table
    result = _clean_display_table(table)
    if "Status" in result.columns:
        result["Status"] = "⛔ Gesperrt"
    if "Auswirkung" in result.columns:
        result["Auswirkung"] = "Export gesperrt"
    if "Naechster Schritt" in result.columns:
        result["Naechster Schritt"] = "Fall prüfen und jede betroffene Minute fachlich schließen."
    return result


def load_case_timeline_once(
    cache: dict[str, pd.DataFrame],
    loader: Callable[[], pd.DataFrame] = load_case_timeline_context,
) -> pd.DataFrame:
    """Load the 30-day case context at most once during one Streamlit UI run."""
    if "timeline" not in cache:
        cache["timeline"] = loader()
    return cache["timeline"]


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
    if summary.export_is_blocked or summary.warning_days > 0:
        st.error("⛔ Export derzeit gesperrt. Bearbeite alle offenen Lokbewegungs- und Loknummernfehler.")
    else:
        st.success("✅ Export möglich. Die automatische Prüfung hat keine offenen Sperren erkannt.")

    col_1, col_2, col_3, col_4 = st.columns(4)
    col_1.metric("Freigegebene Lok-Tage", summary.ready_days)
    col_2.metric("Offene Lok-Tage", summary.blocked_days + summary.warning_days)
    col_3.metric("Einzelne Fehler", summary.blocking_findings + summary.info_findings)
    col_4.metric("Globale Sperren", summary.global_blockers)

    st.markdown("#### Empfohlener Ablauf")
    st.markdown(
        "  \n".join(
            [
                "✅ **1. Daten aktualisieren:** aktuellen Datenstand laden und prüfen",
                "🔎 **2. Offene Aufgaben:** alle Sperren direkt öffnen und bewerten",
                "🛠️ **3. Fall bearbeiten:** Korrektur, Klassifikation oder Ausnahme dokumentieren",
                "📦 **4. Export erstellen:** erst nach vollständiger Klärung herunterladen",
            ]
        )
    )

    with st.expander("Audit-Details anzeigen", expanded=False):
        st.caption("Technische Details bleiben auditierbar. Für die tägliche Bearbeitung zählen nur die offenen Sperren.")
        blocked_days = sort_operator_table(
            operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings)
        )
        warning_days = sort_operator_table(
            operator_ui._friendly_gate_table(export_gate, only_status="WARNING", findings=findings)
        )
        combined = pd.concat([blocked_days, warning_days], ignore_index=True) if not warning_days.empty else blocked_days
        if not combined.empty:
            st.markdown("##### Offene Lok-Tage")
            st.dataframe(_deduplicate_task_table(_force_blocking(combined)), use_container_width=True, hide_index=True)
        global_table = operator_ui._friendly_global_blockers(global_export_blockers)
        if not global_table.empty:
            st.markdown("##### Globale Sperren")
            st.dataframe(_clean_display_table(global_table), use_container_width=True, hide_index=True)
        if operational_kpis is not None and not operational_kpis.empty:
            st.markdown("##### Operative Kennzahlen")
            st.dataframe(operational_kpis, use_container_width=True, hide_index=True)
        if reconciliation is not None and not reconciliation.empty:
            st.markdown("##### Vollständigkeitsprüfung")
            st.dataframe(reconciliation, use_container_width=True, hide_index=True)
        st.write(f"Bewusst ausgeschlossene Exportzeilen: **{summary.excluded_rows}**")
        st.write(f"Offene Einzelprüffälle: **{summary.blocking_findings + summary.info_findings}**")


def _render_sorted_open_tasks(
    *,
    operator_ui,
    user: UserContext,
    case_timeline_loader: Callable[[], pd.DataFrame],
    export_gate,
    global_export_blockers,
    findings,
) -> None:
    st.subheader("Offene Aufgaben")
    st.caption(
        "Es gibt in dieser Ansicht keine Hinweise und keine technischen Nebenlisten mehr. "
        "Alles ist eine Sperre, solange nicht jede betroffene Minute fachlich geklärt ist."
    )
    blocking_gate = sort_operator_table(operator_ui._friendly_gate_table(export_gate, only_status="BLOCKED", findings=findings))
    warning_gate = sort_operator_table(operator_ui._friendly_gate_table(export_gate, only_status="WARNING", findings=findings))
    gate_table = pd.concat([blocking_gate, warning_gate], ignore_index=True) if not warning_gate.empty else blocking_gate
    gate_table = _force_blocking(sort_operator_table(gate_table))

    blocker_table = _force_blocking(sort_operator_table(operator_ui._friendly_global_blockers(global_export_blockers)))
    finding_table = _force_blocking(sort_operator_table(operator_ui._friendly_findings(findings, include_info=True)))

    movement_parts = []
    loco_parts = []
    for table in [gate_table, blocker_table, finding_table]:
        if table is None or table.empty:
            continue
        mask = _loco_number_issue_mask(table)
        if mask.any():
            loco_parts.append(table[mask].copy())
        if (~mask).any():
            movement_parts.append(table[~mask].copy())

    movement_table = pd.concat(movement_parts, ignore_index=True) if movement_parts else pd.DataFrame()
    loco_table = pd.concat(loco_parts, ignore_index=True) if loco_parts else pd.DataFrame()
    movement_table = _deduplicate_task_table(movement_table)
    loco_table = _deduplicate_task_table(loco_table)

    tab_movement, tab_loco = st.tabs([
        f"⛔ Fehler in Lokbewegung ({len(movement_table)})",
        f"⛔ Fehlende Loknummer / Dummylok ({len(loco_table)})",
    ])

    with tab_movement:
        st.markdown("##### Fehler in Lokbewegung")
        st.caption("GAPs, Überschneidungen, fehlende EVU-Zuordnung oder andere Bewegungsfehler. Export bleibt gesperrt, bis jede Minute geschlossen ist.")
        if movement_table.empty:
            st.success("Keine offenen Fehler in Lokbewegungen vorhanden.")
        else:
            st.dataframe(movement_table, use_container_width=True, hide_index=True)
            _render_direct_case_open(movement_table, key_suffix="movement")

    with tab_loco:
        st.markdown("##### Fehlende Loknummer / Dummylok")
        st.caption("Fälle ohne echte Loknummer oder mit Dummy-/Planungslok. Diese Fälle müssen vor Export fachlich korrigiert werden.")
        if loco_table.empty:
            st.success("Keine offenen Loknummer-/Dummy-Fälle vorhanden.")
        else:
            st.dataframe(loco_table, use_container_width=True, hide_index=True)
            _render_direct_case_open(loco_table, key_suffix="loco")

    selected_loco = str(st.session_state.get(SESSION_CASE_LOCO_KEY, "")).strip()
    if selected_loco:
        st.info(f"Fall Lok {selected_loco} ist geöffnet. Wechsle für Prüfung und Korrektur in den Reiter '3. Fall bearbeiten'.")


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
    case_timeline_cache: dict[str, pd.DataFrame] = {}

    def case_timeline() -> pd.DataFrame:
        return load_case_timeline_once(case_timeline_cache)

    def compact_dashboard(**kwargs: Any) -> None:
        _render_compact_dashboard(operator_ui=operator_ui, **kwargs)

    def sorted_tasks(**kwargs: Any) -> None:
        _render_sorted_open_tasks(
            operator_ui=operator_ui,
            user=user,
            case_timeline_loader=case_timeline,
            **kwargs,
        )

    def cockpit(*args: Any, **kwargs: Any):
        original_info = st.info
        st.info = _without_legacy_override_info(original_info)
        try:
            result = original_cockpit(*args, **kwargs)
        except Exception as error:
            st.error(f"Korrektur-Cockpit konnte nicht geladen werden: {error}")
            return None
        finally:
            st.info = original_info

        timeline = case_timeline() if st.session_state.get(SESSION_CASE_LOCO_KEY) else pd.DataFrame()
        try:
            render_case_workspace(
                user=user,
                findings=kwargs.get("findings"),
                timeline=timeline,
                compact=True,
            )
        except Exception as error:
            st.error(f"Fall-Arbeitsbereich konnte nicht geladen werden: {error}")
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
