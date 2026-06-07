from __future__ import annotations

import argparse
import codecs
import py_compile
import shutil
from pathlib import Path


def read_text_preserve_bom(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    return raw.decode("utf-8-sig" if has_bom else "utf-8"), has_bom


def write_text_preserve_bom(path: Path, content: str, has_bom: bool) -> None:
    encoding = "utf-8-sig" if has_bom else "utf-8"
    path.write_text(content, encoding=encoding, newline="")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"Patch '{label}' erwartet exakt 1 Treffer, gefunden: {count}. "
            "Bitte aktuellen GitHub-Stand prüfen und Patch aktualisieren."
        )
    return text.replace(old, new, 1)


def patch_error_rules(text: str) -> str:
    text = replace_once(
        text,
        """def build_r012_raw_findings(\n    con,\n    run_id: str,\n) -> None:\n""",
        """def _get_error_cutoff_utc(con, run_id: str) -> str:\n    \"\"\"\n    Fachlichen 24h-Cutoff aus dem letzten erfolgreichen Rohdatenimport ableiten.\n\n    ERROR- und MANUAL_REVIEW-Findings dürfen nur für Datenzeilen entstehen,\n    deren relevanter Zeitstempel mindestens 24 Stunden vor diesem Import liegt.\n    Falls wider Erwarten kein Import-Audit vorhanden ist, wird defensiv der\n    aktuelle Zeitpunkt als Fallback verwendet.\n    \"\"\"\n    imported_at_utc = con.execute(\"\"\"\n        select max(try_cast(imported_at_utc as timestamp))\n        from raw_import_run\n        where run_id = ?\n          and status = 'imported'\n    \"\"\", [run_id]).fetchone()[0]\n\n    if imported_at_utc is None:\n        imported_at_utc = con.execute(\n            \"select current_timestamp\"\n        ).fetchone()[0]\n\n    return str(\n        con.execute(\n            \"select try_cast(? as timestamp) - interval '1 day'\",\n            [str(imported_at_utc)],\n        ).fetchone()[0]\n    )\n\n\ndef build_r012_raw_findings(\n    con,\n    run_id: str,\n    error_cutoff_utc: str,\n) -> None:\n""",
        "error_rules: helper and R012 signature",
    )

    text = replace_once(
        text,
        """    separate Queue-Einträge vervielfacht.\n    \"\"\"\n    con.execute(\"\"\"\n""",
        """    separate Queue-Einträge vervielfacht.\n    \"\"\"\n    error_cutoff = sql_lit(error_cutoff_utc)\n\n    con.execute(\"\"\"\n""",
        "error_rules: R012 cutoff literal",
    )

    text = replace_once(
        text,
        """                      and period_start_utc <= current_timestamp - interval '1 day'\n""",
        """                      and period_start_utc <= try_cast({error_cutoff} as timestamp)\n""",
        "error_rules: TransportDetail R012 import cutoff",
    )

    text = replace_once(
        text,
        """                    where is_de_relevant\n                      and (has_missing_loco or has_technical_loco or has_dummy_type)\n""",
        """                    where is_de_relevant\n                      and coalesce(period_start_utc, period_end_utc) is not null\n                      and coalesce(period_start_utc, period_end_utc) <= try_cast({error_cutoff} as timestamp)\n                      and (has_missing_loco or has_technical_loco or has_dummy_type)\n""",
        "error_rules: LocomotiveMovement R012 import cutoff",
    )

    text = replace_once(
        text,
        """    run = sql_lit(run_id)\n\n    build_rule_catalog(con)\n""",
        """    run = sql_lit(run_id)\n    error_cutoff_utc = _get_error_cutoff_utc(con, run_id)\n    error_cutoff = sql_lit(error_cutoff_utc)\n\n    print(f\"DQ 24h-Cutoff UTC: {error_cutoff_utc}\")\n\n    build_rule_catalog(con)\n""",
        "error_rules: central cutoff derivation",
    )

    text = replace_once(
        text,
        """        with movement_base as (\n            select *\n            from core_loco_timeline\n            where row_type = 'MOVEMENT'\n              and report_scope = 'IN_REPORT'\n        ),\n        overlap as (\n            select\n                b.*,\n                lag(period_end_utc) over (\n                    partition by loco_no\n                    order by\n                        coalesce(sequence_ts, period_start_utc, period_end_utc) asc nulls last,\n                        source_row_id asc\n                ) as prev_end\n            from movement_base b\n        )\n""",
        """        with movement_base as (\n            select *\n            from core_loco_timeline\n            where row_type = 'MOVEMENT'\n              and report_scope = 'IN_REPORT'\n        ),\n        movement_error_base as (\n            select *\n            from movement_base\n            where coalesce(period_start_utc, period_end_utc) is not null\n              and coalesce(period_start_utc, period_end_utc) <= try_cast({error_cutoff} as timestamp)\n        ),\n        gap_error_base as (\n            select *\n            from core_loco_timeline\n            where row_type = 'GAP'\n              and coalesce(gap_relevant_de, false) = true\n              and coalesce(period_end_utc, period_start_utc) is not null\n              and coalesce(period_end_utc, period_start_utc) <= try_cast({error_cutoff} as timestamp)\n        ),\n        overlap as (\n            select\n                b.*,\n                lag(period_end_utc) over (\n                    partition by loco_no\n                    order by\n                        coalesce(sequence_ts, period_start_utc, period_end_utc) asc nulls last,\n                        source_row_id asc\n                ) as prev_end\n            from movement_error_base b\n        )\n""",
        "error_rules: blocking finding bases",
    )

    text = replace_once(
        text,
        """        from movement_base\n        where report_scope = 'IN_REPORT'\n          and coalesce(movement_sequence_no, 0) <> 1\n          and sequence_ts is null\n""",
        """        from movement_error_base\n        where report_scope = 'IN_REPORT'\n          and coalesce(movement_sequence_no, 0) <> 1\n          and sequence_ts is null\n""",
        "error_rules: R001 ERROR cutoff",
    )

    text = replace_once(
        text,
        """        from movement_base\n        where report_scope = 'IN_REPORT'\n          and period_start_utc is not null\n          and period_end_utc is not null\n          and period_start_utc > period_end_utc\n""",
        """        from movement_error_base\n        where report_scope = 'IN_REPORT'\n          and period_start_utc is not null\n          and period_end_utc is not null\n          and period_start_utc > period_end_utc\n""",
        "error_rules: R004 cutoff",
    )

    text = replace_once(
        text,
        """        from movement_base\n        where report_scope = 'IN_REPORT'\n          and (performing_ru is null or performing_ru = '')\n""",
        """        from movement_error_base\n        where report_scope = 'IN_REPORT'\n          and (performing_ru is null or performing_ru = '')\n""",
        "error_rules: R009 cutoff",
    )

    text = replace_once(
        text,
        """        from core_loco_timeline\n        where row_type = 'GAP'\n          and coalesce(gap_relevant_de, false) = true\n          and coalesce(gap_duration_minutes, 0) > 480\n""",
        """        from gap_error_base\n        where coalesce(gap_duration_minutes, 0) > 480\n""",
        "error_rules: R010 cutoff",
    )

    text = replace_once(
        text,
        """    build_r012_raw_findings(\n        con=con,\n        run_id=run_id,\n    )\n""",
        """    build_r012_raw_findings(\n        con=con,\n        run_id=run_id,\n        error_cutoff_utc=error_cutoff_utc,\n    )\n""",
        "error_rules: pass cutoff to R012",
    )

    return text


def patch_app(text: str) -> str:
    text = replace_once(
        text,
        "from datetime import date, datetime, timedelta\n",
        "from datetime import date, datetime, timedelta, timezone\n",
        "app: timezone import",
    )

    text = replace_once(
        text,
        "    return datetime.fromtimestamp(newest_timestamp)\n",
        "    return datetime.fromtimestamp(newest_timestamp, tz=timezone.utc)\n",
        "app: UTC-aware raw import timestamp",
    )

    text = replace_once(
        text,
        """    summary_rows = []\n    detail_frames = []\n    warnings = []\n\n    # ==================================================\n""",
        """    summary_rows = []\n    detail_frames = []\n    warnings = []\n\n    last_import = get_last_raw_import_datetime()\n\n    if last_import is None:\n        error_cutoff_ts = pd.Timestamp.now(tz=\"UTC\") - pd.Timedelta(days=1)\n        warnings.append(\n            \"Kein Rohdaten-Importzeitpunkt gefunden. \"\n            \"Für die 24h-Prüfung wird ersatzweise aktuelle Zeit minus 24 Stunden verwendet.\"\n        )\n    else:\n        last_import_ts = pd.Timestamp(last_import)\n\n        if last_import_ts.tzinfo is None:\n            last_import_ts = last_import_ts.tz_localize(\"UTC\")\n        else:\n            last_import_ts = last_import_ts.tz_convert(\"UTC\")\n\n        error_cutoff_ts = last_import_ts - pd.Timedelta(days=1)\n\n    # ==================================================\n""",
        "app: diagnostics cutoff derivation",
    )

    text = replace_once(
        text,
        """        # Rolling Window:\n        # Als Fehler gelten nur Transporte, deren ActualDeparture\n        # mindestens 24 Stunden vor dem aktuellen Zeitpunkt liegt.\n        td_cutoff_ts = pd.Timestamp.now(tz=\"UTC\") - pd.Timedelta(days=1)\n""",
        """        # Rolling Window:\n        # Als Fehler gelten nur Transporte, deren ActualDeparture\n        # mindestens 24 Stunden vor dem letzten Importzeitpunkt liegt.\n        td_cutoff_ts = error_cutoff_ts\n""",
        "app: TransportDetail diagnostic import cutoff",
    )

    text = replace_once(
        text,
        """    if lm_loco_col and lm_de_country_cols:\n""",
        """    if lm_loco_col and lm_actual_col and lm_de_country_cols:\n""",
        "app: require LocomotiveMovement timestamp",
    )

    text = replace_once(
        text,
        """        lm_mask = (\n            lm_is_de_relevant\n            & (\n                lm_is_missing_loco_no\n                | lm_is_technical_loco_no\n                | lm_is_dummy_type\n            )\n        )\n""",
        """        lm_actual_departure_ts = parse_actual_departure(\n            locomotive_movement[lm_actual_col]\n        )\n\n        lm_is_at_least_one_day_old = (\n            lm_actual_departure_ts.notna()\n            & (lm_actual_departure_ts <= error_cutoff_ts)\n        )\n\n        lm_mask = (\n            lm_is_de_relevant\n            & lm_is_at_least_one_day_old\n            & (\n                lm_is_missing_loco_no\n                | lm_is_technical_loco_no\n                | lm_is_dummy_type\n            )\n        )\n""",
        "app: LocomotiveMovement diagnostic import cutoff",
    )

    text = replace_once(
        text,
        """                \"DE-relevanter Abschnitt, LocomotiveNo fehlt, \"\n                \"LocomotiveNo = 00000000000-0 \"\n                \"oder LocomotiveType enthält Dummy\"\n""",
        """                \"DE-relevanter Abschnitt, ActualDeparture mindestens 24 Stunden \"\n                \"vor dem letzten Import, LocomotiveNo fehlt, \"\n                \"LocomotiveNo = 00000000000-0 oder LocomotiveType enthält Dummy\"\n""",
        "app: LocomotiveMovement detail reason",
    )

    text = replace_once(
        text,
        """            \"Nicht auswertbar: \"\n            \"LocomotiveNo oder Länderfeld fehlt als Spalte.\"\n""",
        """            \"Nicht auswertbar: \"\n            \"LocomotiveNo, ActualDeparture oder Länderfeld fehlt als Spalte.\"\n""",
        "app: LocomotiveMovement unavailable status",
    )

    text = replace_once(
        text,
        """            \"Benötigt werden die Spalte LocomotiveNo und mindestens \"\n            \"ein auswertbares Länderfeld wie Country. \"\n""",
        """            \"Benötigt werden die Spalten LocomotiveNo, ActualDeparture und mindestens \"\n            \"ein auswertbares Länderfeld wie Country. \"\n""",
        "app: LocomotiveMovement warning",
    )

    text = replace_once(
        text,
        """            \"DE-relevanter Abschnitt, LocomotiveNo fehlt, \"\n            \"LocomotiveNo = 00000000000-0 \"\n            \"oder LocomotiveType enthält Dummy\"\n""",
        """            \"DE-relevanter Abschnitt, ActualDeparture mindestens 24 Stunden \"\n            \"vor dem letzten Import, LocomotiveNo fehlt, \"\n            \"LocomotiveNo = 00000000000-0 oder LocomotiveType enthält Dummy\"\n""",
        "app: LocomotiveMovement summary reason",
    )

    return text


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wendet den 24h-Import-Cutoff-Fix auf das Netzentgelt-MVP an."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Pfad zum Repository-Stamm. Standard: aktuelles Verzeichnis.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prüft nur, ob alle erwarteten Codestellen vorhanden sind.",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    files = {
        root / "scripts" / "error_rules.py": patch_error_rules,
        root / "app" / "app.py": patch_app,
    }

    patched: list[tuple[Path, str, bool]] = []

    for path, patcher in files.items():
        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")

        original, has_bom = read_text_preserve_bom(path)
        updated = patcher(original)

        if original == updated:
            raise RuntimeError(f"Keine Änderung erzeugt: {path}")

        patched.append((path, updated, has_bom))

    if args.dry_run:
        print("DRY RUN erfolgreich: alle erwarteten Codestellen wurden gefunden.")
        for path, _, _ in patched:
            print(f"  OK: {path.relative_to(root)}")
        return

    for path, updated, has_bom in patched:
        backup = path.with_suffix(path.suffix + ".bak_before_24h_fix")
        shutil.copy2(path, backup)
        write_text_preserve_bom(path, updated, has_bom)
        print(f"Aktualisiert: {path.relative_to(root)}")
        print(f"Backup:       {backup.relative_to(root)}")

    for path, _, _ in patched:
        py_compile.compile(str(path), doraise=True)
        print(f"Syntax OK:    {path.relative_to(root)}")

    print("\n24h-Import-Cutoff-Fix erfolgreich eingespielt.")
    print("Bitte anschließend die Pipeline neu ausführen und die Fehlerqueue prüfen.")


if __name__ == "__main__":
    main()
