from __future__ import annotations

from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
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
}


def scalar(con, sql: str, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def table_exists(con, table_name: str) -> bool:
    return bool(
        scalar(
            con,
            "select count(*) from information_schema.tables where lower(table_name)=lower(?)",
            [table_name],
        )
    )


def main() -> int:
    if not DB.exists():
        print(f"FEHLER: DuckDB fehlt: {DB}")
        return 1
    con = duckdb.connect(str(DB), read_only=True)
    required = [
        "cfg_dummy_locomotives_effective",
        "audit_excluded_dummy_locomotives",
        "audit_excluded_dummy_locomotive_staging",
        "stg_loco_events",
        "core_loco_timeline",
        "dq_findings",
        "export_zuordnungen",
        "export_nutzungsmeldung",
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
        "Dummy-Zeilen im Staging": "select count(*) from stg_loco_events e join cfg_dummy_locomotives_effective d on d.loco_no=e.loco_no",
        "Dummy-Zeilen in Timeline": "select count(*) from core_loco_timeline e join cfg_dummy_locomotives_effective d on d.loco_no=e.loco_no",
        "Dummy-Zeilen im Zuordnungs-Export": "select count(*) from export_zuordnungen e join cfg_dummy_locomotives_effective d on d.loco_no=e.loco_no",
        "Dummy-Zeilen im Nutzungsmeldungs-Export": "select count(*) from export_nutzungsmeldung e join cfg_dummy_locomotives_effective d on d.loco_no=e.loco_no",
        "Nicht-R012-Findings fuer Dummies": "select count(*) from dq_findings f join cfg_dummy_locomotives_effective d on d.loco_no=f.loco_no where f.rule_id <> 'R012'",
    }
    failed = False
    print("Dummy-Lok-Verifikation:")
    for label, sql in checks.items():
        count = scalar(con, sql)
        print(f"  {label}: {count}")
        failed = failed or count != 0

    type_not_cataloged = scalar(
        con,
        """
        select count(*)
        from raw_locomotivemovement r
        where lower(coalesce(cast(r.LocomotiveType as varchar), '')) like '%dummy%'
          and nullif(trim(cast(r.LocomotiveNo as varchar)), '') is not null
          and not exists (
                select 1
                from cfg_dummy_locomotives_effective d
                where d.loco_no = trim(cast(r.LocomotiveNo as varchar))
          )
        """,
    )
    print(f"  LocomotiveType-Dummy ohne Katalogtreffer: {type_not_cataloged}")
    failed = failed or type_not_cataloged != 0

    audit = scalar(con, "select count(*) from audit_excluded_dummy_locomotive_staging")
    r012 = scalar(
        con,
        "select count(*) from dq_findings where rule_id='R012' and row_type='RAW_DUMMY_LOCOMOTIVE'",
    )
    print(f"  Auditierte ausgeschlossene Staging-Zeilen: {audit}")
    print(f"  Verdichtete R012-Dummy-Faelle: {r012}")

    if failed:
        print("FEHLER: Dummy-Lok-Verifikation fehlgeschlagen.")
        return 1
    print("OK: Dummy-Lok-Verifikation erfolgreich.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
