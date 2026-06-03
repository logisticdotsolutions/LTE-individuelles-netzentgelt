from pathlib import Path
from datetime import datetime
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
# ------------------------------------------------------
# Skripte und Datenbankpfade
# ------------------------------------------------------

# Lädt die aktuellen Rohdaten aus Azure Blob Storage.
SCRIPT_DOWNLOAD_BLOB = BASE_DIR / "scripts" / "download_blob_data.py"

# Baut die DuckDB und alle CSV-Exporte vollständig neu auf.
SCRIPT_RUN_ALL = BASE_DIR / "scripts" / "run_all.py"

# Anzeigezeitraum in der Lok-Detailprüfung.
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

def get_last_raw_import_datetime():
    """
    Ermittelt den Zeitpunkt des letzten erfolgreichen Rohdatenimports.

    Die Azure-Downloadroutine ersetzt die lokalen Rohdaten-Dateien.
    Der neueste Änderungszeitpunkt der drei erwarteten CSV-Dateien
    entspricht daher dem letzten Importzeitpunkt.

    Rückgabe:
    - datetime: Zeitpunkt des letzten Imports
    - None:      Noch keine Rohdaten-Datei vorhanden
    """
    expected_raw_files = [
        RAW_DIR / "LocomotiveMovement.csv",
        RAW_DIR / "TransportDetail.csv",
        RAW_DIR / "Locomotive.csv",
    ]

    existing_files = [
        file_path
        for file_path in expected_raw_files
        if file_path.exists()
    ]

    if not existing_files:
        return None

    newest_timestamp = max(
        file_path.stat().st_mtime
        for file_path in existing_files
    )

    return datetime.fromtimestamp(newest_timestamp)


def run_python_script(script_path: Path):
    """
    Führt ein Python-Skript mit exakt derselben Python-Umgebung aus,
    mit der auch Streamlit gestartet wurde.

    Dadurch wird immer die lokale .venv verwendet und nicht versehentlich
    ein global installiertes Python ohne benötigte Pakete.

    Rückgabe:
    subprocess.CompletedProcess mit:
    - returncode = 0: Skript erfolgreich
    - returncode != 0: Skript fehlgeschlagen
    - stdout: normale Terminal-Ausgabe
    - stderr: Fehlermeldungen
    """
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        cwd=str(BASE_DIR),
        capture_output=True,
        text=True,
    )


def has_value(series: pd.Series) -> pd.Series:
    """
    Prüft zeilenweise, ob ein Feld tatsächlich befüllt ist.

    Als leer gelten:
    - NaN / NULL
    - leerer String
    - ausschließlich Leerzeichen
    - Textwert 'nan'
    """
    cleaned = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return (
        (cleaned != "")
        & (cleaned.str.lower() != "nan")
    )

def build_de_relevance_mask(source_df: pd.DataFrame):
    """
    Ermittelt zeilenweise, ob ein Datensatz für Deutschland relevant ist.

    Primär wird das Feld Country ausgewertet. Zusätzlich werden vorhandene
    Origin-/Destination-Länderfelder als Fallback berücksichtigt.

    Dadurch werden:
    - reine Auslandsabschnitte ausgeschlossen,
    - Einfahrten nach DE berücksichtigt,
    - Ausfahrten aus DE berücksichtigt,
    - Inland-Abschnitte in DE berücksichtigt.

    Rückgabe:
    - mask: boolesche Series mit DE-Relevanz je Zeile
    - detected_columns: tatsächlich verwendete Länderfelder
    """
    de_values = {
        "DE",
        "DEU",
        "GERMANY",
        "DEUTSCHLAND",
    }

    country_candidates = [
        "Country",
        "OriginCountryISO",
        "OriginCountry",
        "DestinationCountryISO",
        "DestinationCountry",
        "TransportOriginCountry",
        "TransportDestinationCountry",
    ]

    de_mask = pd.Series(
        False,
        index=source_df.index,
        dtype=bool,
    )

    detected_columns = []

    for candidate in country_candidates:
        column = get_col(
            source_df,
            [candidate],
        )

        if not column or column in detected_columns:
            continue

        normalized = (
            source_df[column]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        de_mask = de_mask | normalized.isin(de_values)
        detected_columns.append(column)

    return de_mask, detected_columns

def parse_actual_departure(series: pd.Series) -> pd.Series:
    """
    Konvertiert ActualDeparture aus dem DataLake-Format in einen Zeitstempel.

    Erwartetes Quellformat:
    2026-05-06T22:00:00.0000000

    Bedeutung:
    - %Y = Jahr
    - %m = Monat
    - %d = Tag
    - T  = festes Trennzeichen zwischen Datum und Uhrzeit
    - %H = Stunde
    - %M = Minute
    - %S = Sekunde
    - %f = Nachkommastellen der Sekunde

    utc=True:
    Da die DataLake-Zeitwerte keinen expliziten Zeitzonen-Suffix enthalten,
    werden sie für die Verarbeitung einheitlich als UTC interpretiert.

    errors="coerce":
    Nicht interpretierbare Werte werden zu NaT.
    Dadurch bricht die Anwendung bei fehlerhaften Einzelwerten nicht ab.
    """
    return pd.to_datetime(
        series,
        format="%Y-%m-%dT%H:%M:%S.%f",
        errors="coerce",
        utc=True,
    )

def summarize_no_loco_rows(
    source_df: pd.DataFrame,
    mask: pd.Series,
    source_name: str,
    reason: str,
    transport_col,
    actual_departure_col,
):
    """
    Verdichtet auffällige CSV-Zeilen auf Transportebene.

    Die Detailtabelle zeigt:
    - Datenquelle
    - Fehlergrund
    - TransportNumber
    - erstes vorhandenes ActualDeparture
    - Anzahl der betroffenen CSV-Zeilen

    Dadurch wird dieselbe TransportNumber nicht mehrfach unübersichtlich
    dargestellt, obwohl mehrere CSV-Zeilen betroffen sein können.
    """
    result_columns = [
        "Quelle",
        "Grund",
        "TransportNumber",
        "Erstes Datum",
        "Anzahl Zeilen",
    ]

    if source_df.empty or int(mask.sum()) == 0:
        return pd.DataFrame(columns=result_columns)

    work = source_df.loc[mask].copy()

    # TransportNumber aufbereiten
    if transport_col and transport_col in work.columns:
        work["TransportNumber"] = (
            work[transport_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "(ohne TransportNumber)")
        )
    else:
        work["TransportNumber"] = "(TransportNumber-Spalte fehlt)"

    # Erstes fachlich relevantes Datum aufbereiten
    if actual_departure_col and actual_departure_col in work.columns:
        work["_first_actual_departure"] = parse_actual_departure(
        work[actual_departure_col]
    )
    else:
        work["_first_actual_departure"] = pd.NaT

    grouped = (
        work
        .groupby("TransportNumber", dropna=False)
        .agg(
            _first_actual_departure=(
                "_first_actual_departure",
                "min",
            ),
            **{
                "Anzahl Zeilen": (
                    "TransportNumber",
                    "size",
                )
            },
        )
        .reset_index()
    )

    grouped.insert(0, "Grund", reason)
    grouped.insert(0, "Quelle", source_name)

    grouped = grouped.sort_values(
        by=[
            "_first_actual_departure",
            "TransportNumber",
        ],
        ascending=[
            True,
            True,
        ],
        na_position="last",
    )

    grouped["Erstes Datum"] = (
        grouped["_first_actual_departure"]
        .dt.strftime("%d.%m.%Y %H:%M")
        .fillna("Kein gültiges Datum vorhanden")
    )

    return grouped[result_columns]


def build_no_loco_diagnostics():
    """
    Erstellt die gewünschte Datenqualitätsprüfung direkt aus den Rohdaten.

    Prüfung 1:
    TransportDetail.csv
    - Zeile hat einen DE-Bezug
    - ActualDeparture ist befüllt und mindestens 24 Stunden vergangen
    - MovementType ist exakt 'Train movement'
    - FirstLocomotiveNo ist nicht befüllt

    Prüfung 2:
    LocomotiveMovement.csv
    - Zeile hat einen DE-Bezug
    - LocomotiveNo ist exakt '00000000000-0'

    Rückgabe:
    - summary_df: Übersicht mit den zwei Zählern
    - detail_df:  gruppierte Liste für den Tab 'Keine Loks'
    - warnings:   technische Hinweise bei fehlenden Dateien oder Spalten
    """
    summary_rows = []
    detail_frames = []
    warnings = []

    # ==================================================
    # Prüfung 1: TransportDetail.csv
    # ==================================================
    transport_detail = read_csv_safe(
        RAW_DIR / "TransportDetail.csv"
    )

    td_actual_col = get_col(
        transport_detail,
        ["ActualDeparture"],
    )

    td_loco_col = get_col(
        transport_detail,
        ["FirstLocomotiveNo"],
    )

    # Nur echte Zugbewegungen sollen als Fehlerfall zählen.
    # Andere MovementTypes werden bewusst ignoriert.

    td_movement_type_col = get_col(
        transport_detail,
        ["MovementType"],
    )

    td_transport_col = get_col(
        transport_detail,
        [
            "TransportNumber",
            "TransportNo",
            "TransportId",
            "TransportID",
        ],
    )

    td_is_de_relevant, td_de_country_cols = (
        build_de_relevance_mask(
            transport_detail
        )
    )

    if (
        td_actual_col
        and td_loco_col
        and td_movement_type_col
        and td_de_country_cols
    ):
        # ==================================================
        # Fehlerprüfung für TransportDetail.csv
        # ==================================================
        #
        # Eine Zeile wird nur dann als Fehlerfall gezählt, wenn:
        #
        # 1. Die Zeile einen DE-Bezug hat
        # 2. MovementType exakt "Train movement" entspricht
        # 3. ActualDeparture tatsächlich befüllt ist
        # 4. ActualDeparture mindestens 24 Stunden zurückliegt
        # 5. FirstLocomotiveNo leer ist
        #
        # Hintergrund:
        # Bei sehr neuen Transporten kann die Loknummer noch nachträglich
        # ergänzt werden. Diese Fälle sollen nicht sofort als Fehler erscheinen.
        # ==================================================

        td_is_train_movement = (
            transport_detail[td_movement_type_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq("train movement")
        )

        # ActualDeparture robust als UTC-Zeitwert interpretieren.
        #
        # errors="coerce":
        # Nicht interpretierbare Werte werden zu NaT und damit nicht gezählt.
        #
        # utc=True:
        # Alle Werte werden einheitlich als UTC behandelt.
        td_actual_departure_ts = parse_actual_departure(
        transport_detail[td_actual_col]
        )

        # Rolling Window:
        # Als Fehler gelten nur Transporte, deren ActualDeparture
        # mindestens 24 Stunden vor dem aktuellen Zeitpunkt liegt.
        td_cutoff_ts = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)

        td_is_at_least_one_day_old = (
            td_actual_departure_ts.notna()
            & (td_actual_departure_ts <= td_cutoff_ts)
        )

        td_mask = (
            td_is_de_relevant
            & td_is_train_movement
            & td_is_at_least_one_day_old
            & ~has_value(transport_detail[td_loco_col])
        )

        td_count = int(td_mask.sum())
        td_status = "OK"

        td_details = summarize_no_loco_rows(
            source_df=transport_detail,
            mask=td_mask,
            source_name="TransportDetail.csv",
            reason=(
                "DE-relevanter Abschnitt, "
                "MovementType = Train movement, "
                "ActualDeparture mindestens 24 Stunden vergangen, "
                "FirstLocomotiveNo fehlt"
            ),
            transport_col=td_transport_col,
            actual_departure_col=td_actual_col,
        )

        if not td_details.empty:
            detail_frames.append(td_details)

    else:
        td_count = None
        td_status = (
            "Nicht auswertbar: "
            "ActualDeparture, FirstLocomotiveNo, MovementType "
            "oder Länderfeld fehlt als Spalte."
        )

        warnings.append(
            "TransportDetail.csv konnte nicht vollständig geprüft werden. "
            "Benötigt werden die Spalten ActualDeparture, "
            "FirstLocomotiveNo, MovementType und mindestens ein "
            "auswertbares Länderfeld wie Country."
        )

    summary_rows.append({
        "Quelle": "TransportDetail.csv",
        "Prüfung": (
            "DE-relevanter Abschnitt, "
            "MovementType = Train movement, "
            "ActualDeparture mindestens 24 Stunden vergangen, "
            "aber FirstLocomotiveNo leer"
        ),
        "Anzahl Zeilen": td_count,
        "Status": td_status,
    })

    # ==================================================
    # Prüfung 2: LocomotiveMovement.csv
    # ==================================================
    locomotive_movement = read_csv_safe(
        RAW_DIR / "LocomotiveMovement.csv"
    )

    lm_loco_col = get_col(
        locomotive_movement,
        ["LocomotiveNo"],
    )

    lm_actual_col = get_col(
        locomotive_movement,
        [
            "ActualDeparture",
            "LocomotiveActualDeparture",
        ],
    )

    lm_transport_col = get_col(
        locomotive_movement,
        [
            "TransportNumber",
            "TransportNo",
            "TransportId",
            "TransportID",
        ],
    )

    lm_is_de_relevant, lm_de_country_cols = (
        build_de_relevance_mask(
            locomotive_movement
        )
    )

    if lm_loco_col and lm_de_country_cols:
        lm_mask = (
            lm_is_de_relevant
            & locomotive_movement[lm_loco_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .eq("00000000000-0")
        )

        lm_count = int(lm_mask.sum())
        lm_status = "OK"

        lm_details = summarize_no_loco_rows(
            source_df=locomotive_movement,
            mask=lm_mask,
            source_name="LocomotiveMovement.csv",
            reason=(
                "DE-relevanter Abschnitt, "
                "LocomotiveNo = 00000000000-0"
            ),
            transport_col=lm_transport_col,
            actual_departure_col=lm_actual_col,
        )

        if not lm_details.empty:
            detail_frames.append(lm_details)

    else:
        lm_count = None
        lm_status = (
            "Nicht auswertbar: "
            "LocomotiveNo oder Länderfeld fehlt als Spalte."
        )

        warnings.append(
            "LocomotiveMovement.csv konnte nicht vollständig geprüft werden. "
            "Benötigt werden die Spalte LocomotiveNo und mindestens "
            "ein auswertbares Länderfeld wie Country."
        )

    summary_rows.append({
        "Quelle": "LocomotiveMovement.csv",
        "Prüfung": (
            "DE-relevanter Abschnitt, "
            "LocomotiveNo = 00000000000-0"
        ),
        "Anzahl Zeilen": lm_count,
        "Status": lm_status,
    })

    # ==================================================
    # Ergebnis zusammenbauen
    # ==================================================
    summary_df = pd.DataFrame(summary_rows)

    if detail_frames:
        detail_df = pd.concat(
            detail_frames,
            ignore_index=True,
        )
    else:
        detail_df = pd.DataFrame(columns=[
            "Quelle",
            "Grund",
            "TransportNumber",
            "Erstes Datum",
            "Anzahl Zeilen",
        ])

    return summary_df, detail_df, warnings

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

timeline_path = EXPORT_DIR / "core_loco_timeline.csv"
findings_path = EXPORT_DIR / "dq_findings.csv"
rule_catalog_path = EXPORT_DIR / "cfg_dq_rule_catalog.csv"
unresolved_market_partner_path = (
    EXPORT_DIR / "dq_unresolved_performing_ru_market_partner_alias.csv"
)
vens_tens_exception_path = (
    EXPORT_DIR / "cfg_vens_tens_exception_effective.csv"
)
zuordnungen_path = EXPORT_DIR / "export_zuordnungen.csv"
nutzungsmeldung_path = EXPORT_DIR / "export_nutzungsmeldung.csv"
run_path = EXPORT_DIR / "raw_import_run.csv"

timeline = read_csv_safe(timeline_path)
findings = read_csv_safe(findings_path)
rule_catalog = read_csv_safe(rule_catalog_path)
unresolved_performing_ru_market_partner_alias = read_csv_safe(
    unresolved_market_partner_path
)
vens_tens_exception = read_csv_safe(
    vens_tens_exception_path
)
zuordnungen = read_csv_safe(zuordnungen_path)
nutzungsmeldung = read_csv_safe(nutzungsmeldung_path)
runs = read_csv_safe(run_path)

# Datenqualitätswerte direkt aus den aktuellen Rohdaten bilden.
# Dadurch werden sie bereits nach einem Download aktualisiert,
# auch wenn die Pipeline noch nicht neu berechnet wurde.
#
# WICHTIG:
# Die Diagnose wird defensiv gekapselt. Ein unerwarteter Fehler in einer
# Rohdaten-Datei darf nicht mehr die gesamte Streamlit-Seite abbrechen.
try:
    no_loco_summary, no_loco_cases, no_loco_warnings = (
        build_no_loco_diagnostics()
    )

except Exception as diagnostics_error:
    no_loco_summary = pd.DataFrame(columns=[
        "Quelle",
        "Prüfung",
        "Anzahl Zeilen",
        "Status",
    ])

    no_loco_cases = pd.DataFrame(columns=[
        "Quelle",
        "Grund",
        "TransportNumber",
        "Erstes Datum",
        "Anzahl Zeilen",
    ])

    no_loco_warnings = [
        (
            "Die Datenqualitätsprüfung 'Keine Loks' konnte nicht vollständig "
            f"ausgeführt werden: {diagnostics_error}"
        )
    ]

    st.error(
        "Fehler beim Aufbau der Datenqualitätsprüfung 'Keine Loks'. "
        "Die übrigen Bereiche der Anwendung bleiben verfügbar."
    )

    st.exception(diagnostics_error)

tab_overview, tab_no_loco, tab_timeline, tab_findings, tab_exports, tab_run = st.tabs([
    "Überblick",
    "Keine Loks",
    "Lok-Zeitachse",
    "Fehlerqueue",
    "Exporte",
    "Pipeline"
])

with tab_overview:
    st.subheader("Überblick")

        # ==================================================
    # Vollständigen Tageslauf starten
    # ==================================================
    #
    # Ein Klick führt beide Schritte automatisch aus:
    #
    # 1. Aktuelle Rohdaten aus Azure Blob Storage laden
    # 2. Alte DuckDB entfernen und sämtliche Werte neu berechnen
    #
    # Während ein Schritt läuft, zeigt Streamlit einen Ladekreis.
    # Nach erfolgreichem Abschluss wird daraus ein grüner Haken.
    #
    # Nach Abschluss wird die Seite automatisch neu geladen.
    # Die beiden grünen Haken bleiben für die aktuelle Browser-
    # Sitzung sichtbar.
    # ==================================================

    import_info_col, import_button_col = st.columns([4, 1])

    # --------------------------------------------------
    # Zeitpunkt des letzten Imports anzeigen
    # --------------------------------------------------
    with import_info_col:
        last_import = get_last_raw_import_datetime()

        if last_import:
            st.markdown(
                f"### Letzter Import am "
                f"{last_import:%d.%m.%Y} "
                f"um {last_import:%H:%M}"
            )
        else:
            st.markdown(
                "### Letzter Import: noch nicht vorhanden"
            )

    # --------------------------------------------------
    # Button für vollständigen Tageslauf
    # --------------------------------------------------
    with import_button_col:
        start_new_import = st.button(
            "Neuen Import starten",
            type="primary",
            use_container_width=True,
            key="overview_start_new_import",
        )

    # --------------------------------------------------
    # Nach erfolgreichem Lauf:
    # Beide grünen Haken nach dem automatischen Neuladen
    # weiterhin anzeigen.
    # --------------------------------------------------
    if st.session_state.get(
        "overview_refresh_completed",
        False,
    ):
        st.status(
            "Neue Rohdaten wurden aus Azure Blob Storage geladen.",
            state="complete",
            expanded=False,
        )

        st.status(
            "Berechnung der neuen Werte wurde abgeschlossen.",
            state="complete",
            expanded=False,
        )

        completed_at = st.session_state.get(
            "overview_refresh_completed_at"
        )

        if completed_at:
            st.caption(
                f"Letzter vollständiger Tageslauf: {completed_at}"
            )

    # --------------------------------------------------
    # Vollständigen Tageslauf ausführen
    # --------------------------------------------------
    if start_new_import:
        # Alte Erfolgsmeldungen ausblenden, sobald ein
        # neuer Lauf beginnt.
        st.session_state["overview_refresh_completed"] = False

        st.session_state.pop(
            "overview_refresh_completed_at",
            None,
        )

        # ==============================================
        # SCHRITT 1:
        # Neue Rohdaten aus Azure Blob Storage laden
        # ==============================================
        if not SCRIPT_DOWNLOAD_BLOB.exists():
            st.error(
                f"Download-Skript nicht gefunden: "
                f"{SCRIPT_DOWNLOAD_BLOB}"
            )

            st.stop()

        with st.status(
            "Neue Rohdaten werden aus Azure Blob Storage geladen ...",
            expanded=True,
        ) as download_status:
            download_result = run_python_script(
                SCRIPT_DOWNLOAD_BLOB
            )

            if download_result.returncode == 0:
                download_status.update(
                    label=(
                        "Neue Rohdaten wurden aus Azure Blob Storage "
                        "geladen."
                    ),
                    state="complete",
                    expanded=False,
                )

            else:
                download_status.update(
                    label=(
                        "Fehler beim Laden der Rohdaten aus "
                        "Azure Blob Storage."
                    ),
                    state="error",
                    expanded=True,
                )

                st.error(
                    "Der Azure-Download ist fehlgeschlagen. "
                    "Die Neuberechnung wurde nicht gestartet."
                )

                st.text_area(
                    "Fehler beim Azure-Download",
                    download_result.stderr,
                    height=220,
                )

                st.text_area(
                    "Output des Azure-Downloads",
                    download_result.stdout,
                    height=220,
                )

                st.stop()

        # ==============================================
        # SCHRITT 2:
        # Werte sicher neu berechnen
        #
        # run_all.py baut zuerst netzentgelt_build.duckdb auf und ersetzt
        # den letzten produktiven Stand erst nach einem erfolgreichen Lauf.
        # ==============================================
        if not SCRIPT_RUN_ALL.exists():
            st.error(
                f"Pipeline-Skript nicht gefunden: "
                f"{SCRIPT_RUN_ALL}"
            )

            st.stop()

        with st.status(
            "Berechnen der neuen Werte ...",
            expanded=True,
        ) as calculation_status:
            try:
                st.write(
                    "Die neue DuckDB wird zunächst als Build-Datei erzeugt. "
                    "Der bisherige Tagesstand bleibt bis zum erfolgreichen "
                    "Abschluss erhalten."
                )

                # run_all.py importiert die neuen Rohdaten,
                # baut eine temporäre Build-Datenbank auf und erzeugt
                # DuckDB sowie CSV-Exporte vollständig neu.
                calculation_result = run_python_script(
                    SCRIPT_RUN_ALL
                )

            except Exception as error:
                calculation_status.update(
                    label=(
                        "Fehler beim Start der Berechnung."
                    ),
                    state="error",
                    expanded=True,
                )

                st.error(
                    f"Berechnung konnte nicht gestartet werden: "
                    f"{error}"
                )

                st.stop()

            if calculation_result.returncode == 0:
                calculation_status.update(
                    label=(
                        "Berechnung der neuen Werte wurde "
                        "abgeschlossen."
                    ),
                    state="complete",
                    expanded=False,
                )

            else:
                calculation_status.update(
                    label=(
                        "Fehler bei der Berechnung der neuen Werte."
                    ),
                    state="error",
                    expanded=True,
                )

                st.error(
                    "Die Neuberechnung ist fehlgeschlagen."
                )

                st.text_area(
                    "Fehler der Berechnung",
                    calculation_result.stderr,
                    height=220,
                )

                st.text_area(
                    "Output der Berechnung",
                    calculation_result.stdout,
                    height=220,
                )

                st.stop()

        # ==============================================
        # Beide Schritte erfolgreich abgeschlossen
        # ==============================================
        st.session_state["overview_refresh_completed"] = True

        st.session_state["overview_refresh_completed_at"] = (
            datetime.now().strftime("%d.%m.%Y um %H:%M")
        )

        # Seite automatisch neu laden:
        # Timeline, Findings, Exporte und Kennzahlen
        # werden dadurch aus den neuen CSV-Dateien gelesen.
        st.rerun()

    st.divider()

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

    # ==================================================
    # Übersicht der fehlenden bzw. technischen Loknummern
    # ==================================================
    st.subheader(
        "Datenqualität: fehlende oder technische Loknummern"
    )

    st.caption(
        "Diese Zähler werden direkt aus TransportDetail.csv "
        "und LocomotiveMovement.csv gebildet."
    )

    for warning in no_loco_warnings:
        st.warning(warning)

    st.dataframe(
        no_loco_summary,
        use_container_width=True,
        hide_index=True,
    )

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

with tab_no_loco:
    st.subheader("Keine Loks")

    st.caption(
        "Auflistung der Transporte aus den beiden Rohdaten-Prüfungen. "
        "Je Transport wird das früheste vorhandene ActualDeparture "
        "und die Anzahl der betroffenen CSV-Zeilen angezeigt."
    )

    for warning in no_loco_warnings:
        st.warning(warning)

    if no_loco_cases.empty:
        st.success(
            "Keine auffälligen Transporte gefunden."
        )

    else:
        st.write(
            f"Betroffene Transporte: "
            f"**{len(no_loco_cases)}**"
        )

        st.dataframe(
            no_loco_cases,
            use_container_width=True,
            hide_index=True,
        )

        csv = (
            no_loco_cases
            .to_csv(index=False, sep=";")
            .encode("utf-8-sig")
        )

        st.download_button(
            "Liste 'Keine Loks' herunterladen",
            data=csv,
            file_name="keine_loks.csv",
            mime="text/csv",
        )


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
            selected_loco = st.selectbox(
                "Lok auswählen",
                ["Alle"] + locos,
                key="timeline_preview_loco",
            )

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

    st.caption(
        "Die Queue enthält einzelne Regelverletzungen. "
        "Ein Transport kann mehrfach vorkommen, wenn mehrere Regeln greifen."
    )

    with st.expander(
        "⚪ Ausnahmeliste vEns/tEns",
        expanded=False,
    ):
        st.caption(
            "Diese PerformingRUs sind explizit von den vEns-/tEns-bezogenen "
            "Prüfungen ausgenommen. Für sie werden weder R006 noch R007 erzeugt. "
            "Zeitachsenfehler und fehlende PerformingRU bleiben weiterhin aktiv."
        )

        if vens_tens_exception.empty:
            st.info(
                "Keine aktive vEns-/tEns-Ausnahmeliste gefunden "
                "oder Exportdatei noch nicht vorhanden."
            )
        else:
            st.dataframe(
                vens_tens_exception,
                use_container_width=True,
                hide_index=True,
            )

    with st.expander(
        "🏢 Ungeklärte PerformingRU-Schreibweisen",
        expanded=False,
    ):
        st.caption(
            "Diese Liste enthält DE-relevante PerformingRU-Werte ohne "
            "eindeutige ANU_VENS-Marktpartner-ID. PerformingRUs auf der "
            "freigegebenen vEns-/tEns-Ausnahmeliste werden hier nicht angezeigt."
        )

        if unresolved_performing_ru_market_partner_alias.empty:
            st.success(
                "Keine ungeklärten PerformingRU-Schreibweisen gefunden "
                "oder Exportdatei noch nicht vorhanden."
            )

        else:
            st.write(
                "Ungeklärte Schreibweisen: "
                f"**{len(unresolved_performing_ru_market_partner_alias)}**"
            )

            st.dataframe(
                unresolved_performing_ru_market_partner_alias,
                use_container_width=True,
                hide_index=True,
            )

            unresolved_csv = (
                unresolved_performing_ru_market_partner_alias
                .to_csv(
                    index=False,
                    sep=";",
                )
                .encode("utf-8-sig")
            )

            st.download_button(
                "Ungeklärte PerformingRU-Schreibweisen herunterladen",
                data=unresolved_csv,
                file_name="dq_unresolved_performing_ru_market_partner_alias.csv",
                mime="text/csv",
                key="download_unresolved_performing_ru_market_partner_alias",
            )

    if findings.empty:
        st.success("Keine Findings gefunden oder Datei dq_findings.csv fehlt.")

    else:
        filtered_findings = findings.copy()

        severity_col = get_col(findings, ["severity"])
        rule_col = get_col(findings, ["rule_id", "rule"])
        loco_col = get_col(
            findings,
            [
                "loco_no",
                "LocomotiveNo",
                "locomotive_no",
            ],
        )

        # ==================================================
        # Farbige Filter-Chips für Severity und Regeln
        # ==================================================
        #
        # Streamlit verwendet für Multiselect-Chips standardmäßig die
        # Accent-Color des Themes. Damit INFO/WARNING nicht wie ERROR wirken,
        # erhalten die Einträge zusätzlich eindeutige Symbole und – soweit
        # durch das aktuelle Streamlit-Frontend unterstützt – eigene Farben.
        #
        # Regeln werden nach ihrer höchsten aktuell auftretenden Severity
        # eingefärbt. Das ist bei gemischten Regeln wie R001 bewusst defensiv:
        # Wenn mindestens ein ERROR existiert, bleibt der Regel-Chip rot.
        # ==================================================
        severity_priority = {
            "ERROR": 40,
            "MANUAL_REVIEW": 30,
            "WARNING": 20,
            "INFO": 10,
        }

        severity_icon = {
            "ERROR": "🔴",
            "MANUAL_REVIEW": "🟠",
            "WARNING": "🟡",
            "INFO": "🟡",
        }

        severity_label = {
            level: f"{severity_icon[level]} {level}"
            for level in severity_icon
        }

        rule_severity_map = {}

        if rule_col and severity_col:
            for rule_id, group in findings.groupby(
                rule_col,
                dropna=False,
            ):
                levels = [
                    str(value).strip().upper()
                    for value in group[severity_col]
                    .dropna()
                    .astype(str)
                    .tolist()
                    if str(value).strip().upper()
                    in severity_priority
                ]

                if levels:
                    rule_severity_map[str(rule_id)] = max(
                        levels,
                        key=lambda level: severity_priority[level],
                    )

        rule_label = {
            str(rule_id): (
                f"{severity_icon.get(level, '⚪')} {rule_id}"
            )
            for rule_id, level in rule_severity_map.items()
        }

        # ==================================================
        # Neutrale Filter-Chips
        # ==================================================
        #
        # Die Severity bleibt über die Emojis sichtbar. Die Chip-Fläche
        # bleibt bewusst neutral, damit INFO/WARNING nicht wie ERROR wirken.
        # ==================================================
# ==================================================
# Neutrale Filter-Chips
# ==================================================
        st.markdown(
            """
            <style>
            /* Streamlit Multiselect-Chips neutral darstellen */
            [data-baseweb="tag"] {
                background-color: #2B2D36 !important;
                border: 1px solid #4A4D57 !important;
                color: #F5F5F5 !important;
            }

            [data-baseweb="tag"] span {
                color: #F5F5F5 !important;
            }

            [data-baseweb="tag"] svg {
                fill: #F5F5F5 !important;
                color: #F5F5F5 !important;
            }

            [data-baseweb="tag"]:hover {
                background-color: #353842 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Defaultwerte sicher initialisieren. Dadurch bleibt die Legende auch
        # bei unerwarteten Spaltenstrukturen robust.
        selected_sev = []
        selected_rules = []
        selected_loco_find = "Alle"

        f1, f2, f3 = st.columns(3)

        with f1:
            if severity_col:
                severities = sorted(
                    findings[severity_col]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )

                selected_sev = st.multiselect(
                    "Severity",
                    severities,
                    default=severities,
                    format_func=lambda value: severity_label.get(
                        str(value).strip().upper(),
                        str(value),
                    ),
                    key="findings_filter_severity",
                )

                filtered_findings = filtered_findings[
                    filtered_findings[severity_col]
                    .astype(str)
                    .isin(selected_sev)
                ]

        with f2:
            if rule_col:
                rules = sorted(
                    findings[rule_col]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )

                selected_rules = st.multiselect(
                    "Regel",
                    rules,
                    default=rules,
                    format_func=lambda value: rule_label.get(
                        str(value),
                        f"⚪ {value}",
                    ),
                    key="findings_filter_rules",
                )

                filtered_findings = filtered_findings[
                    filtered_findings[rule_col]
                    .astype(str)
                    .isin(selected_rules)
                ]

        with f3:
            if loco_col:
                locos = sorted(
                    findings[loco_col]
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )

                selected_loco_find = st.selectbox(
                    "Lok",
                    ["Alle"] + locos,
                    key="findings_filter_loco",
                )

                if selected_loco_find != "Alle":
                    filtered_findings = filtered_findings[
                        filtered_findings[loco_col]
                        .astype(str)
                        .eq(selected_loco_find)
                    ]

        # ==================================================
        # Statische Legende aller Regeln
        # ==================================================
        #
        # Die Legende bleibt bewusst unabhängig von den Filtern sichtbar.
        # Sie zeigt zusätzlich die aktuellen Trefferzahlen je Regel sowie
        # deren Verteilung nach Severity.
        # ==================================================
        with st.expander(
            "📘 Legende der Fehlerregeln",
            expanded=True,
        ):
            st.caption(
                "Die Legende bleibt unabhängig von den gesetzten Filtern "
                "vollständig sichtbar. Die Spalte 'Anzahl' bezieht sich "
                "auf den aktuellen Datenlauf vor Anwendung der Filter."
            )

            legend_df = pd.DataFrame()

            if not rule_catalog.empty:
                catalog_rule_col = get_col(
                    rule_catalog,
                    ["rule_id", "rule"],
                )

                if catalog_rule_col:
                    legend_df = rule_catalog.copy()

                    rename_map = {}

                    for candidate, display_name in [
                        ("rule_id", "Regel"),
                        ("rule_group", "Kategorie"),
                        ("severity_policy", "Severity-Regel"),
                        ("description", "Bedeutung"),
                        ("active_flag", "Aktiv"),
                    ]:
                        actual_col = get_col(
                            legend_df,
                            [candidate],
                        )

                        if actual_col:
                            rename_map[actual_col] = display_name

                    legend_df = legend_df.rename(
                        columns=rename_map
                    )

            # Fallback für ältere Exporte ohne cfg_dq_rule_catalog.csv.
            if legend_df.empty and rule_col:
                legend_df = (
                    findings[
                        [rule_col]
                    ]
                    .drop_duplicates()
                    .rename(
                        columns={
                            rule_col: "Regel",
                        }
                    )
                )

            if legend_df.empty:
                st.info(
                    "Für die Regeln konnte keine Legende ermittelt werden."
                )

            else:
                # Trefferzahlen aus der vollständigen Findings-Datei bilden.
                count_df = pd.DataFrame()

                if rule_col:
                    count_source = findings.copy()

                    count_source["_rule_for_count"] = (
                        count_source[rule_col]
                        .fillna("")
                        .astype(str)
                    )

                    count_df = (
                        count_source
                        .groupby(
                            "_rule_for_count",
                            dropna=False,
                        )
                        .size()
                        .rename("Anzahl")
                        .reset_index()
                        .rename(
                            columns={
                                "_rule_for_count": "Regel",
                            }
                        )
                    )


                if "Regel" in legend_df.columns:
                    legend_df["Regel"] = (
                        legend_df["Regel"]
                        .fillna("")
                        .astype(str)
                    )

                    if not count_df.empty:
                        legend_df = legend_df.merge(
                            count_df,
                            on="Regel",
                            how="left",
                        )

                for numeric_col in [
                    "Anzahl",
                ]:
                    if numeric_col not in legend_df.columns:
                        legend_df[numeric_col] = 0

                    legend_df[numeric_col] = (
                        pd.to_numeric(
                            legend_df[numeric_col],
                            errors="coerce",
                        )
                        .fillna(0)
                        .astype(int)
                    )

                preferred_legend_cols = [
                    "Regel",
                    "Anzahl",
                    "Bedeutung",
                    "Aktiv",
                ]

                legend_df = legend_df[
                    [
                        col
                        for col in preferred_legend_cols
                        if col in legend_df.columns
                    ]
                ]

                if "Regel" in legend_df.columns:
                    legend_df = legend_df.sort_values(
                        by="Regel"
                    )

                st.dataframe(
                    legend_df,
                    use_container_width=True,
                    hide_index=True,
                )

        st.write(
            f"Treffer gesamt: **{len(filtered_findings)}**"
        )

        max_rows = st.number_input(
            "Maximale Anzeigezeilen",
            min_value=100,
            max_value=10000,
            value=1000,
            step=100,
            key="findings_max_display_rows",
        )

        display_findings = filtered_findings.head(
            int(max_rows)
        )

        st.info(
            f"Angezeigt werden {len(display_findings)} von "
            f"{len(filtered_findings)} Treffern. "
            "Die vollständige Datei bleibt im Exportordner erhalten."
        )

        st.dataframe(
            display_findings,
            use_container_width=True,
            hide_index=True,
        )

        csv = (
            display_findings
            .to_csv(
                index=False,
                sep=";",
            )
            .encode("utf-8-sig")
        )

        st.download_button(
            "Angezeigte Fehlerliste herunterladen",
            data=csv,
            file_name="dq_findings_gefiltert_preview.csv",
            mime="text/csv",
            key="findings_download_preview",
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

with tab_timeline:
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
            index=0 if loco_values else None,
            key="timeline_detail_loco",
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
                "performing_ru_marktpartner_id",
                "exempt_vens",
                "exempt_tens",
                "vens_tens_exception_flag",
                "vens_tens_exception_comment",
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
                    transport_values,
                    key="timeline_detail_transport",
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
