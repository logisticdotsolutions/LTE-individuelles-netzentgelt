from __future__ import annotations

import argparse
from pathlib import Path
import duckdb

MARKER = "NETZENTGELT_DUMMY_LOCOMOTIVE_VERIFY_SCHEMA_HOTFIX_V1_20260609"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
KNOWN = {
    "91850000002-4",
    "00000000011-7",
    "00000000000-0",
    "00000000003-4",
    "00000000013-3",
    "00000000010-9",
    "00000000008-3",
    "00000000015-8",
    "00000000004-2",
    "00000000009-1",
    "00000000005-9",
    "00000000006-7",
    "00000000007-5",
    "91850000007-3",
    "91850000008-1",
    "91850000003-2",
    "91850000004-0",
    "91850000001-6",
    "00000000002-6",
    "00000000014-1",
    "00000000001-8",
    "91806189000-3",
}


def scalar(con, sql: str, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def qident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def table_exists(con, table_name: str) -> bool:
    return bool(
        scalar(
            con,
            "select count(*) from information_schema.tables where lower(table_name)=lower(?)",
            [table_name],
        )
    )


def columns(con, table_name: str) -> list[str]:
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def resolve_column(con, table_name: str, candidates: list[str]) -> str:
    by_lower = {column.lower(): column for column in columns(con, table_name)}
    for candidate in candidates:
        if candidate.lower() in by_lower:
            return by_lower[candidate.lower()]
    raise RuntimeError(
        f"Tabelle {table_name} enthält keine erwartete Lokspalte. "
        f"Erwartet eine von: {', '.join(candidates)}. "
        f"Vorhanden: {', '.join(columns(con, table_name))}"
    )


def count_dummy_rows_in_table(con, table_name: str, candidates: list[str]) -> int:
    loco_column = resolve_column(con, table_name, candidates)
    return int(
        scalar(
            con,
            f"""
            select count(*)
            from {qident(table_name)} e
            join cfg_dummy_locomotives_effective d
              on d.loco_no = trim(cast(e.{qident(loco_column)} as varchar))
            """,
        )
    )


def verify(db_path: Path) -> int:
    if not db_path.exists():
        print(f"FEHLER: DuckDB fehlt: {db_path}")
        return 1

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        required = [
            "cfg_dummy_locomotives_effective",
            "audit_excluded_dummy_locomotives",
            "audit_excluded_dummy_locomotive_staging",
            "stg_loco_events",
            "core_loco_timeline",
            "dq_findings",
            "export_zuordnungen",
            "export_nutzungsmeldung",
            "raw_locomotivemovement",
        ]
        missing = [table for table in required if not table_exists(con, table)]
        if missing:
            print("FEHLER: Tabellen fehlen: " + ", ".join(missing))
            return 1

        present = {
            row[0]
            for row in con.execute("select loco_no from cfg_dummy_locomotives_effective").fetchall()
        }
        missing_known = sorted(KNOWN - present)
        if missing_known:
            print("FEHLER: bekannte zusätzliche Dummy-Loks fehlen im Katalog: " + ", ".join(missing_known))
            return 1

        checks = {
            "Dummy-Zeilen im Staging": count_dummy_rows_in_table(
                con, "stg_loco_events", ["loco_no", "tfze_or_tens", "TfzE oder tEns*"]
            ),
            "Dummy-Zeilen in Timeline": count_dummy_rows_in_table(
                con, "core_loco_timeline", ["loco_no", "tfze_or_tens", "TfzE oder tEns*"]
            ),
            "Dummy-Zeilen im Zuordnungs-Export": count_dummy_rows_in_table(
                con, "export_zuordnungen", ["loco_no", "tfze_or_tens", "TfzE oder tEns*"]
            ),
            "Dummy-Zeilen im Nutzungsmeldungs-Export": count_dummy_rows_in_table(
                con, "export_nutzungsmeldung", ["loco_no", "tfze_or_tens", "TfzE oder tEns*"]
            ),
            "Nicht-R012-Findings fuer Dummies": int(
                scalar(
                    con,
                    """
                    select count(*)
                    from dq_findings f
                    join cfg_dummy_locomotives_effective d on d.loco_no=f.loco_no
                    where f.rule_id <> 'R012'
                    """,
                )
            ),
        }

        failed = False
        print("Dummy-Lok-Verifikation:")
        for label, count in checks.items():
            print(f"  {label}: {count}")
            failed = failed or count != 0

        raw_loco_column = resolve_column(
            con, "raw_locomotivemovement", ["LocomotiveNo", "FirstLocomotiveNo", "Alias"]
        )
        raw_type_column = resolve_column(con, "raw_locomotivemovement", ["LocomotiveType"])
        type_not_cataloged = int(
            scalar(
                con,
                f"""
                select count(*)
                from raw_locomotivemovement r
                where lower(coalesce(cast(r.{qident(raw_type_column)} as varchar), '')) like '%dummy%'
                  and nullif(trim(cast(r.{qident(raw_loco_column)} as varchar)), '') is not null
                  and not exists (
                        select 1
                        from cfg_dummy_locomotives_effective d
                        where d.loco_no = trim(cast(r.{qident(raw_loco_column)} as varchar))
                  )
                """,
            )
        )
        print(f"  LocomotiveType-Dummy ohne Katalogtreffer: {type_not_cataloged}")
        failed = failed or type_not_cataloged != 0

        audit = int(scalar(con, "select count(*) from audit_excluded_dummy_locomotive_staging"))
        r012 = int(
            scalar(
                con,
                "select count(*) from dq_findings where rule_id='R012' and row_type='RAW_DUMMY_LOCOMOTIVE'",
            )
        )
        print(f"  Auditierte ausgeschlossene Staging-Zeilen: {audit}")
        print(f"  Verdichtete R012-Dummy-Faelle: {r012}")

        if failed:
            print("FEHLER: Dummy-Lok-Verifikation fehlgeschlagen.")
            return 1
        print("OK: Dummy-Lok-Verifikation erfolgreich.")
        return 0
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Dummy-Lok-Hardening gegen produktives DuckDB-Schema verifizieren.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    return verify(args.db)


if __name__ == "__main__":
    raise SystemExit(main())
