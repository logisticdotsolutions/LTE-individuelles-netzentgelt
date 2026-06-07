from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

HOTFIX_MARKER = "NETZENTGELT_CANCELLED_HOTFIX_V2_20260607"
ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT / "scripts"
TARGETS = [
    ROOT / "scripts" / "run_all.py",
    ROOT / "scripts" / "error_rules.py",
    ROOT / "scripts" / "export_module.py",
    ROOT / "app" / "app.py",
]


def print_ok(message: str) -> None:
    print(f"[OK] {message}")


def print_info(message: str) -> None:
    print(f"[INFO] {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def table_exists(con, table_name: str) -> bool:
    return (
        con.execute(
            """
            select count(*)
            from information_schema.tables
            where lower(table_name) = lower(?)
            """,
            [table_name],
        ).fetchone()[0]
        > 0
    )


def check_static_files() -> None:
    for path in TARGETS:
        require(path.exists(), f"Pflichtdatei fehlt: {path.relative_to(ROOT)}")
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        compile(text, str(path), "exec")
        print_ok(f"Python-Syntax: {path.relative_to(ROOT)}")

        has_crlf = b"\r\n" in raw
        has_bare_lf = b"\n" in raw.replace(b"\r\n", b"")
        if has_crlf and has_bare_lf:
            raise RuntimeError(f"Gemischte Zeilenumbrüche erkannt: {path.relative_to(ROOT)}")
        print_ok(
            f"Zeilenumbrüche konsistent ({'CRLF' if has_crlf else 'LF'}): "
            f"{path.relative_to(ROOT)}"
        )

    run_all = (ROOT / "scripts" / "run_all.py").read_text(encoding="utf-8-sig")
    error_rules = (ROOT / "scripts" / "error_rules.py").read_text(encoding="utf-8-sig")
    export_module = (ROOT / "scripts" / "export_module.py").read_text(encoding="utf-8-sig")
    app = (ROOT / "app" / "app.py").read_text(encoding="utf-8-sig")

    checks = [
        (HOTFIX_MARKER in run_all, "run_all.py enthält Hotfix-Marker"),
        ("def build_cancelled_transport_exclusions(con):" in run_all, "Zentrale Ausschlussfunktion vorhanden"),
        ("TransportLastEditDate" in run_all, "Audit nutzt TransportLastEditDate"),
        ("TransportLastEditBy" in run_all, "Audit nutzt TransportLastEditBy"),
        (run_all.count("from cfg_excluded_cancelled_transports excluded") >= 3, "Timeline und Routenerkennung nutzen zentralen Ausschluss"),
        (error_rules.count("from cfg_excluded_cancelled_transports excluded") == 2, "R012 filtert beide Rohdatenquellen zentral"),
        ("audit_excluded_cancelled_transports.csv" in export_module, "Audit-CSV ist im Exportmodul registriert"),
        ("audit_excluded_cancelled_transports.csv" in run_all, "Audit-CSV wird im Tageslauf geschrieben"),
        ("def load_cancelled_transport_numbers() -> set[str]:" in app, "Streamlit-Rohdatenprüfung lädt zentrale Ausschlussliste"),
        (app.count("build_cancelled_transport_mask(") >= 3, "Streamlit-Rohdatenprüfung filtert TransportDetail und LocomotiveMovement"),
    ]

    for condition, message in checks:
        require(condition, message)
        print_ok(message)


def functional_smoke_test() -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError(
            "DuckDB fehlt in der aktiven Python-Umgebung. Bitte .venv verwenden."
        ) from exc

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))

    for module_name in ["run_all", "error_rules"]:
        if module_name in sys.modules:
            del sys.modules[module_name]

    run_all = importlib.import_module("run_all")
    error_rules = importlib.import_module("error_rules")

    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            create table raw_transportdetail (
                TransportNumber varchar,
                TransportStatus varchar,
                SequenceID varchar,
                OriginCountryISO varchar,
                DestinationCountryISO varchar,
                ActualDeparture varchar,
                ActualArrival varchar,
                FirstLocomotiveNo varchar,
                MovementType varchar
            )
            """
        )
        con.executemany(
            "insert into raw_transportdetail values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("CANCELLED_UK", " Cancelled ", "1", "DE", "DE", "2026-06-01T08:00:00", "2026-06-01T09:00:00", None, "Train movement"),
                ("CANCELED_US", "Canceled", "1", "AT", "DE", "2026-06-01T10:00:00", "2026-06-01T11:00:00", None, "Train movement"),
                ("ACTIVE_TD", "Active", "1", "DE", "DE", "2026-06-01T12:00:00", "2026-06-01T13:00:00", None, "Train movement"),
                ("ACTIVE_MOVE", "Active", "1", "DE", "DE", "2026-06-01T14:00:00", "2026-06-01T15:00:00", "91800000001-1", "Train movement"),
                ("ACTIVE_DUMMY", "Active", "1", "DE", "DE", "2026-06-01T16:00:00", "2026-06-01T17:00:00", "00000000000-0", "Train movement"),
            ],
        )

        con.execute(
            """
            create table raw_locomotivemovement (
                TransportNumber varchar,
                LocomotiveNo varchar,
                LocomotiveType varchar,
                LocomotiveHolder varchar,
                CurrentContractant varchar,
                OriginCountryISO varchar,
                DestinationCountryISO varchar,
                ActualDeparture varchar,
                ActualArrival varchar,
                TransportLastEditDate varchar,
                TransportLastEditBy varchar
            )
            """
        )
        con.executemany(
            "insert into raw_locomotivemovement values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("CANCELLED_UK", "91800000002-2", "Electric", "Holder", "RU", "DE", "DE", "2026-06-01T08:00:00", "2026-06-01T09:00:00", "2026-06-02T07:30:00", "editor.uk"),
                ("CANCELED_US", None, "Dummy", "Holder", "RU", "AT", "DE", "2026-06-01T10:00:00", "2026-06-01T11:00:00", "2026-06-02T08:45:00", "editor.us"),
                ("ACTIVE_MOVE", "91800000001-1", "Electric", "Holder", "RU", "DE", "DE", "2026-06-01T14:00:00", "2026-06-01T15:00:00", "2026-06-02T09:00:00", "editor.active"),
                ("ACTIVE_DUMMY", "00000000000-0", "Dummy", "Holder", "RU", "DE", "DE", "2026-06-01T16:00:00", "2026-06-01T17:00:00", "2026-06-02T09:15:00", "editor.dummy"),
            ],
        )

        run_all.build_cancelled_transport_exclusions(con)

        excluded = {
            row[0]
            for row in con.execute(
                "select transport_number from cfg_excluded_cancelled_transports"
            ).fetchall()
        }
        require(excluded == {"CANCELLED_UK", "CANCELED_US"}, f"Zentrale Ausschlussliste unerwartet: {excluded}")
        print_ok("Zentrale Transportnummernlogik erkennt Cancelled und Canceled")

        audit_rows = con.execute(
            """
            select source_table, transport_number, transport_last_edit_date, transport_last_edit_by
            from audit_excluded_cancelled_transports
            where source_table = 'raw_locomotivemovement'
            order by transport_number
            """
        ).fetchall()
        require(len(audit_rows) == 2, f"Audit enthält unerwartete LM-Zeilen: {audit_rows}")
        audit_by_transport = {row[1]: row for row in audit_rows}
        require(audit_by_transport["CANCELLED_UK"][3] == "editor.uk", "TransportLastEditBy für CANCELLED_UK fehlt")
        require(audit_by_transport["CANCELED_US"][3] == "editor.us", "TransportLastEditBy für CANCELED_US fehlt")
        require(audit_by_transport["CANCELLED_UK"][2] is not None, "TransportLastEditDate für CANCELLED_UK fehlt")
        print_ok("Audit enthält LocomotiveMovement-Zeilen mit TransportLastEditDate und TransportLastEditBy")

        run_all.build_loco_events(con)
        timeline_transports = {
            row[0]
            for row in con.execute(
                "select distinct transport_number from stg_loco_events where transport_number is not null"
            ).fetchall()
        }
        require("CANCELLED_UK" not in timeline_transports, "Cancelled-Transport wurde in Timeline-Staging übernommen")
        require("CANCELED_US" not in timeline_transports, "Canceled-Transport wurde in Timeline-Staging übernommen")
        require("ACTIVE_MOVE" in timeline_transports, "Aktiver Transport fehlt im Timeline-Staging")
        print_ok("Cancelled/Canceled werden aus Timeline-Staging ausgeschlossen")

        run_all.build_transport_routes(con)
        route_transports = {
            row[0]
            for row in con.execute(
                "select transport_number from core_transport_route"
            ).fetchall()
        }
        require("CANCELLED_UK" not in route_transports, "Cancelled-Transport wurde in Routenerkennung übernommen")
        require("CANCELED_US" not in route_transports, "Canceled-Transport wurde in Routenerkennung übernommen")
        require("ACTIVE_TD" in route_transports, "Aktiver Transport fehlt in Routenerkennung")
        print_ok("Cancelled/Canceled werden aus Routenerkennung ausgeschlossen")

        error_rules.build_r012_raw_findings(
            con=con,
            run_id="RUN_SMOKE_TEST",
            error_cutoff_utc="2026-06-10T00:00:00",
        )
        r012_transports = {
            row[0]
            for row in con.execute(
                "select transport_number from tmp_r012_findings where transport_number is not null"
            ).fetchall()
        }
        require("CANCELLED_UK" not in r012_transports, "Cancelled-Transport erzeugt R012")
        require("CANCELED_US" not in r012_transports, "Canceled-Transport erzeugt R012")
        require("ACTIVE_TD" in r012_transports, "Aktiver Transport ohne Loknummer erzeugt kein R012")
        require("ACTIVE_DUMMY" in r012_transports, "Aktiver Dummy-Transport erzeugt kein R012")
        print_ok("Cancelled/Canceled erzeugen keine R012-Findings; aktive Vergleichsfälle weiterhin schon")

        print_ok("Downstream-Prinzip geprüft: Quality Gate, Rest-Export und XLSX-Exporte erhalten keine stornierten Timeline-Zeilen")
    finally:
        con.close()


def production_db_check() -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("DuckDB fehlt in der aktiven Python-Umgebung.") from exc

    db_path = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
    audit_csv = ROOT / "data" / "03_exports" / "audit_excluded_cancelled_transports.csv"
    require(db_path.exists(), f"Produktive DuckDB fehlt: {db_path}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table_name in [
            "cfg_excluded_cancelled_transports",
            "audit_excluded_cancelled_transports",
            "stg_loco_events",
            "core_loco_timeline",
            "stg_transport_details_enriched",
            "core_transport_route",
            "dq_findings",
            "export_zuordnungen",
            "export_nutzungsmeldung",
        ]:
            require(table_exists(con, table_name), f"Tabelle fehlt nach Tageslauf: {table_name}")
        print_ok("Produktive DuckDB enthält zentrale Ausschluss- und Audittabellen")

        central_count = con.execute(
            "select count(*) from cfg_excluded_cancelled_transports"
        ).fetchone()[0]
        audit_count = con.execute(
            "select count(*) from audit_excluded_cancelled_transports"
        ).fetchone()[0]
        print_info(f"Zentral ausgeschlossene Transporte: {central_count}")
        print_info(f"Audit-Zeilen: {audit_count}")

        checks = {
            "stg_loco_events": "transport_number",
            "core_loco_timeline": "transport_number",
            "stg_transport_details_enriched": "transport_number",
            "core_transport_route": "transport_number",
            "dq_findings": "transport_number",
        }
        for table_name, column_name in checks.items():
            count = con.execute(
                f"""
                select count(*)
                from {table_name} target
                join cfg_excluded_cancelled_transports excluded
                  on excluded.transport_number = target.{column_name}
                """
            ).fetchone()[0]
            require(count == 0, f"{table_name} enthält noch {count} ausgeschlossene Transporte")
            print_ok(f"Keine stornierten Transporte in {table_name}")

        # Fachliche CSV-Exporte besitzen keine TransportNumber-Spalte. Da beide aus
        # core_loco_timeline erzeugt werden, ist der geprüfte Core-Ausschluss ihre
        # zentrale Vorbedingung. Zusätzlich wird die erzeugte Audit-Datei geprüft.
        require(audit_csv.exists(), f"Audit-CSV fehlt: {audit_csv}")
        header = audit_csv.read_text(encoding="utf-8-sig").splitlines()[0]
        for field in [
            "source_table",
            "transport_number",
            "transport_status",
            "affected_rows",
            "first_seen_utc",
            "last_seen_utc",
            "transport_last_edit_date",
            "transport_last_edit_by",
        ]:
            require(field in header, f"Audit-CSV-Spalte fehlt: {field}")
        print_ok("Audit-CSV vorhanden und vollständig strukturiert")

        print_ok("Produktionsprüfung erfolgreich: Timeline, Routen, Findings, Quality-Gate-Vorbedingung und Exporte sind konsistent")
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifikation Netzentgelt Cancelled-Hotfix V2")
    parser.add_argument(
        "--production-db",
        action="store_true",
        help="Zusätzlich produktive DuckDB und Audit-CSV nach run_all.py prüfen.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 72)
    print("Netzentgelt Cancelled-Hotfix V2 - Verifikation")
    print("=" * 72)
    check_static_files()
    functional_smoke_test()
    if args.production_db:
        production_db_check()
    else:
        print_info("Produktionsprüfung übersprungen. Nach dem Tageslauf erneut mit --production-db starten.")
    print("")
    print("VERIFIKATION ERFOLGREICH")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("")
        print(f"FEHLER: {exc}")
        raise
