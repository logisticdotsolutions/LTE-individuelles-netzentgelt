from __future__ import annotations

import argparse
import datetime as dt
import py_compile
import re
import shutil
from pathlib import Path

MARKER = "NETZENTGELT_REST_EXPORT_PHASE4_V1_20260607"
ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app" / "app.py"
PAYLOAD = ROOT / "payload" / "rest_export_module.py"
MODULE_TARGET = ROOT / "scripts" / "rest_export_module.py"
BACKUP_ROOT = ROOT / ".patch_backups"
LAST_BACKUP_FILE = ROOT / ".rest_export_phase4_last_backup.txt"


def read_text_preserve_bom(path: Path) -> tuple[str, bool, str]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    newline_style = "\r\n" if "\r\n" in decoded else "\n"
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, has_bom, newline_style


def write_text_preserve_bom(path: Path, text: str, has_bom: bool, newline_style: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    rendered = normalized if newline_style == "\n" else normalized.replace("\n", newline_style)
    raw = rendered.encode("utf-8")
    if has_bom:
        raw = b"\xef\xbb\xbf" + raw
    path.write_bytes(raw)


def require_path(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"Erwartete Datei fehlt: {path}")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. "
            f"Erwartet: 1, gefunden: {count}. "
            "Bitte lokalen Stand prüfen und bei Bedarf zuerst pushen."
        )
    return text.replace(old, new, 1)


def patch_app(text: str) -> str:
    if MARKER in text:
        return text

    export_import_pattern = re.compile(
        r"(from export_module import \(\n(?:    .*\n)+?\)\n)",
        re.MULTILINE,
    )
    match = export_import_pattern.search(text)
    if not match:
        raise RuntimeError("Importblock aus export_module wurde in app/app.py nicht gefunden.")

    import_line = (
        "from rest_export_module import PRIMARY_EXPORT_GROUPS, list_rest_export_overview\n"
    )
    text = text[: match.end()] + import_line + text[match.end() :]

    start_anchor = """            unconfigured_lte_performing_rus = list_unconfigured_lte_performing_rus(
                db_path=DB_PATH
            )
"""
    end_anchor = """    st.divider()

    with st.expander("Technische CSV-Exportdateien", expanded=False):
"""

    start_pos = text.find(start_anchor)
    if start_pos < 0:
        raise RuntimeError("Start des bisherigen RU-Exportblocks wurde nicht gefunden.")
    end_pos = text.find(end_anchor, start_pos)
    if end_pos < 0:
        raise RuntimeError("Ende des bisherigen RU-Exportblocks wurde nicht gefunden.")

    replacement = '''            # ==================================================
            # NETZENTGELT_REST_EXPORT_PHASE4_V1_20260607
            # Fachlich klare Exportgruppen: LTE DE, LTE NL und Rest.
            # ==================================================
            st.subheader("XLSX-Exporte nach nutzendem EVU")
            st.caption(
                "Die beiden Hauptgruppen LTE DE und LTE NL werden gesammelt bereitgestellt. "
                "Alle weiteren nutzenden EVU erscheinen gesammelt unter Rest. "
                "Ein Rest-Download bleibt bewusst je PerformingRU getrennt, weil die offizielle "
                "Vorlage pro Datei eindeutige Marktpartner-Kopfdaten erwartet."
            )

            for group_key, group_config in PRIMARY_EXPORT_GROUPS.items():
                st.divider()
                st.markdown(f"### {group_config['title']}")

                render_nutzungsmeldung_export_section(
                    title="Nutzungsmeldung",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_nutzung_{group_key.lower()}",
                )

                render_aufenthaltsereignis_export_section(
                    title="Aufenthaltsereignisse",
                    export_label=group_config["file_label"],
                    performing_ru_values=tuple(group_config["performing_ru_values"]),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix=f"primary_aufenthalt_{group_key.lower()}",
                )

            st.divider()
            st.markdown("### Rest")
            st.caption(
                "Rest umfasst sämtliche PerformingRUs außerhalb LTE DE und LTE NL. "
                "Die Übersicht zeigt transparent, wie viele DE-relevante Bewegungszeilen je "
                "PerformingRU betroffen sind. Sofern OrderOwner in den importierten Daten verfügbar "
                "ist, kann die Detailansicht zusätzlich danach aufgeteilt werden."
            )

            rest_rows = list_rest_export_overview(
                db_path=DB_PATH,
                date_from=export_date_from,
                date_to=export_date_to,
            )
            rest_df = pd.DataFrame(rest_rows)

            if rest_df.empty:
                st.success("Keine Restzeilen im gewählten Zeitraum vorhanden.")
            else:
                rest_total = int(rest_df["Betroffene Bewegungszeilen"].sum())
                rest_blocked = int(rest_df["Davon gesperrt"].sum())
                rest_ru_count = int(rest_df["PerformingRU"].nunique())

                metric_rest_1, metric_rest_2, metric_rest_3 = st.columns(3)
                with metric_rest_1:
                    st.metric("Restzeilen gesamt", rest_total)
                with metric_rest_2:
                    st.metric("PerformingRUs im Rest", rest_ru_count)
                with metric_rest_3:
                    st.metric("Davon gesperrte Zeilen", rest_blocked)

                rest_summary = (
                    rest_df
                    .groupby("PerformingRU", as_index=False, dropna=False)
                    .agg({
                        "Betroffene Bewegungszeilen": "sum",
                        "Davon exportfähig": "sum",
                        "Davon gesperrt": "sum",
                        "Betroffene Loks": "sum",
                        "Betroffene Transporte": "sum",
                    })
                    .sort_values(
                        by=["Betroffene Bewegungszeilen", "PerformingRU"],
                        ascending=[False, True],
                    )
                )

                st.markdown("#### Restzeilen je PerformingRU")
                st.dataframe(rest_summary, use_container_width=True, hide_index=True)

                with st.expander("Restzeilen zusätzlich nach OrderOwner aufteilen", expanded=False):
                    if (
                        "OrderOwner" not in rest_df.columns
                        or rest_df["OrderOwner"].fillna("").eq("Nicht verfügbar").all()
                    ):
                        st.info(
                            "OrderOwner ist in den aktuell importierten Daten nicht verfügbar. "
                            "Die Restübersicht bleibt deshalb auf PerformingRU-Ebene."
                        )
                    st.dataframe(rest_df, use_container_width=True, hide_index=True)

                    rest_csv = rest_df.to_csv(index=False, sep=";").encode("utf-8-sig")
                    st.download_button(
                        "Restübersicht als CSV herunterladen",
                        data=rest_csv,
                        file_name="rest_export_uebersicht.csv",
                        mime="text/csv",
                        key="download_rest_export_overview",
                    )

                selected_rest_ru = st.selectbox(
                    "Rest-PerformingRU für Download auswählen",
                    rest_summary["PerformingRU"].astype(str).tolist(),
                    key="rest_export_selected_performing_ru",
                )

                st.markdown(f"#### Einzel-Downloads für {selected_rest_ru}")
                render_nutzungsmeldung_export_section(
                    title="Nutzungsmeldung",
                    export_label=f"REST_{selected_rest_ru}",
                    performing_ru_values=(selected_rest_ru,),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix="rest_nutzung",
                )

                render_aufenthaltsereignis_export_section(
                    title="Aufenthaltsereignisse",
                    export_label=f"REST_{selected_rest_ru}",
                    performing_ru_values=(selected_rest_ru,),
                    date_from_value=export_date_from,
                    date_to_value=export_date_to,
                    key_suffix="rest_aufenthalt",
                )

'''

    text = text[:start_pos] + replacement + text[end_pos:]
    return text


def backup_files(paths: list[Path]) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"netzentgelt_rest_export_phase4_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for path in paths:
        if not path.exists():
            continue
        destination = backup_dir / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    LAST_BACKUP_FILE.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in [APP_PATH, PAYLOAD]:
        require_path(path)

    app_text, has_bom, newline_style = read_text_preserve_bom(APP_PATH)
    patched_app = patch_app(app_text)

    print("Rest-Export-Phase-4-Patch wurde gegen den lokalen Stand validiert.")
    print("Geplante Änderungen:")
    print("- app/app.py")
    print("- scripts/rest_export_module.py")

    if args.dry_run:
        print("DRY RUN erfolgreich. Es wurden keine Dateien verändert.")
        return 0

    backup_dir = backup_files([APP_PATH, MODULE_TARGET])
    print(f"Backup erstellt: {backup_dir}")

    try:
        write_text_preserve_bom(APP_PATH, patched_app, has_bom, newline_style)
        MODULE_TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PAYLOAD, MODULE_TARGET)
        py_compile.compile(str(APP_PATH), doraise=True)
        py_compile.compile(str(MODULE_TARGET), doraise=True)
    except Exception:
        print("Fehler beim Patchen. Stelle Backup automatisch wieder her.")
        source_app = backup_dir / APP_PATH.relative_to(ROOT)
        if source_app.exists():
            shutil.copy2(source_app, APP_PATH)
        source_module = backup_dir / MODULE_TARGET.relative_to(ROOT)
        if source_module.exists():
            MODULE_TARGET.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_module, MODULE_TARGET)
        elif MODULE_TARGET.exists():
            MODULE_TARGET.unlink()
        raise

    print("Rest-Export-Phase-4-Patch erfolgreich angewendet und syntaktisch validiert.")
    print("Nächster Schritt: 03_VALIDATE_REST_EXPORT_PHASE4.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
