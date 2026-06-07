from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

HOTFIX_MARKER = "NETZENTGELT_CANCELLED_HOTFIX_V2_20260607"
BACKUP_POINTER = ".cancelled_hotfix_v2_last_backup.txt"
TARGET_FILES = (
    Path("scripts/run_all.py"),
    Path("scripts/error_rules.py"),
    Path("scripts/export_module.py"),
    Path("app/app.py"),
)

RUN_ALL_HELPER = r'''


def build_cancelled_transport_exclusions(con):
    """
    Stornierte Transporte zentral und auditierbar ausschließen.

    Fachliche Quelle für den Status ist TransportDetail.csv. Dadurch werden
    auch statuslose Bewegungszeilen aus LocomotiveMovement.csv über ihre
    TransportNumber ausgeschlossen. Die Audit-Tabelle enthält zusätzlich
    TransportLastEditDate und TransportLastEditBy aus LocomotiveMovement.csv,
    sofern die Spalten im DataLake-Export vorhanden sind.

    NETZENTGELT_CANCELLED_HOTFIX_V2_20260607
    """
    con.execute("""
        create or replace table cfg_excluded_cancelled_transports (
            transport_number varchar,
            transport_status varchar
        )
    """)

    con.execute("""
        create or replace table audit_excluded_cancelled_transports (
            source_table varchar,
            transport_number varchar,
            transport_status varchar,
            affected_rows bigint,
            first_seen_utc timestamp,
            last_seen_utc timestamp,
            transport_last_edit_date timestamp,
            transport_last_edit_by varchar
        )
    """)

    transport_detail_table = "raw_transportdetail"

    if not table_exists(con, transport_detail_table):
        print(
            "WARNUNG: Keine raw_transportdetail-Tabelle vorhanden. "
            "Cancelled-Transportausschluss bleibt leer."
        )
        return

    transport_detail_columns = columns(con, transport_detail_table)
    transport_number_expr = pick_text(
        transport_detail_columns,
        ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
    )
    transport_status_expr = pick_text(
        transport_detail_columns,
        ["TransportStatus", "Status"],
    )

    if transport_number_expr == "NULL" or transport_status_expr == "NULL":
        print(
            "WARNUNG: TransportDetail.csv enthält keine auswertbare "
            "TransportNumber- oder TransportStatus-Spalte. "
            "Cancelled-Transportausschluss bleibt leer."
        )
        return

    con.execute(f"""
        create or replace table cfg_excluded_cancelled_transports as
        with source_rows as (
            select
                {transport_number_expr} as transport_number,
                {transport_status_expr} as transport_status
            from {qident(transport_detail_table)}
        )
        select
            transport_number,
            string_agg(
                distinct transport_status,
                ' | '
                order by transport_status
            ) as transport_status
        from source_rows
        where transport_number is not null
          and regexp_replace(
                lower(coalesce(transport_status, '')),
                '[^a-z]+',
                '',
                'g'
          ) in ('cancelled', 'canceled')
        group by transport_number
    """)

    audit_selects = []

    for source_table in ["raw_transportdetail", "raw_locomotivemovement"]:
        if not table_exists(con, source_table):
            continue

        source_columns = columns(con, source_table)
        source_transport_number = pick_text(
            source_columns,
            ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
        )

        if source_transport_number == "NULL":
            continue

        first_seen_source = coalesce(
            source_columns,
            [
                "ActualDeparture",
                "LocomotiveActualDeparture",
                "ActualArrival",
                "LocomotiveActualArrival",
                "TransportLastEditDate",
            ],
        )
        last_seen_source = coalesce(
            source_columns,
            [
                "ActualArrival",
                "LocomotiveActualArrival",
                "ActualDeparture",
                "LocomotiveActualDeparture",
                "TransportLastEditDate",
            ],
        )
        transport_last_edit_date = pick_text(
            source_columns,
            ["TransportLastEditDate"],
        )
        transport_last_edit_by = pick_text(
            source_columns,
            ["TransportLastEditBy"],
        )

        first_seen_sql = (
            "null::timestamp"
            if first_seen_source == "NULL"
            else f"try_cast({first_seen_source} as timestamp)"
        )
        last_seen_sql = (
            "null::timestamp"
            if last_seen_source == "NULL"
            else f"try_cast({last_seen_source} as timestamp)"
        )
        last_edit_date_sql = (
            "null::timestamp"
            if transport_last_edit_date == "NULL"
            else f"max(try_cast({transport_last_edit_date} as timestamp))"
        )
        last_edit_by_sql = (
            "null::varchar"
            if transport_last_edit_by == "NULL"
            else (
                "string_agg("
                f"distinct {transport_last_edit_by}, "
                "' | ' "
                f"order by {transport_last_edit_by}"
                f") filter (where {transport_last_edit_by} is not null)"
            )
        )
        source_table_literal = source_table.replace("'", "''")

        audit_selects.append(f"""
            select
                '{source_table_literal}' as source_table,
                {source_transport_number} as transport_number,
                excluded.transport_status,
                count(*) as affected_rows,
                min({first_seen_sql}) as first_seen_utc,
                max({last_seen_sql}) as last_seen_utc,
                {last_edit_date_sql} as transport_last_edit_date,
                {last_edit_by_sql} as transport_last_edit_by
            from {qident(source_table)} source_rows
            join cfg_excluded_cancelled_transports excluded
              on excluded.transport_number = {source_transport_number}
            group by
                {source_transport_number},
                excluded.transport_status
        """)

    if audit_selects:
        con.execute(
            "create or replace table audit_excluded_cancelled_transports as\n"
            + "\nunion all\n".join(audit_selects)
        )

    excluded_transport_count = con.execute(
        "select count(*) from cfg_excluded_cancelled_transports"
    ).fetchone()[0]
    audit_row_count = con.execute(
        "select count(*) from audit_excluded_cancelled_transports"
    ).fetchone()[0]

    print(
        "Cancelled-Transporte ausgeschlossen: "
        f"{excluded_transport_count} Transporte | "
        f"{audit_row_count} Audit-Zeilen."
    )
'''

APP_HELPER = r'''


def load_cancelled_transport_numbers() -> set[str]:
    """
    Stornierte Transporte aus TransportDetail.csv laden.

    Die Streamlit-Rohdatenprüfung verwendet dieselbe zentrale Fachlogik wie
    die DuckDB-Pipeline: TransportStatus = Cancelled oder Canceled wird über
    TransportNumber auf TransportDetail.csv und LocomotiveMovement.csv
    angewendet.

    NETZENTGELT_CANCELLED_HOTFIX_V2_20260607
    """
    transport_detail = read_csv_safe(RAW_DIR / "TransportDetail.csv")

    if transport_detail.empty:
        return set()

    transport_number_col = get_col(
        transport_detail,
        ["TransportNumber", "TransportNo", "TransportId", "TransportID"],
    )
    transport_status_col = get_col(
        transport_detail,
        ["TransportStatus", "Status"],
    )

    if not transport_number_col or not transport_status_col:
        return set()

    normalized_status = (
        transport_detail[transport_status_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z]+", "", regex=True)
    )

    is_cancelled = normalized_status.isin({"cancelled", "canceled"})

    return {
        str(value).strip()
        for value in transport_detail.loc[is_cancelled, transport_number_col]
        .dropna()
        .tolist()
        if str(value).strip()
    }


def build_cancelled_transport_mask(
    source_df: pd.DataFrame,
    transport_number_col: str | None,
    cancelled_transport_numbers: set[str],
) -> pd.Series:
    """Zeilenmaske für zentral ausgeschlossene Transportnummern bilden."""
    if source_df.empty or not transport_number_col or not cancelled_transport_numbers:
        return pd.Series(False, index=source_df.index, dtype=bool)

    return (
        source_df[transport_number_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .isin(cancelled_transport_numbers)
    )
'''


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_newline(data: bytes) -> str:
    return "\r\n" if b"\r\n" in data else "\n"


def decode_source(data: bytes) -> tuple[str, str, bool]:
    newline = detect_newline(data)
    has_bom = data.startswith(b"\xef\xbb\xbf")
    text = data.decode("utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text, newline, has_bom


def encode_source(text: str, newline: str, has_bom: bool) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    rendered = normalized.replace("\n", newline)
    encoded = rendered.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if has_bom else encoded


def compile_python(text: str, label: str) -> None:
    try:
        compile(text, label, "exec")
    except SyntaxError as exc:
        raise RuntimeError(f"Python-Syntaxprüfung fehlgeschlagen für {label}: {exc}") from exc


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: 1, gefunden: {count}. "
            "Lokalen Stand prüfen."
        )
    return text.replace(old, new, 1)


def replace_exact_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(
            f"Patchstelle '{label}' nicht eindeutig gefunden. Erwartet: {expected}, gefunden: {count}. "
            "Lokalen Stand prüfen."
        )
    return text.replace(old, new)


def get_function_section(text: str, function_name: str) -> tuple[int, int, str]:
    lines = text.splitlines(keepends=True)
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith(f"def {function_name}(")
    ]
    if len(starts) != 1:
        raise RuntimeError(
            f"Funktionsabschnitt '{function_name}' nicht eindeutig gefunden. "
            f"Erwartet: 1, gefunden: {len(starts)}."
        )
    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("def "):
            end = index
            break
    return start, end, "".join(lines[start:end])


def replace_function_section(text: str, function_name: str, new_section: str) -> str:
    lines = text.splitlines(keepends=True)
    start, end, _ = get_function_section(text, function_name)
    replacement_lines = new_section.splitlines(keepends=True)
    return "".join(lines[:start] + replacement_lines + lines[end:])


def patch_run_all(text: str) -> str:
    if HOTFIX_MARKER in text:
        return text

    text = replace_once(
        text,
        "def build_loco_events(con):\n",
        RUN_ALL_HELPER + "\n\ndef build_loco_events(con):\n",
        "run_all Helper vor build_loco_events",
    )

    _, _, loco_events = get_function_section(text, "build_loco_events")
    loco_events = replace_exact_count(
        loco_events,
        "            from {qident(source)}\n",
        "            from {qident(source)}\n"
        "            where not exists (\n"
        "                select 1\n"
        "                from cfg_excluded_cancelled_transports excluded\n"
        "                where excluded.transport_number = {transport_number}\n"
        "            )\n",
        2,
        "run_all build_loco_events zentrale Cancelled-Filter",
    )
    text = replace_function_section(text, "build_loco_events", loco_events)

    _, _, routes = get_function_section(text, "build_transport_routes")
    routes = replace_once(
        routes,
        "        where {transport_number} is not null\n"
        "          and {transport_number} <> ''\n",
        "        where {transport_number} is not null\n"
        "          and {transport_number} <> ''\n"
        "          and not exists (\n"
        "                select 1\n"
        "                from cfg_excluded_cancelled_transports excluded\n"
        "                where excluded.transport_number = {transport_number}\n"
        "          )\n",
        "run_all build_transport_routes zentrale Cancelled-Filter",
    )
    text = replace_function_section(text, "build_transport_routes", routes)

    _, _, main_section = get_function_section(text, "main")
    main_section = replace_once(
        main_section,
        "        run_id, imported = import_csvs(con)\n",
        "        run_id, imported = import_csvs(con)\n"
        "        build_cancelled_transport_exclusions(con)\n",
        "run_all main zentraler Cancelled-Ausschluss nach Import",
    )
    main_section = replace_once(
        main_section,
        '            ("raw_import_run", "raw_import_run.csv"),\n',
        '            ("raw_import_run", "raw_import_run.csv"),\n'
        '            ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),\n',
        "run_all main Audit-CSV",
    )
    text = replace_function_section(text, "main", main_section)
    return text


def patch_error_rules(text: str) -> str:
    if HOTFIX_MARKER in text:
        return text

    _, _, section = get_function_section(text, "build_r012_raw_findings")
    section = replace_once(
        section,
        "                    from {qident(td_table)}\n",
        "                    from {qident(td_table)}\n"
        "                    where not exists (\n"
        "                        select 1\n"
        "                        from cfg_excluded_cancelled_transports excluded\n"
        "                        where excluded.transport_number = {td_transport_number}\n"
        "                    )\n",
        "error_rules R012 TransportDetail ohne Cancelled",
    )
    section = replace_once(
        section,
        "                    from {qident(lm_table)}\n",
        "                    from {qident(lm_table)}\n"
        "                    where not exists (\n"
        "                        select 1\n"
        "                        from cfg_excluded_cancelled_transports excluded\n"
        "                        where excluded.transport_number = {lm_transport_number}\n"
        "                    )\n",
        "error_rules R012 LocomotiveMovement ohne Cancelled",
    )
    section = section.replace(
        "    R012 direkt aus den Rohdaten bilden.\n",
        "    R012 direkt aus den Rohdaten bilden.\n\n"
        "    NETZENTGELT_CANCELLED_HOTFIX_V2_20260607: zentral stornierte\n"
        "    Transporte werden vor der Verdichtung vollständig ausgeschlossen.\n",
        1,
    )
    return replace_function_section(text, "build_r012_raw_findings", section)


def patch_export_module(text: str) -> str:
    if HOTFIX_MARKER in text:
        return text

    return replace_once(
        text,
        '    ("raw_import_run", "raw_import_run.csv"),\n',
        '    ("raw_import_run", "raw_import_run.csv"),\n'
        '    ("audit_excluded_cancelled_transports", "audit_excluded_cancelled_transports.csv"),  # NETZENTGELT_CANCELLED_HOTFIX_V2_20260607\n',
        "export_module Audit-CSV registrieren",
    )


def patch_app(text: str) -> str:
    if HOTFIX_MARKER in text:
        return text

    text = replace_once(
        text,
        "def build_no_loco_diagnostics():\n",
        APP_HELPER + "\n\ndef build_no_loco_diagnostics():\n",
        "app Helper vor build_no_loco_diagnostics",
    )

    _, _, diagnostics = get_function_section(text, "build_no_loco_diagnostics")
    diagnostics = replace_once(
        diagnostics,
        "    warnings = []\n",
        "    warnings = []\n"
        "    cancelled_transport_numbers = load_cancelled_transport_numbers()\n",
        "app Diagnostik Cancelled-Liste laden",
    )
    diagnostics = replace_once(
        diagnostics,
        "            & ~has_value(transport_detail[td_loco_col])\n",
        "            & ~has_value(transport_detail[td_loco_col])\n"
        "            & ~build_cancelled_transport_mask(\n"
        "                transport_detail,\n"
        "                td_transport_col,\n"
        "                cancelled_transport_numbers,\n"
        "            )\n",
        "app TransportDetail Diagnose ohne Cancelled",
    )
    diagnostics = replace_once(
        diagnostics,
        "            & (\n"
        "                lm_is_missing_loco_no\n"
        "                | lm_is_technical_loco_no\n"
        "                | lm_is_dummy_type\n"
        "            )\n",
        "            & (\n"
        "                lm_is_missing_loco_no\n"
        "                | lm_is_technical_loco_no\n"
        "                | lm_is_dummy_type\n"
        "            )\n"
        "            & ~build_cancelled_transport_mask(\n"
        "                locomotive_movement,\n"
        "                lm_transport_col,\n"
        "                cancelled_transport_numbers,\n"
        "            )\n",
        "app LocomotiveMovement Diagnose ohne Cancelled",
    )
    return replace_function_section(text, "build_no_loco_diagnostics", diagnostics)


PATCHERS = {
    Path("scripts/run_all.py"): patch_run_all,
    Path("scripts/error_rules.py"): patch_error_rules,
    Path("scripts/export_module.py"): patch_export_module,
    Path("app/app.py"): patch_app,
}


def project_root() -> Path:
    return Path(__file__).resolve().parent


def load_and_patch(root: Path) -> dict[Path, bytes]:
    patched: dict[Path, bytes] = {}
    for relative in TARGET_FILES:
        path = root / relative
        if not path.exists():
            raise RuntimeError(f"Pflichtdatei fehlt: {relative}")
        raw = path.read_bytes()
        text, newline, has_bom = decode_source(raw)
        patched_text = PATCHERS[relative](text)
        compile_python(patched_text, str(relative))
        patched[relative] = encode_source(patched_text, newline, has_bom)
    return patched


def verify_semantic_markers(patched: dict[Path, bytes]) -> None:
    decoded = {
        relative: decode_source(data)[0]
        for relative, data in patched.items()
    }

    required_checks = {
        Path("scripts/run_all.py"): [
            "def build_cancelled_transport_exclusions(con):",
            "cfg_excluded_cancelled_transports",
            "audit_excluded_cancelled_transports",
            "TransportLastEditDate",
            "TransportLastEditBy",
            "build_cancelled_transport_exclusions(con)",
        ],
        Path("scripts/error_rules.py"): [
            HOTFIX_MARKER,
            "from cfg_excluded_cancelled_transports excluded",
        ],
        Path("scripts/export_module.py"): [
            HOTFIX_MARKER,
            'audit_excluded_cancelled_transports.csv',
        ],
        Path("app/app.py"): [
            "def load_cancelled_transport_numbers() -> set[str]:",
            "def build_cancelled_transport_mask(",
            "cancelled_transport_numbers = load_cancelled_transport_numbers()",
        ],
    }

    for relative, markers in required_checks.items():
        text = decoded[relative]
        for marker in markers:
            if marker not in text:
                raise RuntimeError(
                    f"Semantische Prüfung fehlgeschlagen: {relative} enthält Marker nicht: {marker}"
                )

    run_all = decoded[Path("scripts/run_all.py")]
    if run_all.count("from cfg_excluded_cancelled_transports excluded") < 3:
        raise RuntimeError(
            "Semantische Prüfung fehlgeschlagen: zentrale Filter fehlen in Timeline oder Routenerkennung."
        )

    error_rules = decoded[Path("scripts/error_rules.py")]
    if error_rules.count("from cfg_excluded_cancelled_transports excluded") != 2:
        raise RuntimeError(
            "Semantische Prüfung fehlgeschlagen: R012 muss exakt zwei zentrale Filter enthalten."
        )


def make_backup(root: Path) -> Path:
    backup_dir = root / ".patch_backups" / (
        "netzentgelt_cancelled_hotfix_v2_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    manifest = {"hotfix": HOTFIX_MARKER, "files": {}}

    for relative in TARGET_FILES:
        source = root / relative
        target = backup_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        target.write_bytes(raw)
        manifest["files"][str(relative).replace("\\", "/")] = {
            "sha256": sha256_bytes(raw),
            "newline": "CRLF" if detect_newline(raw) == "\r\n" else "LF",
        }

    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / BACKUP_POINTER).write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def restore_backup(root: Path, backup_dir: Path) -> None:
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Backup-Manifest fehlt: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for relative_text, metadata in manifest["files"].items():
        relative = Path(relative_text)
        source = backup_dir / relative
        target = root / relative
        raw = source.read_bytes()
        if sha256_bytes(raw) != metadata["sha256"]:
            raise RuntimeError(f"Backup-Prüfsumme ungültig: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    print(f"Rollback erfolgreich aus Backup: {backup_dir}")


def dry_run(root: Path) -> None:
    before = {
        relative: sha256_bytes((root / relative).read_bytes())
        for relative in TARGET_FILES
    }
    patched = load_and_patch(root)
    verify_semantic_markers(patched)
    after = {
        relative: sha256_bytes((root / relative).read_bytes())
        for relative in TARGET_FILES
    }
    if before != after:
        raise RuntimeError("Dry-Run hat Dateien verändert. Sicherheitsabbruch.")

    changed = [
        str(relative).replace("\\", "/")
        for relative in TARGET_FILES
        if patched[relative] != (root / relative).read_bytes()
    ]
    print("Dry-Run erfolgreich. Keine Dateien wurden verändert.")
    print("Geplante Änderungen:")
    for item in changed:
        print(f"  - {item}")


def apply(root: Path) -> None:
    patched = load_and_patch(root)
    verify_semantic_markers(patched)

    changed = [
        relative
        for relative in TARGET_FILES
        if patched[relative] != (root / relative).read_bytes()
    ]
    if not changed:
        print("Hotfix ist bereits vollständig enthalten. Keine Änderung erforderlich.")
        return

    backup_dir = make_backup(root)
    try:
        for relative in changed:
            (root / relative).write_bytes(patched[relative])

        # Abschließende Syntax- und Markerprüfung direkt gegen die geschriebenen Dateien.
        persisted = load_and_patch(root)
        verify_semantic_markers(persisted)
    except Exception:
        restore_backup(root, backup_dir)
        raise

    print(f"Hotfix erfolgreich angewendet. Backup: {backup_dir}")
    print("Geänderte Dateien:")
    for relative in changed:
        print(f"  - {relative.as_posix()}")


def rollback(root: Path, backup: str | None) -> None:
    if backup:
        backup_dir = Path(backup)
        if not backup_dir.is_absolute():
            backup_dir = root / backup_dir
    else:
        pointer = root / BACKUP_POINTER
        if not pointer.exists():
            raise RuntimeError(
                "Kein letztes Backup registriert. Bitte --backup <Pfad> angeben."
            )
        backup_dir = Path(pointer.read_text(encoding="utf-8").strip())

    restore_backup(root, backup_dir)


def self_test() -> None:
    """Installer-Sicherheit mit CRLF-Fixture, Apply, Syntaxprüfung und Rollback testen."""
    with TemporaryDirectory(prefix="netzentgelt_cancelled_hotfix_v2_") as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir(parents=True)
        (root / "app").mkdir(parents=True)

        fixture_run_all = '''from pathlib import Path\n\ndef table_exists(con, table):\n    return True\n\ndef columns(con, table):\n    return []\n\ndef pick_text(cols, candidates, fallback="NULL"):\n    return fallback\n\ndef coalesce(cols, candidates):\n    return "NULL"\n\ndef qident(name):\n    return name\n\ndef import_csvs(con):\n    return "RUN", []\n\ndef build_loco_events(con):\n    source = "raw_locomotivemovement"\n    transport_number = "TransportNumber"\n    con.execute(f"""\n        create or replace table stg_loco_events as\n        with base as (\n            select *\n            from {qident(source)}\n        ) select * from base\n    """)\n    con.execute(f"""\n        create or replace table stg_loco_events_skipped as\n        with base as (\n            select *\n            from {qident(source)}\n        ) select * from base\n    """)\n\ndef sql_lit(value):\n    return repr(value)\n\ndef build_transport_routes(con, home_country="DE"):\n    source = "raw_transportdetail"\n    transport_number = "TransportNumber"\n    con.execute(f"""\n        select *\n        from {qident(source)}\n        where {transport_number} is not null\n          and {transport_number} <> ''\n    """)\n\ndef main():\n    con = object()\n    if True:\n        run_id, imported = import_csvs(con)\n        for table, name in [\n            ("raw_import_run", "raw_import_run.csv"),\n        ]:\n            pass\n'''
        fixture_error_rules = '''def build_r012_raw_findings(con, run_id, error_cutoff_utc):\n    """\n    R012 direkt aus den Rohdaten bilden.\n    """\n    td_table = "raw_transportdetail"\n    td_transport_number = "TransportNumber"\n    con.execute(f"""\n                    from {qident(td_table)}\n    """)\n    lm_table = "raw_locomotivemovement"\n    lm_transport_number = "TransportNumber"\n    con.execute(f"""\n                    from {qident(lm_table)}\n    """)\n\ndef qident(value):\n    return value\n'''
        fixture_export_module = '''AUDIT_CSV_EXPORTS = [\n    ("raw_import_run", "raw_import_run.csv"),\n]\n'''
        fixture_app = '''from pathlib import Path\nimport pandas as pd\nRAW_DIR = Path(".")\n\ndef read_csv_safe(path):\n    return pd.DataFrame()\n\ndef get_col(df, candidates):\n    return None\n\ndef has_value(series):\n    return series.notna()\n\ndef build_no_loco_diagnostics():\n    warnings = []\n    transport_detail = pd.DataFrame()\n    td_loco_col = "loco"\n    td_transport_col = "transport"\n    td_is_de_relevant = pd.Series(dtype=bool)\n    td_is_train_movement = pd.Series(dtype=bool)\n    td_is_at_least_one_day_old = pd.Series(dtype=bool)\n    td_mask = (\n            td_is_de_relevant\n            & td_is_train_movement\n            & td_is_at_least_one_day_old\n            & ~has_value(transport_detail[td_loco_col])\n        )\n    locomotive_movement = pd.DataFrame()\n    lm_transport_col = "transport"\n    lm_is_de_relevant = pd.Series(dtype=bool)\n    lm_is_at_least_one_day_old = pd.Series(dtype=bool)\n    lm_is_missing_loco_no = pd.Series(dtype=bool)\n    lm_is_technical_loco_no = pd.Series(dtype=bool)\n    lm_is_dummy_type = pd.Series(dtype=bool)\n    lm_mask = (\n            lm_is_de_relevant\n            & lm_is_at_least_one_day_old\n            & (\n                lm_is_missing_loco_no\n                | lm_is_technical_loco_no\n                | lm_is_dummy_type\n            )\n        )\n'''

        fixtures = {
            Path("scripts/run_all.py"): fixture_run_all,
            Path("scripts/error_rules.py"): fixture_error_rules,
            Path("scripts/export_module.py"): fixture_export_module,
            Path("app/app.py"): fixture_app,
        }

        for relative, content in fixtures.items():
            (root / relative).write_bytes(content.replace("\n", "\r\n").encode("utf-8"))

        originals = {relative: (root / relative).read_bytes() for relative in TARGET_FILES}
        dry_run(root)
        apply(root)

        for relative in TARGET_FILES:
            raw = (root / relative).read_bytes()
            if b"\r\n" not in raw:
                raise RuntimeError(f"CRLF-Selbsttest fehlgeschlagen: {relative}")
            text, _, _ = decode_source(raw)
            compile_python(text, str(relative))

        rollback(root, None)
        for relative in TARGET_FILES:
            if (root / relative).read_bytes() != originals[relative]:
                raise RuntimeError(f"Rollback-Selbsttest fehlgeschlagen: {relative}")

    print("Installer-Selbsttest erfolgreich: Dry-Run, Apply, Syntax, CRLF und Rollback geprüft.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Netzentgelt Cancelled-Hotfix V2")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--dry-run", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", action="store_true")
    action.add_argument("--self-test", action="store_true")
    parser.add_argument("--backup", help="Optionaler Backup-Pfad für Rollback")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = project_root()

    if args.self_test:
        self_test()
        return 0
    if args.dry_run:
        dry_run(root)
        return 0
    if args.apply:
        apply(root)
        return 0
    if args.rollback:
        rollback(root, args.backup)
        return 0

    raise RuntimeError("Keine Aktion gewählt.")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"FEHLER: {exc}")
        raise
