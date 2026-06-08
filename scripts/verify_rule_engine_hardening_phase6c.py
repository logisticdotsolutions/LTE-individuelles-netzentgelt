from __future__ import annotations

# NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_V1_20260608

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
            "core_usage_assignment_segment_movements",
            "core_usage_assignment_segments",
            "core_loco_stand_candidates",
            "dq_phase6c_uncertain_gaps",
            "dq_phase6c_gap_context_review",
            "dq_rule_engine_hardening_phase6c_audit",
        ]
        missing = [name for name in required if not table_exists(con, name)]
        if missing:
            raise RuntimeError("Fehlende Phase-6C-Tabellen: " + ", ".join(missing))

        old_overlap_without_r011 = scalar(con, """
            with movements as (
                select row_number() over () as rn, *
                from core_loco_timeline
                where row_type='MOVEMENT' and report_scope='IN_REPORT'
                  and period_start_utc is not null and period_end_utc is not null
                  and period_end_utc > period_start_utc
                  and period_start_utc <= (select max(error_cutoff_utc) from dq_run_metadata)
            ), pairs as (
                select a.loco_no, a.source_table as sta, a.source_row_id as sra,
                       b.source_table as stb, b.source_row_id as srb
                from movements a join movements b
                  on b.loco_no=a.loco_no and b.rn>a.rn
                 and a.period_start_utc < b.period_end_utc
                 and b.period_start_utc < a.period_end_utc
            )
            select count(*) from pairs p
            where not exists (
                select 1 from dq_findings f
                where f.rule_id='R011' and f.loco_no=p.loco_no
                  and ((f.source_table is not distinct from p.sta and f.source_row_id is not distinct from p.sra)
                    or (f.source_table is not distinct from p.stb and f.source_row_id is not distinct from p.srb))
            )
        """)

        unsafe_gap_hard_findings = scalar(con, """
            select count(*)
            from dq_findings f
            join core_loco_timeline g
              on g.row_type='GAP'
             and g.loco_no is not distinct from f.loco_no
             and g.source_table is not distinct from f.source_table
             and g.source_row_id is not distinct from f.source_row_id
            where f.rule_id in ('R010','R010.5')
              and coalesce(g.gap_time_basis_safe,false)=false
        """)

        td_dummy_without_r012 = scalar(con, """
            select count(*)
            from (
                select distinct trim(cast(TransportNumber as varchar)) as transport_number
                from raw_transportdetail
                where trim(coalesce(cast(FirstLocomotiveNo as varchar),''))='00000000000-0'
                  and lower(coalesce(cast(MovementType as varchar),''))='train movement'
                  and (upper(coalesce(cast(OriginCountryISO as varchar),''))='DE'
                    or upper(coalesce(cast(DestinationCountryISO as varchar),''))='DE')
            ) d
            where not exists (
                select 1 from dq_findings f
                where f.rule_id='R012' and f.source_table='raw_transportdetail'
                  and f.transport_number is not distinct from d.transport_number
            )
        """)

        segment_outside_scope = scalar(con, """
            select count(*)
            from core_usage_assignment_segments s
            join (
                select usage_segment_id, min(de_period_start_utc) as min_de, max(de_period_end_utc) as max_de
                from core_usage_assignment_segment_movements
                group by usage_segment_id
            ) m using (usage_segment_id)
            where s.segment_start_utc is distinct from m.min_de
               or s.segment_end_utc is distinct from m.max_de
        """)

        fresh_overlap_blocked = scalar(con, """
            select count(*)
            from dq_export_gate g
            where coalesce(g.overlap_minutes,0)>0
              and g.coverage_date > cast((select max(error_cutoff_utc) from dq_run_metadata) as date)
        """)

        audit_rows = scalar(con, "select count(*) from dq_rule_engine_hardening_phase6c_audit")
        segments = scalar(con, "select count(*) from core_usage_assignment_segments")
        stands = scalar(con, "select count(*) from core_loco_stand_candidates")
        uncertain = scalar(con, "select count(*) from dq_phase6c_uncertain_gaps")
        context_review = scalar(con, "select count(*) from dq_phase6c_gap_context_review")

        print("Phase-6C-Verifikation:")
        print(f"  Alte Overlaps ohne sichtbares R011: {old_overlap_without_r011}")
        print(f"  Unsichere GAPs mit harter R010/R010.5-Bewertung: {unsafe_gap_hard_findings}")
        print(f"  TransportDetail-Dummys ohne R012: {td_dummy_without_r012}")
        print(f"  DE-Segmente außerhalb ihrer DE-Grenzen: {segment_outside_scope}")
        print(f"  Frische Overlaps trotz 24h-Toleranz blockiert: {fresh_overlap_blocked}")
        print(f"  Zentrale DE-Segmente: {segments}")
        print(f"  Potenzielle kalte Abstellungen: {stands}")
        print(f"  Unsichere GAP-Prüffälle: {uncertain}")
        print(f"  Grenzkontext zur fachlichen Sichtung: {context_review}")
        print(f"  Phase-6C-Auditzeilen: {audit_rows}")

        errors=[]
        if old_overlap_without_r011: errors.append(f"alte-overlaps-ohne-r011={old_overlap_without_r011}")
        if unsafe_gap_hard_findings: errors.append(f"unsichere-gaps-hart-bewertet={unsafe_gap_hard_findings}")
        if td_dummy_without_r012: errors.append(f"td-dummys-ohne-r012={td_dummy_without_r012}")
        if segment_outside_scope: errors.append(f"segment-outside-scope={segment_outside_scope}")
        if fresh_overlap_blocked: errors.append(f"frische-overlaps-blockiert={fresh_overlap_blocked}")
        if segments == 0: errors.append("zentrale-segmente-fehlen")
        if audit_rows == 0: errors.append("phase6c-audit-fehlt")
        if errors:
            raise RuntimeError("Phase-6C-Verifikation fehlgeschlagen: " + " | ".join(errors))
        print("OK: Phase-6C-Verifikation erfolgreich.")
        return 0
    finally:
        con.close()

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FEHLER: {exc}")
        raise SystemExit(1)
