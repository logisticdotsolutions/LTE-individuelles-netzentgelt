from __future__ import annotations

import argparse
import ast
import datetime as dt
import os
from pathlib import Path
import re
import shutil
import sys

PATCH_ID = "NETZENTGELT_HARDENING_V1_20260607"
TARGET_FILES = [
    Path("scripts/download_blob_data.py"),
    Path("scripts/run_all.py"),
    Path("scripts/error_rules.py"),
    Path("scripts/export_module.py"),
    Path("app/app.py"),
]


class PatchError(RuntimeError):
    pass


def replace_once(text: str, old: str, new: str, label: str) -> str:
    """Replace an exact anchor once. Already patched anchors are accepted."""
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise PatchError(
            f"[{label}] Erwartete Codestelle nicht eindeutig gefunden. "
            f"Treffer: {count}. Datei wurde nicht verändert."
        )
    return text.replace(old, new, 1)


def regex_replace_once(text: str, pattern: str, replacement: str, label: str) -> str:
    """Replace one regex block. A patch marker allows idempotent reruns."""
    if PATCH_ID in text and label in text:
        return text
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise PatchError(
            f"[{label}] Erwarteter Codeblock nicht eindeutig gefunden. "
            f"Treffer: {count}. Datei wurde nicht verändert."
        )
    return updated


def transform_download_blob_data(text: str) -> str:
    text = replace_once(
        text,
        "import csv\nimport os\n",
        "import csv\nimport json\nimport os\nimport shutil\n",
        "download imports",
    )
    text = replace_once(
        text,
        'DOWNLOAD_DIR = ROOT / "data" / "00_raw"\nTEMP_ROOT_DIR = DOWNLOAD_DIR / "_tmp_blob_download"\n',
        'DOWNLOAD_DIR = ROOT / "data" / "00_raw"\nTEMP_ROOT_DIR = DOWNLOAD_DIR / "_tmp_blob_download"\nSNAPSHOT_MANIFEST_PATH = DOWNLOAD_DIR / "raw_import_manifest.json"\n# NETZENTGELT_HARDENING_V1_20260607: gemeinsamer Rohdaten-Snapshot\n',
        "download manifest constant",
    )

    helper_block = r'''

def write_snapshot_manifest(
    snapshot_at_utc: datetime,
    summary_rows: list[tuple],
) -> None:
    """Auditierbaren Snapshot-Zeitpunkt nach erfolgreichem Gesamtdownload schreiben."""
    payload = {
        "schema_version": 1,
        "snapshot_at_utc": snapshot_at_utc.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "committed_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "files": [
            {
                "file_name": row[0],
                "mode": row[1],
                "timestamp_column": row[2],
                "max_timestamp": row[3],
                "cutoff_timestamp": row[4],
                "status": row[5],
            }
            for row in summary_rows
        ],
    }

    manifest_temp = SNAPSHOT_MANIFEST_PATH.with_suffix(".json.tmp")
    manifest_temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    replace_file_safely(manifest_temp, SNAPSHOT_MANIFEST_PATH)


def commit_snapshot_safely(
    pending_replacements: list[tuple[Path, Path]],
    snapshot_at_utc: datetime,
    summary_rows: list[tuple],
    run_temp_dir: Path,
) -> None:
    """
    Alle validierten Dateien gemeinsam übernehmen.

    Falls das Ersetzen einer Datei fehlschlägt, werden bereits ersetzte Dateien
    auf den vorherigen lokalen Stand zurückgesetzt. Erst danach wird das
    Snapshot-Manifest geschrieben.
    """
    backup_dir = run_temp_dir / "previous_snapshot"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backups: dict[Path, Path] = {}
    replaced_targets: list[Path] = []

    try:
        for _, target_path in pending_replacements:
            if target_path.exists():
                backup_path = backup_dir / target_path.name
                shutil.copy2(target_path, backup_path)
                backups[target_path] = backup_path

        for source_path, target_path in pending_replacements:
            replace_file_safely(source_path, target_path)
            replaced_targets.append(target_path)

        write_snapshot_manifest(
            snapshot_at_utc=snapshot_at_utc,
            summary_rows=summary_rows,
        )

    except Exception:
        for target_path in reversed(replaced_targets):
            backup_path = backups.get(target_path)

            if backup_path is not None and backup_path.exists():
                shutil.copy2(backup_path, target_path)
            elif target_path.exists():
                target_path.unlink()

        raise

'''
    text = replace_once(
        text,
        "\ndef remove_obsolete_local_files() -> None:\n",
        helper_block + "\ndef remove_obsolete_local_files() -> None:\n",
        "download snapshot helpers",
    )
    text = replace_once(
        text,
        "    summary_rows = []\n\n    # Jeder Importlauf erhält einen eigenen temporären Unterordner.\n",
        "    summary_rows = []\n    snapshot_at_utc = datetime.now(timezone.utc)\n\n    # Jeder Importlauf erhält einen eigenen temporären Unterordner.\n",
        "download snapshot timestamp",
    )
    text = replace_once(
        text,
        "        run_temp_dir = Path(run_temp_dir_text)\n\n        try:\n",
        "        run_temp_dir = Path(run_temp_dir_text)\n        pending_replacements: list[tuple[Path, Path]] = []\n\n        try:\n",
        "download pending list",
    )
    text = replace_once(
        text,
        "                    replace_file_safely(\n                        source_path=temp_full_download,\n                        target_path=local_target,\n                    )\n",
        "                    pending_replacements.append((\n                        temp_full_download,\n                        local_target,\n                    ))\n",
        "download defer full replace",
    )
    text = replace_once(
        text,
        "                replace_file_safely(\n                    source_path=temp_filtered_output,\n                    target_path=local_target,\n                )\n",
        "                pending_replacements.append((\n                    temp_filtered_output,\n                    local_target,\n                ))\n",
        "download defer filtered replace",
    )
    text = replace_once(
        text,
        "                print(f\"Status:            erfolgreich gefiltert ({filtered_count} Zeilen)\")\n\n        finally:\n",
        "                print(f\"Status:            erfolgreich gefiltert ({filtered_count} Zeilen)\")\n\n            commit_snapshot_safely(\n                pending_replacements=pending_replacements,\n                snapshot_at_utc=snapshot_at_utc,\n                summary_rows=summary_rows,\n                run_temp_dir=run_temp_dir,\n            )\n\n            print(\n                \"Snapshot vollständig übernommen: \"\n                f\"{snapshot_at_utc:%Y-%m-%dT%H:%M:%SZ}\"\n            )\n\n        finally:\n",
        "download commit snapshot",
    )
    return text


def transform_run_all(text: str) -> str:
    text = replace_once(
        text,
        "import csv\nimport os\n",
        "import csv\nimport json\nimport os\n",
        "run_all imports",
    )
    text = replace_once(
        text,
        "from error_rules import build_findings\n",
        "from error_rules import build_findings\nfrom export_module import build_export_tables\n",
        "run_all central export import",
    )
    text = replace_once(
        text,
        'LOG_DIR = ROOT / "data" / "04_logs"\n',
        'LOG_DIR = ROOT / "data" / "04_logs"\nRAW_IMPORT_MANIFEST_PATH = RAW_DIR / "raw_import_manifest.json"\nREQUIRED_RAW_SOURCE_FILES = {\n    "locomotivemovement.csv",\n    "transportdetail.csv",\n    "locomotive.csv",\n}\n# NETZENTGELT_HARDENING_V1_20260607: stabiler Rohdaten-Snapshot\n',
        "run_all manifest constants",
    )
    snapshot_helper = r'''

def get_source_snapshot_at_utc() -> str:
    """
    Stabilen Zeitpunkt des letzten vollständig übernommenen Azure-Snapshots lesen.

    Das Manifest wird erst geschrieben, nachdem alle benötigten Rohdaten-Dateien
    validiert und gemeinsam übernommen wurden. Der Fallback über Datei-mtime hält
    bestehende lokale Entwicklungsstände weiterhin lauffähig.
    """
    if RAW_IMPORT_MANIFEST_PATH.exists():
        try:
            payload = json.loads(
                RAW_IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
            )
            value = str(payload.get("snapshot_at_utc", "")).strip()

            if value:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)

                return parsed.astimezone(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

    expected_files = [
        RAW_DIR / "LocomotiveMovement.csv",
        RAW_DIR / "TransportDetail.csv",
        RAW_DIR / "Locomotive.csv",
    ]
    existing_files = [path for path in expected_files if path.exists()]

    if existing_files:
        newest_timestamp = max(path.stat().st_mtime for path in existing_files)
        return datetime.fromtimestamp(
            newest_timestamp,
            tz=timezone.utc,
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    return ts()

'''
    text = replace_once(
        text,
        "\ndef remove_if_exists(path: Path):\n",
        snapshot_helper + "\ndef remove_if_exists(path: Path):\n",
        "run_all snapshot helper",
    )
    text = replace_once(
        text,
        "            imported_at_utc varchar,\n            source_file varchar,\n",
        "            imported_at_utc varchar,\n            source_snapshot_at_utc varchar,\n            source_file varchar,\n",
        "run_all import schema",
    )
    text = replace_once(
        text,
        '    run_id = datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S")\n    files = sorted(RAW_DIR.glob("*.csv"))\n',
        '    run_id = datetime.now(timezone.utc).strftime("RUN_%Y%m%d_%H%M%S")\n    source_snapshot_at_utc = get_source_snapshot_at_utc()\n    files = sorted(RAW_DIR.glob("*.csv"))\n',
        "run_all import snapshot value",
    )
    text = replace_once(
        text,
        "    imported = []\n    for file in files:\n",
        "    imported = []\n    successful_source_files = []\n    import_failures = []\n\n    for file in files:\n",
        "run_all import tracking",
    )
    text = replace_once(
        text,
        '            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?)",\n                        [run_id, ts(), file.name, target, sha256(file), rc, "imported", None])\n            imported.append(target)\n',
        '            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?, ?)",\n                        [run_id, ts(), source_snapshot_at_utc, file.name, target, sha256(file), rc, "imported", None])\n            imported.append(target)\n            successful_source_files.append(file.name.lower())\n',
        "run_all successful insert",
    )
    text = replace_once(
        text,
        '            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?)",\n                        [run_id, ts(), file.name, target, sha256(file), 0, "failed", str(e)])\n            print(f"FEHLER Import {file.name}: {e}")\n    return run_id, imported\n',
        '            con.execute("insert into raw_import_run values (?, ?, ?, ?, ?, ?, ?, ?, ?)",\n                        [run_id, ts(), source_snapshot_at_utc, file.name, target, sha256(file), 0, "failed", str(e)])\n            import_failures.append(f"{file.name}: {e}")\n            print(f"FEHLER Import {file.name}: {e}")\n\n    missing_required_files = sorted(\n        REQUIRED_RAW_SOURCE_FILES - set(successful_source_files)\n    )\n\n    if missing_required_files or import_failures:\n        details = []\n\n        if missing_required_files:\n            details.append(\n                "Fehlende Pflichtimporte: "\n                + ", ".join(missing_required_files)\n            )\n\n        if import_failures:\n            details.append(\n                "Fehlgeschlagene CSV-Importe: "\n                + " | ".join(import_failures)\n            )\n\n        raise RuntimeError(\n            "Rohdatenimport unvollständig. Fachliche Berechnung wird abgebrochen. "\n            + " ".join(details)\n        )\n\n    return run_id, imported\n',
        "run_all fail fast",
    )

    wrapper = '''def build_exports(con):
    """
    Rückwärtskompatibler Wrapper.

    Die zentrale Exportlogik liegt ausschließlich in export_module.py, damit
    CSV- und XLSX-Ausgaben dieselben Fallbacks und Felddefinitionen verwenden.
    NETZENTGELT_HARDENING_V1_20260607
    """
    build_export_tables(con)

'''
    text = regex_replace_once(
        text,
        r"def build_exports\(con\):\n.*?\n(?=def export_table\(con, table, file_name\):)",
        wrapper,
        "run_all central export wrapper",
    )
    text = replace_once(
        text,
        '            ("dq_findings", "dq_findings.csv"),\n',
        '            ("dq_findings", "dq_findings.csv"),\n            ("dq_run_metadata", "dq_run_metadata.csv"),\n',
        "run_all dq metadata csv",
    )
    return text


def transform_error_rules(text: str) -> str:
    helper = '''def _get_error_cutoff_utc(con, run_id: str) -> tuple[str, str]:
    """
    Stabilen Snapshot-Zeitpunkt und fachlichen 24h-Cutoff liefern.

    source_snapshot_at_utc stammt aus dem nach vollständigem Azure-Download
    geschriebenen Manifest. Für ältere Datenbankstände bleibt imported_at_utc
    als defensiver Fallback erhalten.
    NETZENTGELT_HARDENING_V1_20260607
    """
    raw_import_columns = {
        column.lower()
        for column in _columns(con, "raw_import_run")
    }

    if "source_snapshot_at_utc" in raw_import_columns:
        snapshot_expression = (
            "coalesce(" 
            "try_cast(source_snapshot_at_utc as timestamp), "
            "try_cast(imported_at_utc as timestamp)"
            ")"
        )
    else:
        snapshot_expression = "try_cast(imported_at_utc as timestamp)"

    source_snapshot_at_utc = con.execute(
        f"""
        select max({snapshot_expression})
        from raw_import_run
        where run_id = ?
          and status = 'imported'
        """,
        [run_id],
    ).fetchone()[0]

    if source_snapshot_at_utc is None:
        source_snapshot_at_utc = con.execute(
            "select current_timestamp"
        ).fetchone()[0]

    error_cutoff_utc = con.execute(
        "select try_cast(? as timestamp) - interval '1 day'",
        [str(source_snapshot_at_utc)],
    ).fetchone()[0]

    return str(source_snapshot_at_utc), str(error_cutoff_utc)


'''
    text = regex_replace_once(
        text,
        r"def _get_error_cutoff_utc\(con, run_id: str\) -> str:\n.*?\n(?=def build_r012_raw_findings\()",
        helper,
        "error_rules stable cutoff helper",
    )
    text = replace_once(
        text,
        "    error_cutoff_utc = _get_error_cutoff_utc(con, run_id)\n    error_cutoff = sql_lit(error_cutoff_utc)\n\n    print(f\"DQ 24h-Cutoff UTC: {error_cutoff_utc}\")\n\n    build_rule_catalog(con)\n",
        "    source_snapshot_at_utc, error_cutoff_utc = _get_error_cutoff_utc(\n        con,\n        run_id,\n    )\n    error_cutoff = sql_lit(error_cutoff_utc)\n\n    print(f\"DQ Snapshot UTC: {source_snapshot_at_utc}\")\n    print(f\"DQ 24h-Cutoff UTC: {error_cutoff_utc}\")\n\n    con.execute(\"\"\"\n        create or replace table dq_run_metadata as\n        select\n            ?::varchar as run_id,\n            try_cast(? as timestamp) as source_snapshot_at_utc,\n            try_cast(? as timestamp) as error_cutoff_utc,\n            current_timestamp as calculated_at_utc\n    \"\"\", [\n        run_id,\n        source_snapshot_at_utc,\n        error_cutoff_utc,\n    ])\n\n    build_rule_catalog(con)\n",
        "error_rules dq metadata",
    )
    refresh_export_ready = r'''

    # Exportfähigkeit nach der zentralen Finding-Berechnung neu ableiten.
    # Dadurch blockieren offene ERROR- und MANUAL_REVIEW-Findings auch Exporte.
    con.execute("""
        update core_loco_timeline
        set export_ready = case
            when row_type = 'MOVEMENT'
             and report_scope = 'IN_REPORT'
             and coalesce(needs_manual_review, false) = false
             and sequence_ts is not null
             and period_start_utc is not null
             and period_end_utc is not null
             and period_start_utc <= period_end_utc
             and loco_no is not null
             and loco_no <> ''
             and user_vens is not null
             and user_vens <> ''
             and performing_ru_marktpartner_id is not null
             and performing_ru_marktpartner_id <> ''
                then true
            else false
        end
    """)
'''
    text = replace_once(
        text,
        "          and c.source_row_id is not distinct from s.source_row_id\n    \"\"\")\n\n\ndef build_findings(\n",
        "          and c.source_row_id is not distinct from s.source_row_id\n    \"\"\")\n" + refresh_export_ready + "\n\ndef build_findings(\n",
        "error_rules export ready refresh",
    )
    return text


def transform_export_module(text: str) -> str:
    text = replace_once(
        text,
        '    ("dq_findings", "dq_findings.csv"),\n',
        '    ("dq_findings", "dq_findings.csv"),\n    ("dq_run_metadata", "dq_run_metadata.csv"),\n',
        "export_module dq metadata csv",
    )
    text = replace_once(
        text,
        '    normalized_performing_ru_sql = _normalize_company_name_sql("s.performing_ru")\n',
        '    normalized_performing_ru_sql = _normalize_company_name_sql("s.performing_ru")\n    normalized_holder_sql = _normalize_company_name_sql("s.holder_name")\n',
        "export_module normalized holder",
    )
    text = replace_once(
        text,
        "                count(*) filter (\n                    where row_type = 'MOVEMENT'\n                ) as movement_count,\n\n                first(\n",
        "                count(*) filter (\n                    where row_type = 'MOVEMENT'\n                ) as movement_count,\n\n                max(\n                    case\n                        when row_type = 'MOVEMENT'\n                         and report_scope = 'IN_REPORT'\n                         and coalesce(export_ready, false) = false\n                            then 1\n                        else 0\n                    end\n                ) as has_export_blocking_movement,\n\n                first(\n",
        "export_module segment blocking flag",
    )
    text = replace_once(
        text,
        "         and ane_mapping.source_value_normalized = {normalized_performing_ru_sql}\n",
        "         and ane_mapping.source_value_normalized = {normalized_holder_sql}\n",
        "export_module ane holder mapping",
    )
    text = replace_once(
        text,
        "         and ane_direct.company_name_normalized = {normalized_performing_ru_sql}\n",
        "         and ane_direct.company_name_normalized = {normalized_holder_sql}\n",
        "export_module ane holder direct",
    )
    text = replace_once(
        text,
        "          and s.usage_start is not null\n\n        order by\n",
        "          and s.usage_start is not null\n          and coalesce(s.has_export_blocking_movement, 0) = 0\n\n        order by\n",
        "export_module segment block where",
    )
    text = replace_once(
        text,
        "              and performing_ru in ({placeholders})\n        ),\n",
        "              and performing_ru in ({placeholders})\n              and coalesce(needs_manual_review, false) = false\n        ),\n",
        "export_module event blocking",
    )
    return text


def transform_app(text: str) -> str:
    text = replace_once(
        text,
        "from pathlib import Path\nfrom datetime import date, datetime, timedelta, timezone\nimport subprocess\n",
        "from pathlib import Path\nfrom datetime import date, datetime, timedelta, timezone\nimport json\nimport subprocess\n",
        "app json import",
    )
    text = replace_once(
        text,
        'RAW_DIR = BASE_DIR / "data" / "00_raw"\nDB_PATH = BASE_DIR / "data" / "02_duckdb" / "netzentgelt.duckdb"\n',
        'RAW_DIR = BASE_DIR / "data" / "00_raw"\nRAW_IMPORT_MANIFEST_PATH = RAW_DIR / "raw_import_manifest.json"\nDB_PATH = BASE_DIR / "data" / "02_duckdb" / "netzentgelt.duckdb"\n# NETZENTGELT_HARDENING_V1_20260607: einheitlicher Snapshot-Zeitpunkt\n',
        "app manifest constant",
    )
    manifest_reader = '''def get_last_raw_import_datetime():
    """
    Zeitpunkt des letzten vollständig übernommenen Rohdaten-Snapshots liefern.

    Primär wird das Manifest aus download_blob_data.py gelesen. Nur für ältere
    lokale Entwicklungsstände ohne Manifest wird defensiv auf Datei-mtime
    zurückgefallen.
    """
    if RAW_IMPORT_MANIFEST_PATH.exists():
        try:
            payload = json.loads(
                RAW_IMPORT_MANIFEST_PATH.read_text(encoding="utf-8")
            )
            value = str(payload.get("snapshot_at_utc", "")).strip()

            if value:
                parsed = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)

                return parsed.astimezone(timezone.utc)

        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

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

    return datetime.fromtimestamp(newest_timestamp, tz=timezone.utc)


'''
    text = regex_replace_once(
        text,
        r"def get_last_raw_import_datetime\(\):\n.*?\n(?=def run_python_script\(script_path: Path\):)",
        manifest_reader,
        "app manifest reader",
    )
    text = replace_once(
        text,
        "    lm_actual_col = get_col(\n        locomotive_movement,\n        [\n            \"ActualDeparture\",\n            \"LocomotiveActualDeparture\",\n        ],\n    )\n\n    lm_transport_col = get_col(\n",
        "    lm_actual_col = get_col(\n        locomotive_movement,\n        [\n            \"ActualDeparture\",\n            \"LocomotiveActualDeparture\",\n        ],\n    )\n\n    lm_actual_arrival_col = get_col(\n        locomotive_movement,\n        [\n            \"ActualArrival\",\n            \"LocomotiveActualArrival\",\n        ],\n    )\n\n    lm_transport_col = get_col(\n",
        "app lm arrival column",
    )
    text = replace_once(
        text,
        "    if lm_loco_col and lm_actual_col and lm_de_country_cols:\n",
        "    if lm_loco_col and (lm_actual_col or lm_actual_arrival_col) and lm_de_country_cols:\n",
        "app lm validation condition",
    )
    text = replace_once(
        text,
        "        lm_actual_departure_ts = parse_actual_departure(\n            locomotive_movement[lm_actual_col]\n        )\n\n        lm_is_at_least_one_day_old = (\n            lm_actual_departure_ts.notna()\n            & (lm_actual_departure_ts <= error_cutoff_ts)\n        )\n",
        "        if lm_actual_col:\n            lm_relevant_ts = parse_actual_departure(\n                locomotive_movement[lm_actual_col]\n            )\n        else:\n            lm_relevant_ts = pd.Series(\n                pd.NaT,\n                index=locomotive_movement.index,\n                dtype=\"datetime64[ns, UTC]\",\n            )\n\n        if lm_actual_arrival_col:\n            lm_relevant_ts = lm_relevant_ts.fillna(\n                parse_actual_departure(\n                    locomotive_movement[lm_actual_arrival_col]\n                )\n            )\n\n        lm_is_at_least_one_day_old = (\n            lm_relevant_ts.notna()\n            & (lm_relevant_ts <= error_cutoff_ts)\n        )\n",
        "app lm cutoff fallback",
    )
    text = replace_once(
        text,
        '            "LocomotiveNo, ActualDeparture oder Länderfeld fehlt als Spalte."\n',
        '            "LocomotiveNo, ActualDeparture/ActualArrival oder Länderfeld fehlt als Spalte."\n',
        "app lm status wording",
    )
    text = replace_once(
        text,
        '            "Benötigt werden die Spalten LocomotiveNo, ActualDeparture und mindestens "\n',
        '            "Benötigt werden LocomotiveNo, ActualDeparture oder ActualArrival und mindestens "\n',
        "app lm warning wording",
    )
    return text


TRANSFORMS = {
    Path("scripts/download_blob_data.py"): transform_download_blob_data,
    Path("scripts/run_all.py"): transform_run_all,
    Path("scripts/error_rules.py"): transform_error_rules,
    Path("scripts/export_module.py"): transform_export_module,
    Path("app/app.py"): transform_app,
}


def locate_repo_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
    else:
        root = Path.cwd().resolve()

    missing = [str(path) for path in TARGET_FILES if not (root / path).exists()]
    if missing:
        raise PatchError(
            "Repository-Stamm nicht erkannt. Starte das Skript im Projektstamm "
            "oder verwende --repo-root. Fehlende Dateien: " + ", ".join(missing)
        )
    return root


def syntax_check(files: dict[Path, str]) -> None:
    for relative_path, content in files.items():
        try:
            ast.parse(content, filename=str(relative_path))
        except SyntaxError as error:
            raise PatchError(
                f"Syntaxprüfung fehlgeschlagen: {relative_path}: {error}"
            ) from error


def static_post_checks(files: dict[Path, str]) -> None:
    checks = {
        Path("scripts/download_blob_data.py"): [
            "commit_snapshot_safely(",
            "raw_import_manifest.json",
            "write_snapshot_manifest(",
        ],
        Path("scripts/run_all.py"): [
            "source_snapshot_at_utc varchar",
            "Rohdatenimport unvollständig",
            "build_export_tables(con)",
            '("dq_run_metadata", "dq_run_metadata.csv")',
        ],
        Path("scripts/error_rules.py"): [
            "create or replace table dq_run_metadata",
            "coalesce(needs_manual_review, false) = false",
            "source_snapshot_at_utc, error_cutoff_utc",
        ],
        Path("scripts/export_module.py"): [
            'normalized_holder_sql = _normalize_company_name_sql("s.holder_name")',
            "has_export_blocking_movement",
            "and coalesce(needs_manual_review, false) = false",
        ],
        Path("app/app.py"): [
            "RAW_IMPORT_MANIFEST_PATH",
            "lm_actual_arrival_col",
            "lm_relevant_ts = lm_relevant_ts.fillna",
        ],
    }

    for relative_path, expected_fragments in checks.items():
        content = files[relative_path]
        for fragment in expected_fragments:
            if fragment not in content:
                raise PatchError(
                    f"Post-Check fehlgeschlagen: {relative_path}: {fragment}"
                )


def backup_files(root: Path) -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / ".patch_backups" / f"netzentgelt_hardening_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for relative_path in TARGET_FILES:
        source = root / relative_path
        target = backup_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    marker = root / ".patch_backups" / "LAST_NETZENTGELT_HARDENING_BACKUP.txt"
    marker.write_text(str(backup_dir), encoding="utf-8")
    return backup_dir


def restore_backup(root: Path, backup_dir: Path) -> None:
    for relative_path in TARGET_FILES:
        source = backup_dir / relative_path
        target = root / relative_path
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".patch_tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Netzentgelt-MVP: vollständiges Hardening-Paket anwenden."
    )
    parser.add_argument("--repo-root", help="Projektstamm, Standard: aktueller Ordner")
    parser.add_argument("--dry-run", action="store_true", help="Nur prüfen, nichts schreiben")
    args = parser.parse_args()

    try:
        root = locate_repo_root(args.repo_root)
        originals = {
            relative_path: (root / relative_path).read_text(encoding="utf-8-sig")
            for relative_path in TARGET_FILES
        }
        updated = {
            relative_path: TRANSFORMS[relative_path](content)
            for relative_path, content in originals.items()
        }

        syntax_check(updated)
        static_post_checks(updated)

        changed_files = [
            path for path in TARGET_FILES if updated[path] != originals[path]
        ]

        print("")
        print("=" * 80)
        print("Netzentgelt MVP - Hardening Patch")
        print("=" * 80)
        print(f"Repository: {root}")
        print(f"Patch-ID:   {PATCH_ID}")
        print(f"Geänderte Dateien: {len(changed_files)}")
        for path in changed_files:
            print(f"- {path}")

        if args.dry_run:
            print("\nDRY-RUN erfolgreich. Es wurden keine Dateien verändert.")
            return 0

        if not changed_files:
            print("\nPatch ist bereits vollständig vorhanden. Keine Änderung erforderlich.")
            return 0

        backup_dir = backup_files(root)
        print(f"\nBackup: {backup_dir}")

        try:
            for relative_path in changed_files:
                atomic_write(root / relative_path, updated[relative_path])

            written = {
                relative_path: (root / relative_path).read_text(encoding="utf-8-sig")
                for relative_path in TARGET_FILES
            }
            syntax_check(written)
            static_post_checks(written)

        except Exception:
            restore_backup(root, backup_dir)
            raise

        print("\nPatch erfolgreich eingespielt und syntaktisch validiert.")
        print("Nächster Schritt: .venv\\Scripts\\python.exe scripts\\run_all.py")
        return 0

    except PatchError as error:
        print(f"\nPATCH FEHLGESCHLAGEN: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"\nUNERWARTETER FEHLER: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
