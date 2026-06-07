from __future__ import annotations

import argparse
import datetime as dt
import py_compile
import shutil
from pathlib import Path

MARKER = "NETZENTGELT_QUALITY_GATE_PHASE2_V1_20260607"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload" / "quality_gate_module.py"
TARGETS = [
    ROOT / "scripts" / "run_all.py",
    ROOT / "scripts" / "export_module.py",
    ROOT / "app" / "app.py",
]
NEW_MODULE_TARGET = ROOT / "scripts" / "quality_gate_module.py"
BACKUP_ROOT = ROOT / ".patch_backups"
LAST_BACKUP_FILE = ROOT / ".quality_gate_phase2_last_backup.txt"


def read_text_preserve_bom(path: Path) -> tuple[str, bool, str]:
    """Datei lesen, CRLF/LF normalisieren und ursprünglichen Stil merken."""
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    newline_style = "\r\n" if "\r\n" in decoded else "\n"
    normalized = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalized, has_bom, newline_style


def write_text_preserve_bom(
    path: Path,
    text: str,
    has_bom: bool,
    newline_style: str,
) -> None:
    """Normalisierten Text wieder mit ursprünglichem Zeilenumbruch schreiben."""
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
            "Lokalen Stand prüfen und bei Bedarf zuerst pushen."
        )
    return text.replace(old, new, 1)


def insert_after_once(text: str, anchor: str, addition: str, label: str) -> str:
    return replace_once(text, anchor, anchor + addition, label)


def patch_run_all(text: str) -> str:
    if MARKER in text:
        return text

    text = insert_after_once(
        text,
        "from export_module import build_export_tables\n",
        "from quality_gate_module import build_quality_gate_tables, refresh_reconciliation_table\n",
        "run_all import quality_gate_module",
    )

    text = replace_once(
        text,
        """        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)\n        build_exports(con)\n""",
        (
            "        build_findings(con, run_id, home_country_iso=HOME_COUNTRY_ISO)\n"
            "        build_quality_gate_tables(con, run_id)\n"
            "        build_exports(con)\n"
            "        refresh_reconciliation_table(con, run_id)\n"
            f"        # {MARKER}: 15-Minuten-Deckung, Export-Gate und Reconciliation\n"
        ),
        "run_all quality gate calls",
    )

    text = insert_after_once(
        text,
        '            ("dq_run_metadata", "dq_run_metadata.csv"),\n',
        """            ("core_loco_day_coverage", "core_loco_day_coverage.csv"),\n            ("dq_export_gate", "dq_export_gate.csv"),\n            ("dq_export_gate_ru", "dq_export_gate_ru.csv"),\n            ("dq_global_export_blockers", "dq_global_export_blockers.csv"),\n            ("export_excluded_rows", "export_excluded_rows.csv"),\n            ("dq_reconciliation", "dq_reconciliation.csv"),\n            ("dq_operational_kpis", "dq_operational_kpis.csv"),\n""",
        "run_all audit csv exports",
    )

    quality_print = """        quality_gate_summary = con.execute(\"\"\"\n            select\n                count(*) filter (where gate_status = 'READY') as ready_days,\n                count(*) filter (where gate_status = 'WARNING') as warning_days,\n                count(*) filter (where gate_status = 'BLOCKED') as blocked_days\n            from dq_export_gate\n        \"\"\").fetchone()\n\n        print(\n            \"Quality Gate Lok-Tage: \"\n            f\"READY={quality_gate_summary[0]} | \"\n            f\"WARNING={quality_gate_summary[1]} | \"\n            f\"BLOCKED={quality_gate_summary[2]}\"\n        )\n\n        # __MARKER__\n\n""".replace("__MARKER__", MARKER)

    text = insert_after_once(
        text,
        "        # 6. Kennzahlen des erfolgreich berechneten Laufs ermitteln.\n",
        quality_print,
        "run_all quality summary",
    )
    return text


def patch_export_module(text: str) -> str:
    if MARKER in text:
        return text

    old_build = '''def build_export_tables(con) -> None:
    """
    Bestehende fachliche CSV-Exporttabellen in DuckDB neu aufbauen.

    Diese Tabellen bleiben für Audit und Rückwärtskompatibilität erhalten.
    Der neue RU-bezogene XLSX-Export wird dynamisch über
    ``build_nutzungsmeldung_xlsx()`` erzeugt.
    """
    con.execute(
        """
        create or replace table export_zuordnungen as
        select
            tfze_or_tens as "TfzE oder tEns*",
            period_start_utc as "Beginn der Zuordnung*",
            period_end_utc as "Ende der Zuordnung",
            user_vens as "Nutzer-vEns*",
            performing_ru_marktpartner_id as "Marktpartner ID für Nutzungsüberlassung"
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and export_ready = true
        """
    )

    con.execute(
        """
        create or replace table export_nutzungsmeldung as
        select
            tfze_or_tens as "TfzE oder tEns*",
            period_start_utc as "Beginn der Nutzung*",
            period_end_utc as "Ende der Nutzung",
            coalesce(nullif(user_vens, ''), performing_ru) as "Nutzer-vEns*",
            coalesce(nullif(holder_market_partner_id, ''), holder_name) as "Marktpartner ID für Nutzungsüberlassung*",
            '' as "Übernahmeanfrage oder Übergabemeldung?"
        from core_loco_timeline
        where row_type = 'MOVEMENT'
          and report_scope = 'IN_REPORT'
          and export_ready = true
        """
    )
'''

    new_build = '''def build_export_tables(con) -> None:
    """
    Fachliche CSV-Exporttabellen mit zentralem Export-Gate aufbauen.

    Bewegungen werden nur exportiert, wenn die Zeile selbst exportfähig ist,
    der zugehörige Lok-Tag nicht blockiert ist und am Kalendertag kein globaler
    Export-Blocker wie R012 vorliegt.
    """
    gate_filter = """
          and not exists (
                select 1
                from dq_export_gate_ru g
                where g.loco_no = c.loco_no
                  and g.performing_ru is not distinct from c.performing_ru
                  and g.coverage_date = cast(
                        coalesce(
                            c.actual_departure_ts,
                            c.period_start_utc,
                            c.sequence_ts,
                            c.actual_arrival_ts,
                            c.period_end_utc
                        ) as date
                  )
                  and g.gate_status = 'BLOCKED'
          )
          and not exists (
                select 1
                from dq_global_export_blockers b
                where b.blocker_date = cast(
                        coalesce(
                            c.actual_departure_ts,
                            c.period_start_utc,
                            c.sequence_ts,
                            c.actual_arrival_ts,
                            c.period_end_utc
                        ) as date
                )
                  and b.gate_status = 'BLOCKED'
          )
    """

    con.execute(
        f"""
        create or replace table export_zuordnungen as
        select
            c.tfze_or_tens as "TfzE oder tEns*",
            c.period_start_utc as "Beginn der Zuordnung*",
            c.period_end_utc as "Ende der Zuordnung",
            coalesce(nullif(c.user_vens, ''), c.performing_ru) as "Nutzer-vEns*",
            coalesce(nullif(c.holder_market_partner_id, ''), c.holder_name) as "Marktpartner ID für Nutzungsüberlassung"
        from core_loco_timeline c
        where c.row_type = 'MOVEMENT'
          and c.report_scope = 'IN_REPORT'
          and c.export_ready = true
          {gate_filter}
        """
    )

    con.execute(
        f"""
        create or replace table export_nutzungsmeldung as
        select
            c.tfze_or_tens as "TfzE oder tEns*",
            c.period_start_utc as "Beginn der Nutzung*",
            c.period_end_utc as "Ende der Nutzung",
            coalesce(nullif(c.user_vens, ''), c.performing_ru) as "Nutzer-vEns*",
            coalesce(nullif(c.holder_market_partner_id, ''), c.holder_name) as "Marktpartner ID für Nutzungsüberlassung*",
            '' as "Übernahmeanfrage oder Übergabemeldung?"
        from core_loco_timeline c
        where c.row_type = 'MOVEMENT'
          and c.report_scope = 'IN_REPORT'
          and c.export_ready = true
          {gate_filter}
        """
    )

    # __MARKER__
'''.replace("__MARKER__", MARKER)

    text = replace_once(text, old_build, new_build, "export_module build_export_tables")

    text = insert_after_once(
        text,
        '    ("dq_run_metadata", "dq_run_metadata.csv"),\n',
        '''    ("core_loco_day_coverage", "core_loco_day_coverage.csv"),
    ("dq_export_gate", "dq_export_gate.csv"),
    ("dq_export_gate_ru", "dq_export_gate_ru.csv"),
    ("dq_global_export_blockers", "dq_global_export_blockers.csv"),
    ("export_excluded_rows", "export_excluded_rows.csv"),
    ("dq_reconciliation", "dq_reconciliation.csv"),
    ("dq_operational_kpis", "dq_operational_kpis.csv"),
''',
        "export_module audit csv exports",
    )

    helper_anchor = "\ndef _fetch_usage_segments(\n"
    helper = r'''

def _assert_export_gate_ready(
    con,
    performing_ru_values: Sequence[str],
    date_from: date,
    date_to: date,
) -> None:
    """Dynamischen XLSX-Export bei blockierten Lok-Tagen sicher verhindern."""
    required_tables = [
        "dq_export_gate_ru",
        "dq_global_export_blockers",
    ]

    missing_tables = [
        table_name
        for table_name in required_tables
        if not table_exists(con, table_name)
    ]

    if missing_tables:
        raise RuntimeError(
            "Export-Gate fehlt. Pipeline mit der Phase-2-Erweiterung neu ausführen. "
            "Fehlende Tabellen: " + ", ".join(missing_tables)
        )

    ru_values = _as_ru_tuple(performing_ru_values)
    placeholders = _placeholders(ru_values)

    local_blockers = con.execute(
        f"""
        select
            count(*) as blocker_count,
            string_agg(
                distinct cast(coverage_date as varchar) || ': ' || loco_no,
                ', '
            ) as examples
        from dq_export_gate_ru
        where performing_ru in ({placeholders})
          and coverage_date >= ?
          and coverage_date <= ?
          and gate_status = 'BLOCKED'
        """,
        [*ru_values, date_from, date_to],
    ).fetchone()

    global_blockers = con.execute(
        """
        select
            count(*) as blocker_count,
            string_agg(
                distinct cast(blocker_date as varchar) || ': ' || rule_id,
                ', '
            ) as examples
        from dq_global_export_blockers
        where blocker_date >= ?
          and blocker_date <= ?
          and gate_status = 'BLOCKED'
        """,
        [date_from, date_to],
    ).fetchone()

    local_count = int(local_blockers[0] or 0)
    global_count = int(global_blockers[0] or 0)

    if local_count > 0 or global_count > 0:
        details = []

        if local_count > 0:
            details.append(
                f"Blockierte Lok-Tage für gewählte RU: {local_count}. "
                f"Beispiele: {local_blockers[1] or '-'}"
            )

        if global_count > 0:
            details.append(
                f"Globale Blocker im Zeitraum: {global_count}. "
                f"Beispiele: {global_blockers[1] or '-'}"
            )

        raise RuntimeError(
            "Export ist gesperrt, bis die blockierenden Prüffälle geklärt sind. "
            + " | ".join(details)
        )
'''
    text = replace_once(text, helper_anchor, helper + helper_anchor, "export_module assert helper")

    text = replace_once(
        text,
        '''    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)
    normalized_performing_ru_sql = _normalize_company_name_sql("s.performing_ru")
''',
        '''    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)
    _assert_export_gate_ready(con, ru_values, date_from, date_to)
    normalized_performing_ru_sql = _normalize_company_name_sql("s.performing_ru")
''',
        "usage XLSX gate call",
    )

    text = replace_once(
        text,
        '''    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)

    rows = con.execute(
''',
        '''    window_start, window_end_exclusive = _to_day_bounds(date_from, date_to)
    _assert_export_gate_ready(con, ru_values, date_from, date_to)

    rows = con.execute(
''',
        "events XLSX gate call",
    )
    return text


def patch_app(text: str) -> str:
    if MARKER in text:
        return text

    text = insert_after_once(
        text,
        'run_path = EXPORT_DIR / "raw_import_run.csv"\n',
        '''coverage_path = EXPORT_DIR / "core_loco_day_coverage.csv"
export_gate_path = EXPORT_DIR / "dq_export_gate.csv"
export_gate_ru_path = EXPORT_DIR / "dq_export_gate_ru.csv"
global_blockers_path = EXPORT_DIR / "dq_global_export_blockers.csv"
reconciliation_path = EXPORT_DIR / "dq_reconciliation.csv"
operational_kpis_path = EXPORT_DIR / "dq_operational_kpis.csv"
excluded_export_rows_path = EXPORT_DIR / "export_excluded_rows.csv"
''',
        "app quality paths",
    )

    text = insert_after_once(
        text,
        "runs = read_csv_safe(run_path)\n",
        '''coverage = read_csv_safe(coverage_path)
export_gate = read_csv_safe(export_gate_path)
export_gate_ru = read_csv_safe(export_gate_ru_path)
global_export_blockers = read_csv_safe(global_blockers_path)
reconciliation = read_csv_safe(reconciliation_path)
operational_kpis = read_csv_safe(operational_kpis_path)
excluded_export_rows = read_csv_safe(excluded_export_rows_path)
''',
        "app quality csv reads",
    )

    overview_anchor = '''    st.caption(
        "Errors sind DE-relevante Prüffälle, die fachlich bearbeitet werden müssen. "
        "Infos dokumentieren DE-relevante Hinweise, blockieren die weitere Verarbeitung aber nicht."
    )

    st.divider()

'''

    overview_addition = '''    # ==================================================
    # __MARKER__: operative Betriebsampel und Export-Gate
    # ==================================================
    st.subheader("Betriebsampel & Export-Gate")

    if operational_kpis.empty:
        st.info(
            "Die Phase-2-KPI-Tabellen wurden noch nicht erzeugt. "
            "Bitte die Pipeline erneut ausführen."
        )
    else:
        gate_status_col = get_col(export_gate, ["gate_status", "Gate_Status"])

        if gate_status_col:
            normalized_gate_status = (
                export_gate[gate_status_col]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )

            ready_days = int((normalized_gate_status == "READY").sum())
            warning_days = int((normalized_gate_status == "WARNING").sum())
            blocked_days = int((normalized_gate_status == "BLOCKED").sum())
        else:
            ready_days = 0
            warning_days = 0
            blocked_days = 0

        global_blocker_count = len(global_export_blockers)
        excluded_row_count = len(excluded_export_rows)

        gate_col_1, gate_col_2, gate_col_3, gate_col_4, gate_col_5 = st.columns(5)

        with gate_col_1:
            st.metric("Lok-Tage READY", ready_days)

        with gate_col_2:
            st.metric("Lok-Tage WARNING", warning_days)

        with gate_col_3:
            st.metric("Lok-Tage BLOCKED", blocked_days)

        with gate_col_4:
            st.metric("Globale Blocker", global_blocker_count)

        with gate_col_5:
            st.metric("Ausgeschlossene Exportzeilen", excluded_row_count)

        if blocked_days > 0 or global_blocker_count > 0:
            st.error(
                "Mindestens ein Export ist gesperrt. Öffne die Fehlerqueue sowie "
                "dq_export_gate.csv und dq_global_export_blockers.csv für die Detailprüfung."
            )
        elif warning_days > 0:
            st.warning(
                "Es bestehen Warnungen, aber keine blockierenden Lok-Tage. "
                "Die Warnungen vor dem Export fachlich prüfen."
            )
        else:
            st.success("Export-Gate ist vollständig grün.")

        st.dataframe(
            operational_kpis,
            use_container_width=True,
            hide_index=True,
        )

    if not reconciliation.empty:
        st.subheader("Reconciliation des letzten Pipeline-Laufs")
        st.dataframe(
            reconciliation,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

'''.replace("__MARKER__", MARKER)

    text = replace_once(
        text,
        overview_anchor,
        overview_anchor + overview_addition,
        "app overview quality gate block",
    )
    return text


def backup_files(paths: list[Path]) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"netzentgelt_quality_gate_phase2_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for path in paths:
        destination = backup_dir / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    if NEW_MODULE_TARGET.exists():
        destination = backup_dir / NEW_MODULE_TARGET.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEW_MODULE_TARGET, destination)

    LAST_BACKUP_FILE.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def compile_targets(paths: list[Path]) -> None:
    for path in paths:
        py_compile.compile(str(path), doraise=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    for path in TARGETS:
        require_path(path)
    require_path(PAYLOAD)

    originals = {path: read_text_preserve_bom(path) for path in TARGETS}

    patched = {
        TARGETS[0]: patch_run_all(originals[TARGETS[0]][0]),
        TARGETS[1]: patch_export_module(originals[TARGETS[1]][0]),
        TARGETS[2]: patch_app(originals[TARGETS[2]][0]),
    }

    print("Phase-2-Patch wurde gegen den lokalen Stand validiert.")
    print("Geplante Änderungen:")
    for path in [*TARGETS, NEW_MODULE_TARGET]:
        print(f"- {path.relative_to(ROOT)}")

    if args.dry_run:
        print("DRY RUN erfolgreich. Es wurden keine Dateien verändert.")
        return 0

    backup_dir = backup_files(TARGETS)
    print(f"Backup erstellt: {backup_dir}")

    try:
        for path, text in patched.items():
            write_text_preserve_bom(
                path,
                text,
                originals[path][1],
                originals[path][2],
            )

        shutil.copy2(PAYLOAD, NEW_MODULE_TARGET)
        compile_targets([*TARGETS, NEW_MODULE_TARGET])

    except Exception:
        print("Fehler beim Patchen. Stelle Backup automatisch wieder her.")
        for source in backup_dir.rglob("*"):
            if source.is_file():
                destination = ROOT / source.relative_to(backup_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        raise

    print("Phase-2-Patch erfolgreich angewendet und syntaktisch validiert.")
    print("Nächster Schritt: 03_RUN_FULL_IMPORT_AND_PIPELINE_PHASE2.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
