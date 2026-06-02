from pathlib import Path
import subprocess
import sys
import pandas as pd
import streamlit as st

def normalize_bool(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in ["true", "1", "yes", "y", "ja"]

BASE_DIR = Path(__file__).resolve().parents[1]
EXPORT_DIR = BASE_DIR / "data" / "03_exports"
RAW_DIR = BASE_DIR / "data" / "00_raw"
SCRIPT_RUN_ALL = BASE_DIR / "scripts" / "run_all.py"
DETAIL_LOOKBACK_DAYS = 30

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

def read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, sep=None, engine="python", encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path, sep=";", encoding="utf-8-sig")
        except Exception as e:
            st.error(f"Datei konnte nicht gelesen werden: {path.name} - {e}")
            return pd.DataFrame()

def get_col(df: pd.DataFrame, candidates):
    lower_map = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    return None

def file_status_box():
    st.sidebar.header("Datenstatus")

    expected_raw = [
        "LocomotiveMovement.csv",
        "LocomotiveUsage.csv",
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

timeline_path = EXPORT_DIR / "core_loco_timeline.csv"
findings_path = EXPORT_DIR / "dq_findings.csv"
zuordnungen_path = EXPORT_DIR / "export_zuordnungen.csv"
nutzungsmeldung_path = EXPORT_DIR / "export_nutzungsmeldung.csv"
run_path = EXPORT_DIR / "raw_import_run.csv"

timeline = read_csv_safe(timeline_path)
findings = read_csv_safe(findings_path)
zuordnungen = read_csv_safe(zuordnungen_path)
nutzungsmeldung = read_csv_safe(nutzungsmeldung_path)
runs = read_csv_safe(run_path)

tab_overview, tab_timeline, tab_findings, tab_exports, tab_run = st.tabs([
    "Überblick",
    "Lok-Zeitachse",
    "Fehlerqueue",
    "Exporte",
    "Pipeline"
])

with tab_overview:
    st.subheader("Überblick")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Timeline-Zeilen", len(timeline))

    with c2:
        st.metric("Findings", len(findings))

    severity_col = get_col(findings, ["severity", "Severity"])
    if severity_col:
        errors = len(findings[findings[severity_col].astype(str).str.upper() == "ERROR"])
        warnings = len(findings[findings[severity_col].astype(str).str.upper() == "WARNING"])
    else:
        errors = 0
        warnings = 0

    with c3:
        st.metric("Errors", errors)

    with c4:
        st.metric("Warnings", warnings)

    st.divider()

    st.subheader("Letzte Importläufe")
    if runs.empty:
        st.info("Noch keine Importlauf-Datei gefunden.")
    else:
        st.dataframe(runs, use_container_width=True, hide_index=True)

    st.subheader("Erste Timeline-Vorschau")
    if timeline.empty:
        st.warning("Keine core_loco_timeline.csv gefunden.")
    else:
        st.dataframe(timeline.head(100), use_container_width=True, hide_index=True)

with tab_timeline:
    st.subheader("Lok-Zeitachse prüfen")

    if timeline.empty:
        st.warning("Keine Timeline vorhanden. Bitte zuerst Pipeline ausführen.")
    else:
        loco_col = get_col(timeline, [
            "loco_no",
            "LocomotiveNo",
            "locomotive_no",
            "locomotiveno",
            "loco",
            "tfze_or_tens"
        ])

        if loco_col:
            locos = sorted(timeline[loco_col].dropna().astype(str).unique().tolist())
            selected_loco = st.selectbox("Lok auswählen", ["Alle"] + locos)

            filtered = timeline.copy()
            if selected_loco != "Alle":
                filtered = filtered[filtered[loco_col].astype(str) == selected_loco]

            st.write(f"Treffer: **{len(filtered)}**")
            st.dataframe(filtered, use_container_width=True, hide_index=True)

            csv = filtered.to_csv(index=False, sep=";").encode("utf-8-sig")
            st.download_button(
                "Gefilterte Timeline herunterladen",
                data=csv,
                file_name="timeline_gefiltert.csv",
                mime="text/csv"
            )
        else:
            st.warning("Keine Lok-Spalte erkannt. Verfügbare Spalten:")
            st.write(list(timeline.columns))
            st.dataframe(timeline, use_container_width=True, hide_index=True)

with tab_findings:
    st.subheader("Fehler- und Prüfqueue")

    if findings.empty:
        st.success("Keine Findings gefunden oder Datei dq_findings.csv fehlt.")
    else:
        filtered_findings = findings.copy()

        severity_col = get_col(findings, ["severity"])
        rule_col = get_col(findings, ["rule_id", "rule"])
        loco_col = get_col(findings, ["loco_no", "LocomotiveNo", "locomotive_no"])

        f1, f2, f3 = st.columns(3)

        with f1:
            if severity_col:
                severities = sorted(findings[severity_col].dropna().astype(str).unique().tolist())
                selected_sev = st.multiselect("Severity", severities, default=severities)
                filtered_findings = filtered_findings[filtered_findings[severity_col].astype(str).isin(selected_sev)]

        with f2:
            if rule_col:
                rules = sorted(findings[rule_col].dropna().astype(str).unique().tolist())
                selected_rules = st.multiselect("Regel", rules, default=rules)
                filtered_findings = filtered_findings[filtered_findings[rule_col].astype(str).isin(selected_rules)]

        with f3:
            if loco_col:
                locos = sorted(findings[loco_col].dropna().astype(str).unique().tolist())
                selected_loco_find = st.selectbox("Lok", ["Alle"] + locos)
                if selected_loco_find != "Alle":
                    filtered_findings = filtered_findings[filtered_findings[loco_col].astype(str) == selected_loco_find]

        st.write(f"Treffer gesamt: **{len(filtered_findings)}**")

        max_rows = st.number_input(
            "Maximale Anzeigezeilen",
            min_value=100,
            max_value=10000,
            value=1000,
            step=100
        )

        display_findings = filtered_findings.head(int(max_rows))

        st.info(
            f"Angezeigt werden {len(display_findings)} von "
            f"{len(filtered_findings)} Treffern. "
            "Die vollständige Datei bleibt im Exportordner erhalten."
        )

        st.dataframe(display_findings, use_container_width=True, hide_index=True)

        csv = display_findings.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            "Angezeigte Fehlerliste herunterladen",
            data=csv,
            file_name="dq_findings_gefiltert_preview.csv",
            mime="text/csv"
        )

with tab_exports:
    st.subheader("Exportdateien")

    export_files = sorted(EXPORT_DIR.glob("*.*"))

    if not export_files:
        st.warning("Keine Exportdateien gefunden.")
    else:
        for file in export_files:
            size_kb = file.stat().st_size / 1024
            col1, col2 = st.columns([4, 1])

            with col1:
                st.write(f"**{file.name}**  \n{size_kb:.1f} KB")

            with col2:
                with open(file, "rb") as f:
                    st.download_button(
                        label="Download",
                        data=f,
                        file_name=file.name,
                        key=f"download_{file.name}"
                    )

    st.divider()

    st.subheader("Zuordnungen Vorschau")
    if not zuordnungen.empty:
        st.dataframe(zuordnungen.head(100), use_container_width=True, hide_index=True)
    else:
        st.info("Keine export_zuordnungen.csv vorhanden.")

    st.subheader("Nutzungsmeldung Vorschau")
    if not nutzungsmeldung.empty:
        st.dataframe(nutzungsmeldung.head(100), use_container_width=True, hide_index=True)
    else:
        st.info("Keine export_nutzungsmeldung.csv vorhanden.")

with tab_run:
    st.subheader("Pipeline ausführen")

    st.write("Hier kannst du den bestehenden Datenlauf neu starten.")
    st.code("python scripts/run_all.py", language="powershell")

    if st.button("Pipeline jetzt starten", type="primary"):
        if not SCRIPT_RUN_ALL.exists():
            st.error(f"Skript nicht gefunden: {SCRIPT_RUN_ALL}")
        else:
            with st.spinner("Pipeline läuft..."):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT_RUN_ALL)],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True
                )

            if result.returncode == 0:
                st.success("Pipeline erfolgreich abgeschlossen. Seite bitte neu laden.")
                st.text_area("Output", result.stdout, height=250)
            else:
                st.error("Pipeline ist fehlgeschlagen.")
                st.text_area("Fehler", result.stderr, height=250)
                st.text_area("Output", result.stdout, height=250)

    st.divider()

    st.subheader("Nächster fachlicher Schritt")
    st.write(
        "Bitte 3 bis 5 konkrete Loks auswählen und anhand der Timeline prüfen, "
        "ob Zeitraum, Halter, vEns und Fehlerstatus fachlich plausibel sind."
    )

st.header("🔎 Lok-Detailprüfung")

core_path = EXPORT_DIR / "core_loco_timeline.csv"
dq_path = EXPORT_DIR / "dq_findings.csv"
route_detail_path = EXPORT_DIR / "stg_transport_details_enriched.csv"

core = read_csv_safe(core_path)
dq = read_csv_safe(dq_path)
route_details = read_csv_safe(route_detail_path)

if core.empty:
    st.warning("Keine core_loco_timeline.csv gefunden. Bitte zuerst die Pipeline ausführen.")
else:
    # Datumsfelder sauber konvertieren
    for col in [
        "period_start_utc",
        "period_end_utc",
        "sequence_ts",
        "gap_from_utc",
        "gap_to_utc",
    ]:
        if col in core.columns:
            core[col] = pd.to_datetime(core[col], errors="coerce")

    # Lokauswahl
    loco_values = (
        core["loco_no"]
        .dropna()
        .astype(str)
        .sort_values()
        .unique()
        .tolist()
    )

    selected_loco = st.selectbox(
        "Lok auswählen",
        loco_values,
        index=0 if loco_values else None
    )

    loco_df = core[core["loco_no"].astype(str) == str(selected_loco)].copy()

    # Lok-Detailprüfung: immer nur die letzten 30 Tage anzeigen
    if not loco_df.empty:
        detail_filter_ts = pd.Series(pd.NaT, index=loco_df.index)

        # Bei GAP-Zeilen ist gap_to_utc der beste Anker.
        if "gap_to_utc" in loco_df.columns:
            detail_filter_ts = detail_filter_ts.fillna(loco_df["gap_to_utc"])

        # Bei normalen Bewegungen ist period_end_utc primär relevant.
        if "period_end_utc" in loco_df.columns:
            detail_filter_ts = detail_filter_ts.fillna(loco_df["period_end_utc"])

        if "period_start_utc" in loco_df.columns:
            detail_filter_ts = detail_filter_ts.fillna(loco_df["period_start_utc"])

        if "sequence_ts" in loco_df.columns:
            detail_filter_ts = detail_filter_ts.fillna(loco_df["sequence_ts"])

        max_ts = detail_filter_ts.max()

        if pd.notna(max_ts):
            cutoff_ts = max_ts - pd.Timedelta(days=DETAIL_LOOKBACK_DAYS)

            loco_df = loco_df[
                detail_filter_ts >= cutoff_ts
            ].copy()

            st.caption(
                f"Anzeigezeitraum Lok-Detailprüfung: letzte {DETAIL_LOOKBACK_DAYS} Tage "
                f"bezogen auf den aktuellsten Datensatz dieser Lok "
                f"({cutoff_ts:%d.%m.%Y %H:%M} bis {max_ts:%d.%m.%Y %H:%M})."
            )
        else:
            st.caption("Für diese Lok konnte kein gültiger Anzeigezeitraum ermittelt werden.")

    if loco_df.empty:
        st.info("Für diese Lok wurden keine Bewegungen im Anzeigezeitraum gefunden.")

    else:
        loco_df = loco_df.sort_values(
            by=["period_start_utc", "period_end_utc", "transport_number"],
            ascending=True
        )

        # Fehlertexte aus dq_findings grob auf Lok + Zeitraum aggregieren
        if not dq.empty:
            for col in ["period_start_utc", "period_end_utc"]:
                if col in dq.columns:
                    dq[col] = pd.to_datetime(dq[col], errors="coerce")

            dq_loco = dq[dq["loco_no"].astype(str) == str(selected_loco)].copy()

            if not dq_loco.empty:
                dq_grouped = (
                    dq_loco
                    .groupby(["loco_no", "period_start_utc", "period_end_utc"], dropna=False)
                    .agg({
                        "severity": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
                        "rule_id": lambda x: ", ".join(sorted(set(x.dropna().astype(str)))),
                        "message": lambda x: " | ".join(x.dropna().astype(str))
                    })
                    .reset_index()
                    .rename(columns={
                        "severity": "dq_severity",
                        "rule_id": "dq_rule_ids",
                        "message": "dq_messages"
                    })
                )

                loco_df = loco_df.merge(
                    dq_grouped,
                    on=["loco_no", "period_start_utc", "period_end_utc"],
                    how="left"
                )
            else:
                loco_df["dq_severity"] = ""
                loco_df["dq_rule_ids"] = ""
                loco_df["dq_messages"] = ""
        else:
            loco_df["dq_severity"] = ""
            loco_df["dq_rule_ids"] = ""
            loco_df["dq_messages"] = ""

        # Anzeige-Spalten
        preferred_cols = [
            "display_sequence_no",
            "row_type",
            "report_scope",
            "de_event_label",
            "transport_number",
            "train_no",
            "period_start_utc",
            "period_end_utc",
            "sequence_ts",
            "sequence_ts_source",
            "gap_from_utc",
            "gap_to_utc",
            "gap_duration_text",
            "gap_message",
            "loco_no",
            "tfze_or_tens",
            "holder_name",
            "performing_ru",
            "user_vens",
            "halter_marktpartner_id",
            "country",
            "origin_name",
            "destination_name",
            "cal_start_country",
            "cal_end_country",
            "cal_entry_count_home",
            "cal_exit_count_home",
            "cal_route_type_home",
            "time_quality",
            "confidence",
            "needs_manual_review",
            "decision_reason",
            "dq_rule_ids",
            "dq_messages",
        ]

        display_cols = [c for c in preferred_cols if c in loco_df.columns]
        view_df = loco_df[display_cols].copy()

        st.subheader(f"Bewegungen für Lok {selected_loco}")

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Bewegungen", len(loco_df))

        if "needs_manual_review" in loco_df.columns:
            error_count = loco_df["needs_manual_review"].apply(normalize_bool).sum()
        else:
            error_count = 0

        c2.metric("Prüffälle", int(error_count))

        if "transport_number" in loco_df.columns:
            c3.metric("Transporte", loco_df["transport_number"].nunique())
        else:
            c3.metric("Transporte", "-")

        if "cal_route_type_home" in loco_df.columns:
            transit_count = (loco_df["cal_route_type_home"] == "Passiert (Transit)").sum()
            c4.metric("Transit", int(transit_count))
        else:
            c4.metric("Transit", "-")

        def highlight_problem_rows(row):
            is_problem = False

            if "needs_manual_review" in row.index:
                is_problem = normalize_bool(row["needs_manual_review"])

            if "dq_severity" in row.index and pd.notna(row["dq_severity"]):
                if "ERROR" in str(row["dq_severity"]).upper():
                    is_problem = True

            if is_problem:
                return ["background-color: #fde2e2; color: #111111"] * len(row)

            return [""] * len(row)

        st.dataframe(
            view_df.style.apply(highlight_problem_rows, axis=1),
            use_container_width=True,
            hide_index=True
        )

        st.divider()

        st.subheader("📌 Transport kontrollieren")

        transport_values = (
            loco_df["transport_number"]
            .dropna()
            .astype(str)
            .sort_values()
            .unique()
            .tolist()
            if "transport_number" in loco_df.columns else []
        )

        if not transport_values:
            st.info("Für diese Lok sind keine Transportnummern vorhanden.")
        else:
            selected_transport = st.selectbox(
                "Transportnummer auswählen",
                transport_values
            )

            movement_detail = loco_df[
                loco_df["transport_number"].astype(str) == str(selected_transport)
            ].copy()

            st.markdown("### Bewegung(en) dieser Lok zu diesem Transport")

            detail_cols = [c for c in display_cols if c in movement_detail.columns]
            st.dataframe(
                movement_detail[detail_cols].style.apply(highlight_problem_rows, axis=1),
                use_container_width=True,
                hide_index=True
            )

            st.markdown("### Grenz-/Segmentverlauf des Transports")

            if route_details.empty:
                st.info("Keine stg_transport_details_enriched.csv gefunden. Bitte Transport-Routenklassifikation in der Pipeline aktivieren.")
            elif "transport_number" not in route_details.columns:
                st.warning("Die Datei stg_transport_details_enriched.csv enthält keine Spalte transport_number.")
            else:
                seg_df = route_details[
                    route_details["transport_number"].astype(str) == str(selected_transport)
                ].copy()

                if seg_df.empty:
                    st.info("Keine TransportDetail-Segmente zu dieser Transportnummer gefunden.")
                else:
                    if "cal_seqnum" in seg_df.columns:
                        seg_df["cal_seqnum"] = pd.to_numeric(seg_df["cal_seqnum"], errors="coerce")
                        seg_df = seg_df.sort_values("cal_seqnum")

                    seg_cols_preferred = [
                        "cal_seqnum",
                        "origin_country_iso",
                        "destination_country_iso",
                        "cal_border_event_home",
                        "origin_name",
                        "destination_name",
                        "departure_time_utc",
                        "arrival_time_utc",
                        "source_table",
                        "source_row_id",
                    ]

                    seg_cols = [c for c in seg_cols_preferred if c in seg_df.columns]

                    def highlight_border_events(row):
                        event = str(row.get("cal_border_event_home", ""))

                        if event == "Einfahrt":
                            return ["background-color: #fff3cd; color: #111111"] * len(row)

                        if event == "Ausfahrt":
                            return ["background-color: #e2f0ff; color: #111111"] * len(row)

                        if event == "Unklar":
                            return ["background-color: #fde2e2; color: #111111"] * len(row)

                        return ["color: #111111"] * len(row)

                    st.dataframe(
                        seg_df[seg_cols].style.apply(highlight_border_events, axis=1),
                        use_container_width=True,
                        hide_index=True
                    )