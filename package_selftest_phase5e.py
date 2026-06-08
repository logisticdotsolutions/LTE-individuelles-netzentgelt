from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

APP_FIXTURE = r'''# NETZENTGELT_MANUAL_OVERRIDE_PHASE5A_V1_20260607
st.set_page_config(
    page_title="Netzentgelt MVP Tool",
    page_icon="🚆",
    layout="wide"
)

st.title("🚆 Netzentgelt MVP Tool")
st.markdown(
    "<small>Entwickelt von <b>Christoph Orgl</b> · LTE-group · MVP-Prototyp für Netzentgelt-Datenprüfung</small>",
    unsafe_allow_html=True
)

def file_status_box():
    st.sidebar.header("Datenstatus")

    expected_raw = [
        "LocomotiveMovement.csv",
        "TransportDetail.csv",
        "Locomotive.csv",
    ]

    for file in expected_raw:
        path = RAW_DIR / file
        if path.exists():
            size_mb = path.stat().st_size / 1024 / 1024
            st.sidebar.success(f"{file} ({size_mb:.1f} MB)")
        else:
            st.sidebar.warning(f"{file} fehlt")

    st.sidebar.divider()

    export_files = list(EXPORT_DIR.glob("*.csv"))
    st.sidebar.write(f"Exportdateien: **{len(export_files)}**")

file_status_box()

    severity_col = get_col(findings, ["severity", "Severity"])
    old_technical_counter_block = True
    # ==================================================
    # NETZENTGELT_DAU_UX_PHASE3_V1_20260607: selbsterklaerende Tagespruefung
    # ==================================================
    render_operator_dashboard()

    st.divider()

    # ==================================================
    # Übersicht der fehlenden bzw. technischen Loknummern
    # ==================================================
    old_overview_details = True

with tab_tasks:
    pass

with tab_override:
    pass

with tab_timeline:
    st.subheader("Lok im Detail prüfen")
    duplicate_quick_preview = True

with tab_findings:
    pass

with tab_exports:
    st.subheader("XLSX-Nutzungsmeldungen je Performing RU")
    if not DB_PATH.exists():
        pass
    else:
        today = datetime.now().date()
        first_allowed_day = today - timedelta(days=29)

        date_col_1, date_col_2 = st.columns(2)

        with date_col_1:
            export_date_from = st.date_input(
                "Von",
                value=first_allowed_day,
                min_value=first_allowed_day,
                max_value=today,
                key="nutzungsmeldung_export_date_from",
            )

        with date_col_2:
            export_date_to = st.date_input(
                "Bis",
                value=today,
                min_value=first_allowed_day,
                max_value=today,
                key="nutzungsmeldung_export_date_to",
            )

        if export_date_from > export_date_to:
            st.error("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")

        else:
            # ==================================================
            # NETZENTGELT_REST_EXPORT_PHASE4_V1_20260607
            pass
        label = "Rest-PerformingRU für Download auswählen"
        title = "Restzeilen je PerformingRU"
        metric = "PerformingRUs im Rest"
        total = "Restzeilen gesamt"

with tab_run:
    pass

with tab_timeline:
    st.header("🔎 Lok-Detailprüfung")

    core_path = EXPORT_DIR / "core_loco_timeline.csv"
    dq_path = EXPORT_DIR / "dq_findings.csv"
    route_detail_path = EXPORT_DIR / "stg_transport_details_enriched.csv"

    core_raw = read_csv_safe(core_path)
    core_gap_relevance_ready = (
        core_raw.empty
    )
    core = hide_non_relevant_gap_rows(core_raw)
    dq = read_csv_safe(dq_path)
    route_details = read_csv_safe(route_detail_path)
    loco_df = core.copy()

        # Lok-Detailprüfung: immer nur die letzten 30 Tage anzeigen
        if not loco_df.empty:
            detail_filter_ts = pd.Series(pd.NaT, index=loco_df.index)
            max_ts = detail_filter_ts.max()
            if pd.notna(max_ts):
                cutoff_ts = max_ts - pd.Timedelta(days=DETAIL_LOOKBACK_DAYS)
                loco_df = loco_df[detail_filter_ts >= cutoff_ts].copy()

        if loco_df.empty:
            pass
'''

OPERATOR_FIXTURE = r'''DAU_UX_MARKER = "NETZENTGELT_DAU_UX_PHASE3_V1_20260607"
text = "Quality-Gate-Tabellen"
text2 = "Quality Gate wurde berechnet"
text3 = "Nutze die Loknummer im Tab '3. Lok pruefen'"
text4 = "Oeffne jetzt den Tab '3. Lok pruefen'"
text5 = "Technische Details oeffnen"
text6 = "Technische Details pruefen"
text7 = "PerformingRU fachlich pruefen und ergaenzen."
export_step = "🔒 **4. Exporte erstellen:** derzeit gesperrt"
export_step = "✅ **4. Exporte erstellen:** moeglich, nach fachlicher Kontrolle"
export_step = "✅ **4. Exporte erstellen:** freigegeben"
'''

MANUAL_UI_FIXTURE = r'''PHASE5B_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607"
CLASSIFICATION_OPTIONS = {
    "MISSING_MOVEMENT": "Fehlende Bewegung vermutet",
}
SUGGESTION_TYPE_LABELS = {
    "A": "PerformingRU aus beiden Nachbarbewegungen",
    "B": "PerformingRU aus angrenzenden Bewegungen",
    "C": "PerformingRU fuer GAP aus beiden Nachbarbewegungen",
    "D": "PerformingRU-Konflikt prüfen",
    "E": "PerformingRU manuell prüfen",
}
TAB_LABELS = ["Aktive Overrides", "Audit und Hinweise"]

def _render_active_overrides():
    display = active.copy()
    display["override_type"] = display["override_type"].map(OVERRIDE_TYPE_LABELS).fillna(display["override_type"])
    st.dataframe(display, use_container_width=True, hide_index=True)

def _suggestion_display_table(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    result = data.copy()
    result["confidence"] = result["confidence"].map(CONFIDENCE_LABELS).fillna(result["confidence"])
    result["suggestion_type"] = result["suggestion_type"].map(SUGGESTION_TYPE_LABELS).fillna(result["suggestion_type"])
    result["override_type"] = result["override_type"].map(OVERRIDE_TYPE_LABELS).fillna(result["override_type"])
    return result.rename(
        columns={
            "suggestion_id": "Vorschlag-ID",
            "suggestion_type": "Vorschlag",
            "override_type": "Bearbeitung",
            "classification_code": "Klassifikation",
            "confidence": "Sicherheit",
            "suggested_value": "Vorgeschlagener Wert",
            "transport_number": "Transportnummer",
            "loco_no": "Loknummer",
            "period_start_utc": "Von",
            "period_end_utc": "Bis",
            "reason": "Begründung",
            "evidence": "Nachweis",
        }
    )


def _save_selected_suggestions(
    *,
    suggestions,
):
    pass

def _render_suggestions(
    *,
    db_path: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    st.caption(
        "Vorschläge reduzieren Suchaufwand, ersetzen aber keine fachliche Freigabe. "
        "Jeder Vorschlag muss bewusst in die Bearbeitungsmaske übernommen werden."
    )
    st.write(f"Treffer: **{len(filtered)}**")

    csv_data = _suggestion_display_table(filtered).to_csv(index=False, sep=";").encode("utf-8-sig")
    selectable = filtered[
        filtered["suggested_value"].fillna("").astype(str).str.strip().ne("")
        | filtered["classification_code"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if selectable.empty:
        st.dataframe(_suggestion_display_table(filtered), use_container_width=True, hide_index=True)
        return
    st.caption(
        "Setze links ein Checkmark bei allen Vorschlägen, die du fachlich geprüft hast. "
        "Erst der Speichern-Button erzeugt lokale Overrides. RailCube wird dadurch nicht geändert."
    )
    st.success("1 Override(s) wurden gespeichert.")
    msg = "Override wurde deaktiviert"
    label = "Override deaktivieren"
    button = "Ausgewählten Override deaktivieren"
    info = "Overrides sind eine lokale, auditierbare Korrekturschicht dieses Tools. Bei einem neuen Import bleiben aktive Overrides bestehen und den lokalen Override bitte deaktivieren."
    suggestion = "Systemvorschlag"

def _render_new_override(
    *,
    db_path: Path,
    run_all_script: Path,
    findings: pd.DataFrame,
    timeline: pd.DataFrame,
) -> None:
    pass
'''

BATCH_FIXTURE = r'''PHASE5D_BATCH_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_BATCH_V1_20260608"

def _clean(value):
    return str(value or "").strip()

def _validate_suggestion(suggestion):
    suggestion_id = _clean(suggestion.get("suggestion_id"))
    override_type = _clean(suggestion.get("override_type")).upper()
    suggested_value = _clean(suggestion.get("suggested_value"))
    classification_code = _clean(suggestion.get("classification_code"))
    transport_number = _clean(suggestion.get("transport_number"))

    if not suggestion_id:
        return "Vorschlag-ID fehlt."
    if not override_type:
        return "Override-Typ fehlt."
    return None

def create_overrides_from_selected_suggestions():
    duplicate_keys = _active_duplicate_keys(base)
    created: list[BatchCreate] = []
    return created
'''

GITIGNORE_FIXTURE = r'''*.duckdb
.vscode/
.idea/
'''

def write_crlf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

def run(cmd, cwd, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = subprocess.run(cmd, cwd=str(cwd), env=merged, capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(f"Command failed: {cmd}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    return result

def selftest_installer() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copy2(HERE / "apply_netzentgelt_phase5e.py", root / "apply_netzentgelt_phase5e.py")
        write_crlf(root / "app/app.py", APP_FIXTURE)
        write_crlf(root / "scripts/operator_ui_module.py", OPERATOR_FIXTURE)
        write_crlf(root / "scripts/manual_override_ui_module.py", MANUAL_UI_FIXTURE)
        write_crlf(root / "scripts/manual_override_batch_module.py", BATCH_FIXTURE)
        write_crlf(root / ".gitignore", GITIGNORE_FIXTURE)
        originals = {p: (root / p).read_bytes() for p in [
            "app/app.py", "scripts/operator_ui_module.py", "scripts/manual_override_ui_module.py",
            "scripts/manual_override_batch_module.py", ".gitignore"
        ]}
        env = {"PHASE5E_ALLOW_FIXTURE": "1", "PHASE5E_SKIP_COMPILE": "1"}
        run([sys.executable, "apply_netzentgelt_phase5e.py", "dry-run"], root, env)
        for rel, raw in originals.items():
            assert (root / rel).read_bytes() == raw, f"Dry-run changed {rel}"
        run([sys.executable, "apply_netzentgelt_phase5e.py", "apply"], root, env)
        run([sys.executable, "apply_netzentgelt_phase5e.py", "verify"], root, env)
        for rel in originals:
            raw = (root / rel).read_bytes()
            assert b"\r\n" in raw, f"CRLF lost in {rel}"
            assert b"NETZENTGELT_CONTROLLER_UX_PHASE5E_V1_20260608" in raw
        app = (root / "app/app.py").read_text(encoding="utf-8")
        assert "Bahnstrom Deutschland - Tagesprüfung" in app
        assert "duplicate_quick_preview" not in app
        assert "value=operational_day_from" in app and "value=operational_day_to" in app
        manual = (root / "scripts/manual_override_ui_module.py").read_text(encoding="utf-8")
        assert "Die Auswahlspalte bleibt immer sichtbar" in manual
        assert 'bulk_table.insert(1, "Übernehmen", False)' in manual
        assert '"Sammelübernahme"' in manual
        assert "SAME_RU_CONTINUITY" in manual
        batch = (root / "scripts/manual_override_batch_module.py").read_text(encoding="utf-8")
        assert "unterschiedliche Klassifikationen" in batch
        assert "niedriger Sicherheit" in batch
        run([sys.executable, "apply_netzentgelt_phase5e.py", "dry-run"], root, env)
        run([sys.executable, "apply_netzentgelt_phase5e.py", "apply"], root, env)
        run([sys.executable, "apply_netzentgelt_phase5e.py", "rollback"], root, env)
        for rel, raw in originals.items():
            assert (root / rel).read_bytes() == raw, f"Rollback mismatch {rel}"

def selftest_cleanup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        shutil.copy2(HERE / "cleanup_repository_phase5e.py", root / "cleanup_repository_phase5e.py")
        (root / "payload").mkdir()
        (root / "payload/old.py").write_text("old", encoding="utf-8")
        (root / "README_PHASE5D.md").write_text("old", encoding="utf-8")
        (root / "keep.py").write_text("keep", encoding="utf-8")
        run(["git", "init"], root)
        run(["git", "config", "user.email", "selftest@example.invalid"], root)
        run(["git", "config", "user.name", "Selftest"], root)
        run(["git", "add", "."], root)
        run(["git", "commit", "-m", "fixture"], root)
        run([sys.executable, "cleanup_repository_phase5e.py", "dry-run"], root)
        assert (root / "payload/old.py").exists()
        run([sys.executable, "cleanup_repository_phase5e.py", "apply"], root)
        assert not (root / "payload/old.py").exists()
        assert not (root / "README_PHASE5D.md").exists()
        assert (root / "keep.py").exists()
        run([sys.executable, "cleanup_repository_phase5e.py", "rollback"], root)
        assert (root / "payload/old.py").exists()
        assert (root / "README_PHASE5D.md").exists()

if __name__ == "__main__":
    selftest_installer()
    selftest_cleanup()
    print("PACKAGE SELFTEST PHASE 5E: OK")
