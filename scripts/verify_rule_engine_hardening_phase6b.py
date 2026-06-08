from __future__ import annotations

# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6B_V1_20260608

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"


def table_exists(con, name: str) -> bool:
    return con.execute(
        "select count(*) from information_schema.tables where lower(table_name)=lower(?)",
        [name],
    ).fetchone()[0] > 0


def scalar(con, sql: str) -> int:
    return int(con.execute(sql).fetchone()[0] or 0)


def main() -> int:
    if not DB_PATH.exists():
        print(f"FEHLER: Produktive DuckDB fehlt: {DB_PATH}")
        return 1

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        required = [
            "core_loco_timeline",
            "dq_findings",
            "dq_run_metadata",
            "dq_export_gate",
            "dq_rule_engine_hardening_audit",
            "dq_rule_engine_hardening_blockers",
        ]
        missing = [name for name in required if not table_exists(con, name)]
        if missing:
            raise RuntimeError("Fehlende Phase-6B-Tabellen: " + ", ".join(missing))

        holder_mismatch = scalar(con, """
            with expected as (
                select
                    c.source_table,
                    c.source_row_id,
                    c.loco_no,
                    c.period_start_utc,
                    c.period_end_utc,
                    coalesce(
                        holder_mapping.market_partner_id,
                        holder_direct.market_partner_id,
                        nullif(trim(c.holder_name), '')
                    ) as expected_holder_market_partner_id
                from core_loco_timeline c
                left join cfg_market_partner_mapping_effective holder_mapping
                  on holder_mapping.role_code = 'ANE_TENS'
                 and holder_mapping.source_value_normalized = normalize_company_name(c.holder_name)
                left join cfg_market_partner_role_effective holder_direct
                  on holder_direct.role_code = 'ANE_TENS'
                 and holder_direct.company_name_normalized = normalize_company_name(c.holder_name)
                where c.row_type = 'MOVEMENT'
            )
            select count(*)
            from core_loco_timeline c
            join expected e
              on e.source_table is not distinct from c.source_table
             and e.source_row_id is not distinct from c.source_row_id
             and e.loco_no is not distinct from c.loco_no
             and e.period_start_utc is not distinct from c.period_start_utc
             and e.period_end_utc is not distinct from c.period_end_utc
            where c.row_type = 'MOVEMENT'
              and c.holder_market_partner_id is distinct from e.expected_holder_market_partner_id
        """)

        r011_without_overlap = scalar(con, """
            select count(*)
            from dq_findings f
            where f.rule_id = 'R011'
              and not exists (
                    select 1
                    from core_loco_timeline a
                    join core_loco_timeline b
                      on b.loco_no = a.loco_no
                     and not (
                            b.source_table is not distinct from a.source_table
                        and b.source_row_id is not distinct from a.source_row_id
                     )
                     and a.period_start_utc < b.period_end_utc
                     and b.period_start_utc < a.period_end_utc
                    where a.row_type = 'MOVEMENT'
                      and b.row_type = 'MOVEMENT'
                      and a.report_scope = 'IN_REPORT'
                      and b.report_scope = 'IN_REPORT'
                      and a.loco_no = f.loco_no
                      and a.source_table is not distinct from f.source_table
                      and a.source_row_id is not distinct from f.source_row_id
              )
        """)

        fresh_blocked = scalar(con, """
            select count(*)
            from core_loco_timeline c
            cross join (select max(error_cutoff_utc) as cutoff from dq_run_metadata) m
            where c.row_type = 'MOVEMENT'
              and c.report_scope = 'IN_REPORT'
              and coalesce(c.export_ready, false) = false
              and coalesce(c.export_blocking, false) = true
              and coalesce(c.period_start_utc, c.period_end_utc, c.sequence_ts) > m.cutoff
        """)

        hidden_blockers = scalar(con, """
            select count(*)
            from core_loco_timeline c
            where c.row_type = 'MOVEMENT'
              and c.report_scope = 'IN_REPORT'
              and coalesce(c.export_blocking, false) = true
              and not exists (
                    select 1 from dq_findings f
                    where f.source_table is not distinct from c.source_table
                      and f.source_row_id is not distinct from c.source_row_id
                      and f.severity in ('ERROR', 'MANUAL_REVIEW')
              )
              and not exists (
                    select 1 from dq_findings f
                    where f.rule_id = 'R012'
                      and f.transport_number is not distinct from c.transport_number
                      and f.severity = 'ERROR'
              )
        """)

        audit_rows = scalar(con, "select count(*) from dq_rule_engine_hardening_audit")
        blocker_rows = scalar(con, "select count(*) from dq_rule_engine_hardening_blockers")

        print("Phase-6B-Verifikation:")
        print(f"  Halter-ID-Abweichungen: {holder_mismatch}")
        print(f"  R011 ohne echte Intervallschnittmenge: {r011_without_overlap}")
        print(f"  Frische Bewegungen trotz 24h-Toleranz blockiert: {fresh_blocked}")
        print(f"  Unsichtbare blockierende Movements: {hidden_blockers}")
        print(f"  Audit-Zeilen: {audit_rows}")
        print(f"  Sichtbare blockierende Movements: {blocker_rows}")

        errors = []
        if holder_mismatch:
            errors.append(f"Halter-ID-Abweichungen={holder_mismatch}")
        if r011_without_overlap:
            errors.append(f"R011-ohne-Overlap={r011_without_overlap}")
        if fresh_blocked:
            errors.append(f"24h-Toleranz-Verletzungen={fresh_blocked}")
        if hidden_blockers:
            errors.append(f"unsichtbare-Blocker={hidden_blockers}")
        if audit_rows == 0:
            errors.append("Hardening-Audit fehlt")

        if errors:
            raise RuntimeError("Phase-6B-Verifikation fehlgeschlagen: " + " | ".join(errors))

        print("OK: Phase-6B-Verifikation erfolgreich.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER: {exc}")
        raise SystemExit(1)
