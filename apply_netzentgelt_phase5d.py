from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import sys
from datetime import datetime, timezone

PHASE_ID = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_V1_20260608"
ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / ".netzentgelt_hotfix_backups"
LATEST_POINTER = BACKUP_ROOT / "manual_override_phase5d_latest.txt"

FILES = (
    "scripts/manual_override_ui_module.py",
    "scripts/manual_override_suggestion_module.py",
    "scripts/manual_override_batch_module.py",
)

UI_PATH = "scripts/manual_override_ui_module.py"
SUGGESTION_PATH = "scripts/manual_override_suggestion_module.py"
BATCH_PATH = "scripts/manual_override_batch_module.py"
BATCH_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_BATCH_V1_20260608"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def detect_newline(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def decode_text(raw: bytes, path: str) -> tuple[str, str]:
    newline = detect_newline(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{path}: UTF-8-Dekodierung fehlgeschlagen: {exc}") from exc
    return text.replace("\r\n", "\n"), newline


def encode_text(text: str, newline: str, *, bom: bool = False) -> bytes:
    normalized = text.replace("\r\n", "\n")
    rendered = normalized.replace("\n", newline)
    encoding = "utf-8-sig" if bom else "utf-8"
    return rendered.encode(encoding)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. "
            "Lokalen Stand pruefen."
        )
    return text.replace(old, new, 1)


def patch_suggestion(text: str) -> str:
    if PHASE_ID in text:
        return text

    text = replace_once(
        text,
        'PHASE5B_SUGGESTION_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_SUGGESTIONS_V1_20260607"\n',
        'PHASE5B_SUGGESTION_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_SUGGESTIONS_V1_20260607"\n'
        f'PHASE5D_SUGGESTION_MARKER = "{PHASE_ID}"\n',
        "suggestion marker",
    )

    text = replace_once(
        text,
        "- gebrochene Ortskette als vermutete fehlende Bewegung\n"
        "- längere Standzeit am selben Ort als mögliche kalte Abstellung\n",
        "- gebrochene Ortskette als vermutete fehlende Bewegung\n"
        "- PerformingRU eines GAPs aus identischen direkten Nachbarbewegungen\n"
        "- längere Standzeit am selben Ort als mögliche kalte Abstellung\n",
        "suggestion doc gap performing ru",
    )

    helper = r'''
def _bool_flag(value: object) -> bool:
    return _clean(value).lower() in {"true", "1", "yes", "y", "ja"}


def _suggest_gap_performing_ru_from_neighbours(timeline: pd.DataFrame) -> list[Suggestion]:
    """
    PerformingRU fuer eine DE-relevante GAP-Zeile nur dann vorschlagen, wenn
    die unmittelbar vorherige und die unmittelbar nachfolgende Bewegung
    derselben Lok eindeutig dieselbe PerformingRU enthalten.

    Der Vorschlag dokumentiert eine lokale GAP-Klassifikation. Er schreibt
    keine Quelldaten um und hebt keine Exportsperre automatisch auf.
    """
    if timeline is None or timeline.empty or "row_type" not in timeline.columns:
        return []

    work = timeline.copy()
    work["_phase5d_sort_sequence"] = pd.to_numeric(
        work.get("sort_sequence", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )
    work["_phase5d_sort_ts"] = pd.to_datetime(
        work.get("period_start_utc", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )
    work["_phase5d_source_row_id"] = pd.to_numeric(
        work.get("source_row_id", pd.Series(index=work.index, dtype="object")),
        errors="coerce",
    )

    suggestions: list[Suggestion] = []
    for loco_no, group in work.groupby("loco_no", dropna=False):
        ordered = group.sort_values(
            ["_phase5d_sort_sequence", "_phase5d_sort_ts", "_phase5d_source_row_id"],
            na_position="last",
        ).reset_index(drop=True)

        for index, gap in ordered.iterrows():
            if _clean(gap.get("row_type")).upper() != "GAP":
                continue
            if not _bool_flag(gap.get("gap_relevant_de")):
                continue

            previous = None
            for previous_index in range(index - 1, -1, -1):
                candidate = ordered.iloc[previous_index]
                if _clean(candidate.get("row_type")).upper() == "MOVEMENT":
                    previous = candidate
                    break

            following = None
            for following_index in range(index + 1, len(ordered)):
                candidate = ordered.iloc[following_index]
                if _clean(candidate.get("row_type")).upper() == "MOVEMENT":
                    following = candidate
                    break

            if previous is None or following is None:
                continue

            previous_ru = _clean(previous.get("performing_ru"))
            following_ru = _clean(following.get("performing_ru"))
            if not previous_ru or previous_ru != following_ru:
                continue

            suggestions.append(
                _new_suggestion(
                    suggestion_type="GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS",
                    override_type="CLASSIFY_GAP",
                    classification_code="SAME_RU_CONTINUITY",
                    confidence="HIGH",
                    suggested_value=previous_ru,
                    loco_no=_clean(loco_no),
                    transport_number=_clean(gap.get("transport_number")) or _clean(previous.get("transport_number")),
                    period_start_utc=_timestamp_text(gap.get("period_start_utc")),
                    period_end_utc=_timestamp_text(gap.get("period_end_utc")),
                    source_table=_clean(gap.get("source_table")),
                    source_row_id=_clean(gap.get("source_row_id")),
                    reason=(
                        "Vor und nach der DE-relevanten GAP-Zeile ist dieselbe PerformingRU vorhanden. "
                        "Lokale GAP-Klassifikation fachlich bestaetigen."
                    ),
                    evidence=(
                        f"Vorherige Bewegung: Transport {_clean(previous.get('transport_number')) or '-'}, "
                        f"PerformingRU {previous_ru}, Beginn {_timestamp_text(previous.get('period_start_utc')) or '-'}; "
                        f"nachfolgende Bewegung: Transport {_clean(following.get('transport_number')) or '-'}, "
                        f"PerformingRU {following_ru}, Beginn {_timestamp_text(following.get('period_start_utc')) or '-'}; "
                        "beide direkten Nachbarn stimmen ueberein."
                    ),
                )
            )

    return suggestions


'''
    text = replace_once(
        text,
        "def _suggest_broken_chain_gaps(timeline: pd.DataFrame) -> list[Suggestion]:\n",
        helper + "def _suggest_broken_chain_gaps(timeline: pd.DataFrame) -> list[Suggestion]:\n",
        "suggest gap performing ru helper",
    )

    text = replace_once(
        text,
        "    suggestions.extend(_suggest_broken_chain_gaps(timeline))\n"
        "    suggestions.extend(_suggest_cold_stands(timeline))\n",
        "    suggestions.extend(_suggest_broken_chain_gaps(timeline))\n"
        "    suggestions.extend(_suggest_gap_performing_ru_from_neighbours(timeline))\n"
        "    suggestions.extend(_suggest_cold_stands(timeline))\n",
        "suggestion table gap ru extension",
    )
    return text


def patch_ui(text: str) -> str:
    if PHASE_ID in text:
        return text

    text = replace_once(
        text,
        'PHASE5B_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607"\n',
        'PHASE5B_UI_MARKER = "NETZENTGELT_MANUAL_OVERRIDE_PHASE5B_UI_V1_20260607"\n'
        f'PHASE5D_UI_MARKER = "{PHASE_ID}"\n',
        "ui marker",
    )

    old_import = '''from manual_override_suggestion_module import (
    PHASE5B_SUGGESTION_MARKER,
    SUGGESTION_COLUMNS,
    build_suggestion_table,
    suggestion_for_case,
)
'''
    new_import = old_import + '''from manual_override_batch_module import (
    PHASE5D_BATCH_MARKER,
    create_overrides_from_selected_suggestions,
)
'''
    text = replace_once(text, old_import, new_import, "ui batch import")

    text = replace_once(
        text,
        '    "MISSING_MOVEMENT": "Fehlende Bewegung vermutet",\n',
        '    "MISSING_MOVEMENT": "Fehlende Bewegung vermutet",\n'
        '    "SAME_RU_CONTINUITY": "PerformingRU vor und nach GAP identisch",\n',
        "ui classification same ru",
    )

    text = replace_once(
        text,
        '    "PERFORMING_RU_FROM_NEIGHBOURHOOD": "PerformingRU aus angrenzenden Bewegungen",\n',
        '    "PERFORMING_RU_FROM_NEIGHBOURHOOD": "PerformingRU aus angrenzenden Bewegungen",\n'
        '    "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS": "PerformingRU fuer GAP aus beiden Nachbarbewegungen",\n',
        "ui suggestion label gap ru",
    )

    helper = r'''
def _save_selected_suggestions(
    *,
    suggestions: pd.DataFrame,
    selected_suggestion_ids: list[str],
    created_by: str,
    comment: str,
) -> tuple[list[object], list[object]]:
    """Ausgewaehlte Vorschlaege atomar als lokale Overrides speichern."""
    overrides = _read_overrides()
    updated, created, skipped = create_overrides_from_selected_suggestions(
        overrides=overrides,
        suggestions=suggestions,
        selected_suggestion_ids=selected_suggestion_ids,
        created_by=created_by,
        comment=comment,
    )

    if created:
        _write_overrides_atomic(updated)
        for item in created:
            override_row = item.override_row
            suggestion = item.suggestion
            _append_change_log(
                action="CREATE_FROM_SUGGESTION_BULK",
                override_id=override_row["override_id"],
                override_type=override_row["override_type"],
                changed_by=override_row["created_by"],
                comment=override_row["comment"],
            )
            _append_suggestion_acceptance_log(
                suggestion=suggestion,
                override_id=override_row["override_id"],
                accepted_value=override_row["override_value"],
                accepted_by=override_row["created_by"],
                comment=override_row["comment"],
            )

    return created, skipped


'''
    text = replace_once(
        text,
        "def _render_suggestions(\n",
        helper + "def _render_suggestions(\n",
        "ui batch save helper",
    )

    old_block = '''    st.write(f"Treffer: **{len(filtered)}**")
    st.dataframe(_suggestion_display_table(filtered), use_container_width=True, hide_index=True)

    csv_data = _suggestion_display_table(filtered).to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Vorschlagsliste als CSV herunterladen",
        data=csv_data,
        file_name="systemvorschlaege_phase5b.csv",
        mime="text/csv",
        key="download_manual_override_suggestions",
    )

    selectable = filtered[
        filtered["suggested_value"].fillna("").astype(str).str.strip().ne("")
        | filtered["classification_code"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if selectable.empty:
        st.info("Die gefilterten Einträge sind reine Prüfhinweise ohne vorausgewählten Wert.")
        return

    selectable["_selection_label"] = selectable.apply(
        lambda row: (
            f"{row['suggestion_id']} | {SUGGESTION_TYPE_LABELS.get(_clean(row['suggestion_type']), _clean(row['suggestion_type']))} "
            f"| Lok {_clean(row['loco_no']) or '-'} | Transport {_clean(row['transport_number']) or '-'}"
        ),
        axis=1,
    )
    selected_label = st.selectbox(
        "Vorschlag für Bearbeitung auswählen",
        selectable["_selection_label"].tolist(),
        key="manual_override_suggestion_select",
    )
    selected = selectable[selectable["_selection_label"].eq(selected_label)].iloc[0].to_dict()
    if st.button("Vorschlag in Bearbeitungsmaske übernehmen", type="primary", key="manual_override_suggestion_prefill_button"):
        st.session_state["manual_override_suggestion_prefill"] = selected
        st.success("Vorschlag wurde vorgemerkt. Öffne jetzt den Reiter 'Neue Korrektur'.")
        st.rerun()
'''
    new_block = '''    st.write(f"Treffer: **{len(filtered)}**")

    csv_data = _suggestion_display_table(filtered).to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        "Vorschlagsliste als CSV herunterladen",
        data=csv_data,
        file_name="systemvorschlaege_phase5d.csv",
        mime="text/csv",
        key="download_manual_override_suggestions",
    )

    selectable = filtered[
        filtered["suggested_value"].fillna("").astype(str).str.strip().ne("")
        | filtered["classification_code"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    if selectable.empty:
        st.dataframe(_suggestion_display_table(filtered), use_container_width=True, hide_index=True)
        st.info("Die gefilterten Einträge sind reine Prüfhinweise ohne vorausgewählten Wert.")
        return

    st.markdown("##### Mehrere Vorschläge direkt übernehmen")
    st.caption(
        "Setze links ein Checkmark bei allen Vorschlägen, die du fachlich geprüft hast. "
        "Erst der Speichern-Button erzeugt lokale Overrides. RailCube wird dadurch nicht geändert."
    )
    bulk_table = _suggestion_display_table(selectable).copy()
    bulk_table.insert(0, "Übernehmen", False)
    bulk_table = st.data_editor(
        bulk_table,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        disabled=[column for column in bulk_table.columns if column != "Übernehmen"],
        column_config={
            "Übernehmen": st.column_config.CheckboxColumn(
                "Übernehmen",
                help="Nur fachlich geprüfte Vorschläge markieren.",
                default=False,
            )
        },
        key="manual_override_suggestion_bulk_editor",
    )
    selected_ids = (
        bulk_table.loc[bulk_table["Übernehmen"].fillna(False), "Vorschlag-ID"]
        .fillna("")
        .astype(str)
        .tolist()
    )
    st.write(f"Ausgewählt: **{len(selected_ids)}**")
    bulk_created_by = st.text_input(
        "Bearbeiter für Sammelübernahme",
        value=getpass.getuser(),
        key="manual_override_bulk_created_by",
    )
    bulk_comment = st.text_area(
        "Gemeinsame Begründung für die ausgewählten Vorschläge",
        placeholder="Warum dürfen diese Vorschläge lokal übernommen werden?",
        key="manual_override_bulk_comment",
    )
    bulk_save_col, bulk_rebuild_col = st.columns(2)
    with bulk_save_col:
        save_selected = st.button(
            "Ausgewählte Vorschläge speichern",
            key="manual_override_bulk_save",
            use_container_width=True,
        )
    with bulk_rebuild_col:
        save_selected_and_rebuild = st.button(
            "Speichern und neu prüfen",
            type="primary",
            key="manual_override_bulk_save_rebuild",
            use_container_width=True,
        )

    if save_selected or save_selected_and_rebuild:
        try:
            created, skipped = _save_selected_suggestions(
                suggestions=selectable,
                selected_suggestion_ids=selected_ids,
                created_by=bulk_created_by,
                comment=bulk_comment,
            )
        except ValueError as error:
            st.error(str(error))
            return

        if created:
            st.success(f"{len(created)} Override(s) wurden gespeichert.")
        for skipped_item in skipped:
            st.warning(f"{skipped_item.suggestion_id}: {skipped_item.reason}")

        if save_selected_and_rebuild and created:
            with st.status("Werte werden mit den neuen Overrides sicher neu berechnet ...", expanded=True) as status:
                result = _run_pipeline(Path(ROOT / "scripts" / "run_all.py"))
                if result.returncode == 0:
                    status.update(label="Neuberechnung erfolgreich abgeschlossen.", state="complete", expanded=False)
                    st.session_state["overview_refresh_completed"] = True
                    st.session_state["overview_refresh_completed_at"] = datetime.now().strftime("%d.%m.%Y um %H:%M")
                    st.rerun()
                status.update(label="Neuberechnung fehlgeschlagen.", state="error", expanded=True)
                st.error("Der letzte produktive DuckDB-Stand bleibt erhalten.")
                st.text_area("Fehler der Berechnung", result.stderr, height=220)
                st.text_area("Output der Berechnung", result.stdout, height=220)
        elif created:
            st.info("Bitte anschließend neu berechnen, damit Timeline, Quality Gate und Exporte aktualisiert werden.")

    st.markdown("##### Einzelvorschlag in Bearbeitungsmaske öffnen")
    with st.expander("Einzelvorschlag für detaillierte Prüfung auswählen", expanded=False):
        selectable["_selection_label"] = selectable.apply(
            lambda row: (
                f"{row['suggestion_id']} | {SUGGESTION_TYPE_LABELS.get(_clean(row['suggestion_type']), _clean(row['suggestion_type']))} "
                f"| Lok {_clean(row['loco_no']) or '-'} | Transport {_clean(row['transport_number']) or '-'}"
            ),
            axis=1,
        )
        selected_label = st.selectbox(
            "Vorschlag für Bearbeitung auswählen",
            selectable["_selection_label"].tolist(),
            key="manual_override_suggestion_select",
        )
        selected = selectable[selectable["_selection_label"].eq(selected_label)].iloc[0].to_dict()
        if st.button("Vorschlag in Bearbeitungsmaske übernehmen", key="manual_override_suggestion_prefill_button"):
            st.session_state["manual_override_suggestion_prefill"] = selected
            st.success("Vorschlag wurde vorgemerkt. Öffne jetzt den Reiter 'Neue Korrektur'.")
            st.rerun()
'''
    text = replace_once(text, old_block, new_block, "ui suggestion list bulk selection")
    return text


def load_and_patch(relative: str) -> tuple[bytes | None, bytes, str]:
    path = ROOT / relative
    if relative == BATCH_PATH:
        payload = ROOT / "payload" / BATCH_PATH
        if not payload.exists():
            raise RuntimeError(f"Payload fehlt: {payload}")
        payload_text = payload.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        new_raw = encode_text(payload_text, "\r\n", bom=False)
        old_raw = path.read_bytes() if path.exists() else None
        if old_raw is not None and BATCH_MARKER not in old_raw.decode("utf-8-sig", errors="ignore"):
            raise RuntimeError(
                f"{relative} existiert bereits ohne Phase-5D-Batch-Marker. Lokalen Stand pruefen."
            )
        return old_raw, new_raw, "CRLF"

    if not path.exists():
        raise RuntimeError(f"Projektdatei fehlt: {relative}")
    raw = path.read_bytes()
    text, newline = decode_text(raw, relative)
    patched = patch_ui(text) if relative == UI_PATH else patch_suggestion(text)
    # Projektdateien ohne BOM erhalten; Zeilenumbruchstil bleibt bestehen.
    return raw, encode_text(patched, newline, bom=False), "CRLF" if newline == "\r\n" else "LF"


def create_backup() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = BACKUP_ROOT / f"manual_override_phase5d_{stamp}"
    counter = 1
    while backup_dir.exists():
        backup_dir = BACKUP_ROOT / f"manual_override_phase5d_{stamp}_{counter}"
        counter += 1
    backup_dir.mkdir(parents=True, exist_ok=False)
    return backup_dir


def validate_syntax(paths: list[Path]) -> None:
    for path in paths:
        py_compile.compile(str(path), doraise=True)


def dry_run() -> int:
    print("=" * 72)
    print("Netzentgelt Phase 5D - DRY RUN")
    print("=" * 72)
    for relative in FILES:
        old_raw, new_raw, newline_label = load_and_patch(relative)
        state = "neu" if old_raw is None else ("unveraendert" if old_raw == new_raw else "geaendert")
        print(f"OK  {relative}: {state}; Zeilenumbruch={newline_label}")
    print("")
    print("DRY RUN erfolgreich. Keine Dateien wurden veraendert.")
    return 0


def apply() -> int:
    print("=" * 72)
    print("Netzentgelt Phase 5D - APPLY")
    print("=" * 72)
    prepared: dict[str, tuple[bytes | None, bytes, str]] = {}
    for relative in FILES:
        prepared[relative] = load_and_patch(relative)

    if all(old_raw == new_raw for old_raw, new_raw, _newline_label in prepared.values()):
        validate_syntax([ROOT / relative for relative in FILES])
        print("Phase 5D ist bereits installiert. Keine Dateien wurden veraendert.")
        return 0

    backup_dir = create_backup()
    manifest = {"phase_id": PHASE_ID, "created_at_utc": datetime.now(timezone.utc).isoformat(), "files": []}
    for relative, (old_raw, _new_raw, _newline_label) in prepared.items():
        item = {"relative": relative, "existed": old_raw is not None}
        if old_raw is not None:
            target = backup_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(old_raw)
            item["sha256"] = sha256_bytes(old_raw)
        manifest["files"].append(item)

    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    LATEST_POINTER.write_text(str(backup_dir), encoding="utf-8")

    written_paths: list[Path] = []
    try:
        for relative, (_old_raw, new_raw, newline_label) in prepared.items():
            path = ROOT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(new_raw)
            written_paths.append(path)
            print(f"OK  geschrieben: {relative}; Zeilenumbruch={newline_label}")
        validate_syntax(written_paths)
    except Exception:
        rollback_from(backup_dir)
        raise

    print("")
    print(f"Backup: {backup_dir}")
    print("APPLY erfolgreich. Python-Syntaxpruefung bestanden.")
    return 0


def verify() -> int:
    print("=" * 72)
    print("Netzentgelt Phase 5D - VERIFY")
    print("=" * 72)
    required = {
        UI_PATH: [PHASE_ID, "st.data_editor", "CREATE_FROM_SUGGESTION_BULK", "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS"],
        SUGGESTION_PATH: [PHASE_ID, "_suggest_gap_performing_ru_from_neighbours", "GAP_PERFORMING_RU_FROM_BOTH_NEIGHBOURS"],
        BATCH_PATH: ["NETZENTGELT_MANUAL_OVERRIDE_PHASE5D_BATCH_V1_20260608", "create_overrides_from_selected_suggestions"],
    }
    paths: list[Path] = []
    for relative, markers in required.items():
        path = ROOT / relative
        if not path.exists():
            raise RuntimeError(f"Datei fehlt: {relative}")
        text = path.read_text(encoding="utf-8-sig")
        for marker in markers:
            if marker not in text:
                raise RuntimeError(f"Marker fehlt in {relative}: {marker}")
        paths.append(path)
        print(f"OK  {relative}")
    validate_syntax(paths)
    print("VERIFY erfolgreich. Marker und Python-Syntax sind gueltig.")
    return 0


def rollback_from(backup_dir: Path) -> None:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Backup-Manifest fehlt: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for item in manifest["files"]:
        relative = item["relative"]
        path = ROOT / relative
        if item["existed"]:
            source = backup_dir / relative
            if not source.exists():
                raise RuntimeError(f"Backup-Datei fehlt: {source}")
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path)
            print(f"OK  wiederhergestellt: {relative}")
        elif path.exists():
            path.unlink()
            print(f"OK  entfernt: {relative}")


def rollback() -> int:
    print("=" * 72)
    print("Netzentgelt Phase 5D - ROLLBACK")
    print("=" * 72)
    if not LATEST_POINTER.exists():
        raise RuntimeError("Kein Phase-5D-Backupzeiger gefunden.")
    backup_dir = Path(LATEST_POINTER.read_text(encoding="utf-8").strip())
    rollback_from(backup_dir)
    print("ROLLBACK erfolgreich.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["dry-run", "apply", "verify", "rollback"])
    args = parser.parse_args()
    if args.mode == "dry-run":
        return dry_run()
    if args.mode == "apply":
        return apply()
    if args.mode == "verify":
        return verify()
    return rollback()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"FEHLER: {exc}")
        raise
