from __future__ import annotations

"""
Netzentgelt MVP - Rule Engine Diagnostic Phase 6A
NETZENTGELT_PHASE6D_VERIFY_HOTFIX_V1_20260608
NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6D_V1_20260608
=================================================

Read-only diagnostic for the current productive DuckDB database.

NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6B_V1_20260608
NETZENTGELT_RULE_ENGINE_HARDENING_PHASE6C_V1_20260608

The script does not alter the database, raw CSV files, mappings or exports. It
connects to DuckDB with read_only=True and writes a timestamped report folder
below data/04_logs.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


PHASE_ID = "NETZENTGELT_RULE_ENGINE_DIAGNOSTIC_PHASE6A_V1_20260608"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "02_duckdb" / "netzentgelt.duckdb"
DEFAULT_RAW_DIR = ROOT / "data" / "00_raw"
DEFAULT_LOG_DIR = ROOT / "data" / "04_logs"
LATEST_POINTER = DEFAULT_LOG_DIR / "rule_engine_diagnostic_phase6a_latest.txt"


@dataclass
class CheckResult:
    check_id: str
    priority: str
    title: str
    status: str
    row_count: int
    description: str
    detail_file: str


class DiagnosticContext:
    def __init__(self, con, output_dir: Path, raw_dir: Path) -> None:
        self.con = con
        self.output_dir = output_dir
        self.raw_dir = raw_dir
        self.results: list[CheckResult] = []
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def add_result(
        self,
        *,
        check_id: str,
        priority: str,
        title: str,
        status: str,
        row_count: int,
        description: str,
        detail_file: str = "",
    ) -> None:
        self.results.append(
            CheckResult(
                check_id=check_id,
                priority=priority,
                title=title,
                status=status,
                row_count=int(row_count or 0),
                description=description,
                detail_file=detail_file,
            )
        )

    def write_detail(self, check_id: str, columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
        file_name = f"{check_id.lower()}_details.csv"
        path = self.output_dir / file_name
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(list(columns))
            writer.writerows(rows)
        return file_name


def qident(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def sql_lit(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def normalize_company_sql(expression: str) -> str:
    return f"""
        regexp_replace(
            lower(
                replace(
                    replace(
                        replace(
                            replace(coalesce(cast({expression} as varchar), ''), 'ä', 'ae'),
                            'ö', 'oe'
                        ),
                        'ü', 'ue'
                    ),
                    'ß', 'ss'
                )
            ),
            '[^a-z0-9]+',
            '',
            'g'
        )
    """


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


def columns(con, table_name: str) -> list[str]:
    if not table_exists(con, table_name):
        return []
    return [row[0] for row in con.execute(f"describe {qident(table_name)}").fetchall()]


def pick_column(available: Iterable[str], candidates: Iterable[str]) -> str | None:
    by_lower = {str(column).lower(): str(column) for column in available}
    for candidate in candidates:
        actual = by_lower.get(str(candidate).lower())
        if actual:
            return actual
    return None


def fetch_rows(con, sql: str, params: Sequence[object] | None = None) -> tuple[list[str], list[tuple]]:
    cursor = con.execute(sql, list(params or []))
    names = [description[0] for description in cursor.description]
    return names, cursor.fetchall()


def require(ctx: DiagnosticContext, check_id: str, priority: str, title: str, tables: Sequence[str]) -> bool:
    missing = [table for table in tables if not table_exists(ctx.con, table)]
    if not missing:
        return True
    ctx.add_result(
        check_id=check_id,
        priority=priority,
        title=title,
        status="SKIPPED",
        row_count=0,
        description="Diagnose nicht ausführbar. Fehlende Tabellen: " + ", ".join(missing),
    )
    return False


def run_sql_check(
    ctx: DiagnosticContext,
    *,
    check_id: str,
    priority: str,
    title: str,
    description: str,
    sql: str,
    params: Sequence[object] | None = None,
    required_tables: Sequence[str] = (),
    status_if_rows: str = "FINDING",
) -> None:
    if not require(ctx, check_id, priority, title, required_tables):
        return
    try:
        names, rows = fetch_rows(ctx.con, sql, params)
        detail_file = ctx.write_detail(check_id, names, rows)
        ctx.add_result(
            check_id=check_id,
            priority=priority,
            title=title,
            status=status_if_rows if rows else "OK",
            row_count=len(rows),
            description=description,
            detail_file=detail_file,
        )
    except Exception as exc:  # diagnostic must continue and report the failed probe
        ctx.add_result(
            check_id=check_id,
            priority=priority,
            title=title,
            status="ERROR",
            row_count=0,
            description=f"Diagnoseabfrage fehlgeschlagen: {exc}",
        )


def run_static_risk(
    ctx: DiagnosticContext,
    *,
    check_id: str,
    priority: str,
    title: str,
    description: str,
) -> None:
    detail_file = ctx.write_detail(check_id, ["risk"], [(description,)])
    ctx.add_result(
        check_id=check_id,
        priority=priority,
        title=title,
        status="RISK",
        row_count=1,
        description=description,
        detail_file=detail_file,
    )


def check_mapping_overlap(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D001",
        priority="P0",
        title="Mehrfach aktive Lok-Mappings mit überlappender Gültigkeit",
        description=(
            "Mehrere aktive Mapping-Zeilen derselben Lok können Bewegungen im Core vervielfachen. "
            "Das erzeugt künstliche Überschneidungen, GAPs und Exportzeilen."
        ),
        required_tables=["cfg_loco_mapping"],
        sql="""
            with active as (
                select
                    row_number() over () as mapping_row_no,
                    nullif(trim(loco_no), '') as loco_no,
                    nullif(trim(tfze_or_tens), '') as tfze_or_tens,
                    nullif(trim(halter_name), '') as halter_name,
                    nullif(trim(default_vens), '') as default_vens,
                    try_cast(replace(nullif(trim(valid_from_utc), ''), 'Z', '') as timestamp) as valid_from,
                    try_cast(replace(nullif(trim(valid_to_utc), ''), 'Z', '') as timestamp) as valid_to,
                    nullif(trim(priority), '') as priority,
                    nullif(trim(source), '') as source
                from cfg_loco_mapping
                where upper(trim(coalesce(active_flag, 'Y'))) not in ('N', 'NO', 'FALSE', '0')
                  and nullif(trim(loco_no), '') is not null
            )
            select
                a.loco_no,
                a.mapping_row_no as mapping_row_a,
                b.mapping_row_no as mapping_row_b,
                a.tfze_or_tens as tfze_a,
                b.tfze_or_tens as tfze_b,
                a.halter_name as holder_a,
                b.halter_name as holder_b,
                a.default_vens as default_vens_a,
                b.default_vens as default_vens_b,
                a.valid_from as valid_from_a,
                a.valid_to as valid_to_a,
                b.valid_from as valid_from_b,
                b.valid_to as valid_to_b,
                a.priority as priority_a,
                b.priority as priority_b,
                a.source as source_a,
                b.source as source_b
            from active a
            join active b
              on b.loco_no = a.loco_no
             and b.mapping_row_no > a.mapping_row_no
             and coalesce(a.valid_to, timestamp '9999-12-31') > coalesce(b.valid_from, timestamp '1900-01-01')
             and coalesce(b.valid_to, timestamp '9999-12-31') > coalesce(a.valid_from, timestamp '1900-01-01')
            order by a.loco_no, a.mapping_row_no, b.mapping_row_no
        """,
    )


def check_core_join_multiplication(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D002",
        priority="P0",
        title="Vervielfachte Movement-Zeilen im Core",
        description=(
            "Eine importierte Movement-Zeile darf im Core nur einmal vorkommen. Mehrfachtreffer deuten "
            "auf Join-Multiplikation oder nicht eindeutige Mappings hin."
        ),
        required_tables=["core_loco_timeline"],
        sql="""
            select
                source_table,
                source_row_id,
                loco_no,
                transport_number,
                period_start_utc,
                period_end_utc,
                count(*) as duplicated_core_rows
            from core_loco_timeline
            where row_type = 'MOVEMENT'
            group by source_table, source_row_id, loco_no, transport_number, period_start_utc, period_end_utc
            having count(*) > 1
            order by duplicated_core_rows desc, loco_no, source_row_id
        """,
    )


def check_hidden_blocked_days(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D003",
        priority="P0",
        title="Gesperrte Lok-Tage ohne sichtbaren blockierenden Prüffall",
        description=(
            "Der Controller muss für jede Sperre einen bearbeitbaren Grund sehen. Diese Lok-Tage sind BLOCKED, "
            "obwohl weder ERROR, MANUAL_REVIEW, echte Überschneidung noch langes GAP ausgewiesen werden."
        ),
        required_tables=["dq_export_gate"],
        sql="""
            select *
            from dq_export_gate
            where gate_status = 'BLOCKED'
              and coalesce(error_findings, 0) = 0
              and coalesce(manual_review_findings, 0) = 0
              and coalesce(overlap_minutes, 0) = 0
              and coalesce(long_gap_rows, 0) = 0
            order by coverage_date desc, loco_no
        """,
    )


def check_export_false_without_findings(ctx: DiagnosticContext) -> None:
    run_sql_check(ctx, check_id="D004", priority="P0",
        title="Blockierende Bewegungen ohne nachvollziehbares Finding",
        description="Nur export_blocking=true ist ein harter Sperrfall. Junge tolerierte INFO-Zeilen werden nicht mehr fälschlich gemeldet.",
        required_tables=["core_loco_timeline", "dq_findings"], sql="""
            select c.* from core_loco_timeline c
            where c.row_type='MOVEMENT' and c.report_scope='IN_REPORT'
              and coalesce(c.export_blocking,false)=true
              and not exists (select 1 from dq_findings f where f.severity in ('ERROR','MANUAL_REVIEW')
                and f.source_table is not distinct from c.source_table and f.source_row_id is not distinct from c.source_row_id)
            order by c.loco_no, c.period_start_utc
        """)



def check_holder_mapping_mismatch(ctx: DiagnosticContext) -> None:
    holder_norm = normalize_company_sql("c.holder_name")
    run_sql_check(
        ctx,
        check_id="D005",
        priority="P0",
        title="Halter-Marktpartner-ID weicht von der Halterauflösung ab",
        description=(
            "Die ANE-tEns-ID des Halters muss anhand des Halternamens ermittelt werden. Abweichungen weisen auf "
            "eine Ableitung anhand des nutzenden EVU oder auf inkonsistente Mappingdaten hin."
        ),
        required_tables=[
            "core_loco_timeline",
            "cfg_market_partner_mapping_effective",
            "cfg_market_partner_role_effective",
        ],
        sql=f"""
            with resolved as (
                select
                    c.loco_no,
                    c.transport_number,
                    c.period_start_utc,
                    c.period_end_utc,
                    c.performing_ru,
                    c.holder_name,
                    c.holder_market_partner_id as core_holder_market_partner_id,
                    coalesce(m.market_partner_id, r.market_partner_id) as expected_holder_market_partner_id,
                    c.source_table,
                    c.source_row_id
                from core_loco_timeline c
                left join cfg_market_partner_mapping_effective m
                  on m.role_code = 'ANE_TENS'
                 and m.source_value_normalized = {holder_norm}
                left join cfg_market_partner_role_effective r
                  on r.role_code = 'ANE_TENS'
                 and r.company_name_normalized = {holder_norm}
                where c.row_type = 'MOVEMENT'
                  and c.report_scope = 'IN_REPORT'
                  and nullif(trim(c.holder_name), '') is not null
            )
            select *
            from resolved
            where expected_holder_market_partner_id is not null
              and core_holder_market_partner_id is distinct from expected_holder_market_partner_id
            order by loco_no, period_start_utc, source_row_id
        """,
    )


def check_actual_overlap_without_r011(ctx: DiagnosticContext) -> None:
    run_sql_check(ctx, check_id="D006", priority="P0", title="Alte echte Überschneidungen ohne R011-Finding",
        description="Nur Überschneidungen vor dem 24h-Cutoff müssen bereits als R011 sichtbar sein.",
        required_tables=["core_loco_timeline","dq_findings","dq_run_metadata"], sql="""
            with m as (select row_number() over () rn,* from core_loco_timeline
                where row_type='MOVEMENT' and report_scope='IN_REPORT' and period_start_utc is not null and period_end_utc is not null
                  and period_end_utc>period_start_utc and period_start_utc <= (select max(error_cutoff_utc) from dq_run_metadata)),
            p as (select a.loco_no,a.source_table sta,a.source_row_id sra,b.source_table stb,b.source_row_id srb
                from m a join m b on b.loco_no=a.loco_no and b.rn>a.rn and a.period_start_utc<b.period_end_utc and b.period_start_utc<a.period_end_utc)
            select * from p where not exists (select 1 from dq_findings f where f.rule_id='R011' and f.loco_no=p.loco_no
              and ((f.source_table is not distinct from p.sta and f.source_row_id is not distinct from p.sra)
                or (f.source_table is not distinct from p.stb and f.source_row_id is not distinct from p.srb)))
        """)



def check_r011_without_actual_overlap(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D007",
        priority="P0",
        title="R011-Findings ohne echte Überschneidung",
        description=(
            "Jedes R011-Finding muss durch eine tatsächliche Intervallschnittmenge erklärbar sein. Diese Treffer sind "
            "potenzielle Fehlalarme oder veraltete Findings."
        ),
        required_tables=["core_loco_timeline", "dq_findings"],
        sql="""
            select
                f.loco_no,
                f.transport_number,
                f.period_start_utc,
                f.period_end_utc,
                f.message,
                f.source_table,
                f.source_row_id
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
            order by f.loco_no, f.period_start_utc
        """,
    )


def check_uncertain_gap_duration(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D008",
        priority="P1",
        title="Unsichere Unterbrechungen ohne belastbare Zeitgrenzen",
        description=(
            "Phase 6C bewertet diese Faelle bewusst nicht automatisch. Sie bleiben als R015-Pruefliste sichtbar, "
            "bis fehlende Zeitwerte in RailCube ergaenzt oder fachlich bewertet wurden."
        ),
        required_tables=["dq_phase6c_uncertain_gaps"],
        status_if_rows="REVIEW",
        sql="""
            select *
            from dq_phase6c_uncertain_gaps
            order by loco_no, approximate_gap_start_utc, source_row_id
        """,
    )


def check_non_de_gap_findings(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D009",
        priority="P0",
        title="Nicht DE-relevante GAPs besitzen Findings",
        description=(
            "Nur GAPs mit gap_relevant_de=true dürfen operative Findings erzeugen. Treffer deuten auf veraltete oder "
            "inkonsistente Regelresultate hin."
        ),
        required_tables=["core_loco_timeline", "dq_findings"],
        sql="""
            select
                f.rule_id,
                f.severity,
                f.loco_no,
                f.transport_number,
                f.period_start_utc,
                f.period_end_utc,
                f.message,
                c.gap_relevant_de,
                f.source_table,
                f.source_row_id
            from dq_findings f
            join core_loco_timeline c
              on c.row_type = 'GAP'
             and c.loco_no is not distinct from f.loco_no
             and c.source_table is not distinct from f.source_table
             and c.source_row_id is not distinct from f.source_row_id
             and c.period_start_utc is not distinct from f.period_start_utc
             and c.period_end_utc is not distinct from f.period_end_utc
            where f.row_type = 'GAP'
              and coalesce(c.gap_relevant_de, false) = false
            order by f.loco_no, f.period_start_utc
        """,
    )


def check_gap_cockpit_duplicates(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D010",
        priority="P1",
        title="Mehrfach erzeugte GAP-Findings",
        description=(
            "Phase 6B dedupliziert die Cockpit-Anzeige. Verbleibende Treffer bedeuten, dass fuer dieselbe "
            "fachliche Unterbrechung mehrfach atomare GAP-Findings erzeugt wurden."
        ),
        required_tables=["dq_findings"],
        sql="""
            select
                loco_no,
                transport_number,
                period_start_utc,
                period_end_utc,
                source_table,
                source_row_id,
                count(*) as duplicate_finding_rows,
                string_agg(distinct rule_id, ' | ' order by rule_id) as rule_ids
            from dq_findings
            where row_type = 'GAP'
            group by
                loco_no, transport_number, period_start_utc, period_end_utc,
                source_table, source_row_id
            having count(*) > 1
            order by duplicate_finding_rows desc, loco_no, period_start_utc
        """,
    )



def _count_csv_rows(path: Path) -> tuple[int | None, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            sample = handle.read(8192)
            handle.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
            except csv.Error:
                dialect = csv.excel
                dialect.delimiter = ";"
            reader = csv.reader(handle, dialect)
            row_count = sum(1 for _ in reader)
        return max(row_count - 1, 0), ""
    except Exception as exc:
        return None, str(exc)


def check_raw_import_row_counts(ctx: DiagnosticContext) -> None:
    check_id = "D011"
    title = "Rohdatenzeilen und importierte DuckDB-Zeilen weichen ab"
    if not require(ctx, check_id, "P0", title, ["raw_import_run"]):
        return
    try:
        names, rows = fetch_rows(
            ctx.con,
            """
                select source_file, target_table, row_count, imported_at_utc
                from raw_import_run
                where status = 'imported'
                qualify row_number() over (
                    partition by lower(source_file)
                    order by try_cast(imported_at_utc as timestamp) desc nulls last
                ) = 1
                order by lower(source_file)
            """,
        )
        details = []
        for source_file, target_table, imported_rows, imported_at_utc in rows:
            physical_rows, error = _count_csv_rows(ctx.raw_dir / str(source_file))
            difference = None if physical_rows is None else int(physical_rows) - int(imported_rows or 0)
            details.append(
                (
                    source_file,
                    target_table,
                    imported_at_utc,
                    physical_rows,
                    imported_rows,
                    difference,
                    error,
                )
            )
        detail_file = ctx.write_detail(
            check_id,
            [
                "source_file",
                "target_table",
                "imported_at_utc",
                "physical_csv_data_rows",
                "duckdb_imported_rows",
                "difference",
                "count_error",
            ],
            details,
        )
        suspicious = [row for row in details if row[5] not in (0, None) or row[6]]
        ctx.add_result(
            check_id=check_id,
            priority="P0",
            title=title,
            status="FINDING" if suspicious else "OK",
            row_count=len(suspicious),
            description=(
                "Der Import verwendet derzeit ignore_errors=true. Unterschiede zwischen physischen CSV-Zeilen und "
                "DuckDB-Zeilen können auf still verworfene Rohdaten hinweisen."
            ),
            detail_file=detail_file,
        )
    except Exception as exc:
        ctx.add_result(
            check_id=check_id,
            priority="P0",
            title=title,
            status="ERROR",
            row_count=0,
            description=f"Diagnoseabfrage fehlgeschlagen: {exc}",
        )


def check_foreign_segment_expansion(ctx: DiagnosticContext) -> None:
    run_sql_check(ctx, check_id="D012", priority="P1", title="Zentrale Segmente reichen über ihre DE-Grenzen hinaus",
        description="Phase 6C verwendet core_usage_assignment_segments als zentrale DE-begrenzte Wahrheit.",
        required_tables=["core_usage_assignment_segments","core_usage_assignment_segment_movements"], sql="""
            select s.* from core_usage_assignment_segments s join (
              select usage_segment_id,min(de_period_start_utc) min_de,max(de_period_end_utc) max_de
              from core_usage_assignment_segment_movements group by usage_segment_id
            ) m using(usage_segment_id)
            where s.segment_start_utc is distinct from m.min_de or s.segment_end_utc is distinct from m.max_de
        """)



def check_invisible_same_place_stands(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D013",
        priority="P1",
        title="Mögliche kalte Abstellungen zur fachlichen Sichtung",
        description=(
            "Phase 6C stellt lange Standzeiten am selben DE-Ort strukturiert bereit. Die Liste ist eine fachliche "
            "Pruefqueue und kein Fehler der Regelengine."
        ),
        required_tables=["core_loco_stand_candidates"],
        status_if_rows="REVIEW",
        sql="""
            select *
            from core_loco_stand_candidates
            order by stand_duration_minutes desc, loco_no, stand_from_utc
        """,
    )


def check_unsupported_gap_transitions(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D014",
        priority="P1",
        title="Grenzkontext-Fälle zur fachlichen Sichtung",
        description=(
            "Phase 6C klassifiziert diese gebrochenen Ortsketten auditierbar als Grenzkontext. Sie werden nicht "
            "automatisch als DE-interner GAP-Fehler bewertet."
        ),
        required_tables=["dq_phase6c_gap_context_review"],
        status_if_rows="REVIEW",
        sql="""
            select *
            from dq_phase6c_gap_context_review
            order by loco_no, actual_arrival_ts, source_row_id
        """,
    )


def check_cutoff_bypass(ctx: DiagnosticContext) -> None:
    run_sql_check(ctx, check_id="D015", priority="P0", title="24h-Cutoff wird durch harte Sperren umgangen",
        description="Junge unvollständige Bewegungen dürfen export_ready=false sein, aber noch nicht export_blocking=true.",
        required_tables=["core_loco_timeline","dq_run_metadata"], sql="""
          select c.* from core_loco_timeline c cross join (select max(error_cutoff_utc) cutoff from dq_run_metadata) x
          where c.row_type='MOVEMENT' and c.report_scope='IN_REPORT' and coalesce(c.export_blocking,false)=true
            and coalesce(c.period_start_utc,c.period_end_utc,c.sequence_ts)>x.cutoff
        """)



def check_r012_transportdetail_asymmetry(ctx: DiagnosticContext) -> None:
    check_id = "D016"
    title = "TransportDetail-R012 erkennt technische Dummy-Loks nicht symmetrisch"
    if not require(ctx, check_id, "P1", title, ["raw_transportdetail"]):
        return
    available = columns(ctx.con, "raw_transportdetail")
    loco_col = pick_column(available, ["FirstLocomotiveNo", "LocomotiveNo", "Alias"])
    transport_col = pick_column(available, ["TransportNumber", "TransportNo", "TransportId", "TransportID"])
    origin_col = pick_column(available, ["OriginCountryISO", "OriginCountryIso", "OriginCountry", "FromCountryISO", "FromCountry"])
    destination_col = pick_column(available, ["DestinationCountryISO", "DestinationCountryIso", "DestinationCountry", "ToCountryISO", "ToCountry"])
    country_col = pick_column(available, ["Country"])
    if not loco_col or not transport_col:
        ctx.add_result(
            check_id=check_id,
            priority="P1",
            title=title,
            status="SKIPPED",
            row_count=0,
            description="TransportDetail besitzt keine auswertbare Lok- oder Transportnummernspalte.",
        )
        return
    if origin_col or destination_col:
        de_expr = (
            f"upper(coalesce(cast({qident(origin_col)} as varchar), '')) = 'DE'" if origin_col else "false"
        ) + " or " + (
            f"upper(coalesce(cast({qident(destination_col)} as varchar), '')) = 'DE'" if destination_col else "false"
        )
    elif country_col:
        de_expr = f"upper(coalesce(cast({qident(country_col)} as varchar), '')) = 'DE'"
    else:
        de_expr = "false"
    run_sql_check(
        ctx,
        check_id=check_id,
        priority="P1",
        title=title,
        description=(
            "LocomotiveMovement erkennt Dummy-Loks, TransportDetail prüft derzeit nur fehlende FirstLocomotiveNo. "
            "Diese DE-relevanten TransportDetail-Zeilen enthalten technische Dummy-Werte."
        ),
        required_tables=["raw_transportdetail"],
        sql=f"""
            select
                nullif(trim(cast({qident(transport_col)} as varchar)), '') as transport_number,
                nullif(trim(cast({qident(loco_col)} as varchar)), '') as first_loco_no
            from raw_transportdetail
            where ({de_expr})
              and (
                    trim(cast({qident(loco_col)} as varchar)) = '00000000000-0'
                 or upper(trim(cast({qident(loco_col)} as varchar))) like '%DUMMY%'
              )
              and not exists (
                    select 1 from dq_findings f
                    where f.rule_id = 'R012'
                      and f.source_table = 'raw_transportdetail'
                      and f.transport_number is not distinct from nullif(trim(cast({qident(transport_col)} as varchar)), '')
              )
            order by transport_number
        """,
    )


def check_source_row_identity(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D017",
        priority="P1",
        title="Core besitzt keine stabile fachliche Rohdatenidentität",
        description=(
            "source_row_id wird aus row_number() ohne stabile Sortierung erzeugt. Dieser Check zeigt, ob ergänzende "
            "stabile Hash- oder Zeilennummernspalten bereits vorhanden sind. Fehlen sie, bleibt ein strukturelles Auditrisiko."
        ),
        required_tables=["core_loco_timeline"],
        status_if_rows="RISK",
        sql="""
            select
                column_name
            from information_schema.columns
            where lower(table_name) = 'core_loco_timeline'
              and lower(column_name) in ('source_row_hash', 'source_line_number', 'source_file_line_no', 'source_record_hash')
            order by column_name
        """,
    )
    # Invert semantics: existing stable columns are good. Replace latest result if none exist.
    latest = ctx.results[-1]
    if latest.check_id == "D017":
        if latest.row_count == 0 and latest.status == "OK":
            latest.status = "RISK"
            latest.description = (
                "Keine stabile Hash- oder Dateizeilenidentität im Core gefunden. source_row_id basiert derzeit auf "
                "row_number() ohne deterministische Sortierung und kann sich nach Neuimporten verschieben."
            )
        elif latest.row_count > 0:
            latest.status = "OK"
            latest.description = "Mindestens eine stabile Rohdatenidentität ist im Core vorhanden."


def check_global_blocker_scope(ctx: DiagnosticContext) -> None:
    run_sql_check(
        ctx,
        check_id="D018",
        priority="P2",
        title="Globale Tagesblocker sperren sämtliche RUs eines Meldetags",
        description=(
            "Dies ist eine konservative MVP-Entscheidung. Der Bericht zeigt vorhandene globale Blocker, damit fachlich "
            "entschieden werden kann, ob später je Lok, RU, Segment oder Meldetag gesperrt werden soll."
        ),
        required_tables=["dq_global_export_blockers"],
        status_if_rows="REVIEW",
        sql="""
            select blocker_date, rule_id, severity, row_type, transport_number, performing_ru, message
            from dq_global_export_blockers
            order by blocker_date desc, rule_id, transport_number
        """,
    )


def check_exact_overlap_rounding(ctx: DiagnosticContext) -> None:
    check_id = "D019"
    title = "Exakte Überschneidungsminuten zusätzlich zu Viertelstunden-Slots vorhanden"
    if not require(ctx, check_id, "P2", title, ["dq_export_gate"]):
        return
    available = {column.lower() for column in columns(ctx.con, "dq_export_gate")}
    if "exact_overlap_minutes" not in available or "exact_overlap_seconds" not in available:
        detail = ctx.write_detail(check_id, ["missing_columns"], [("exact_overlap_seconds | exact_overlap_minutes",)])
        ctx.add_result(
            check_id=check_id,
            priority="P2",
            title=title,
            status="FINDING",
            row_count=1,
            description="Phase-6D-Spalten fuer die exakte Ueberschneidungsdauer fehlen im Quality Gate.",
            detail_file=detail,
        )
        return
    run_sql_check(
        ctx,
        check_id=check_id,
        priority="P2",
        title=title,
        description=(
            "Die konservative Slotzahl bleibt erhalten. Zusaetzlich muss fuer jeden Overlap-Lok-Tag eine exakte "
            "Dauer in Sekunden und Minuten vorliegen."
        ),
        required_tables=["dq_export_gate"],
        sql="""
            select *
            from dq_export_gate
            where coalesce(overlap_minutes, 0) > 0
              and exact_overlap_minutes is null
            order by coverage_date desc, loco_no
        """,
    )


def check_info_blocking_movements(ctx: DiagnosticContext) -> None:
    run_sql_check(ctx, check_id="D020", priority="P0", title="INFO-Sachverhalte blockieren indirekt den Export",
        description="Nur harte export_blocking-Zeilen ohne ERROR oder MANUAL_REVIEW sind inkonsistent.",
        required_tables=["core_loco_timeline","dq_findings"], sql="""
          select c.* from core_loco_timeline c
          where c.row_type='MOVEMENT' and c.report_scope='IN_REPORT' and coalesce(c.export_blocking,false)=true
            and not exists (select 1 from dq_findings f where f.severity in ('ERROR','MANUAL_REVIEW')
              and f.source_table is not distinct from c.source_table and f.source_row_id is not distinct from c.source_row_id)
        """)



def write_inventory(ctx: DiagnosticContext) -> None:
    names, rows = fetch_rows(
        ctx.con,
        """
            select table_name, table_type
            from information_schema.tables
            where table_schema = 'main'
            order by table_name
        """,
    )
    ctx.write_detail("inventory_tables", names, rows)


def write_summary(ctx: DiagnosticContext, metadata: dict[str, object]) -> None:
    summary_path = ctx.output_dir / "summary.csv"
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["check_id", "priority", "title", "status", "row_count", "description", "detail_file"],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(asdict(result) for result in ctx.results)

    counts: dict[str, int] = {}
    for result in ctx.results:
        counts[result.status] = counts.get(result.status, 0) + 1

    report_lines = [
        "# Rule Engine Diagnostic Phase 6A",
        "",
        f"- Erstellt: `{metadata['created_at_utc']}`",
        f"- Phase: `{PHASE_ID}`",
        f"- Datenbank: `{metadata['db_path']}`",
        f"- Git HEAD: `{metadata.get('git_head') or 'nicht ermittelbar'}`",
        f"- Checks: `{len(ctx.results)}`",
        "",
        "## Statusübersicht",
        "",
    ]
    for status in sorted(counts):
        report_lines.append(f"- **{status}**: {counts[status]}")
    report_lines.extend([
        "",
        "## Prüfergebnisse",
        "",
        "| ID | Priorität | Status | Treffer | Prüfung | Detaildatei |",
        "|---|---:|---|---:|---|---|",
    ])
    for result in ctx.results:
        report_lines.append(
            f"| {result.check_id} | {result.priority} | {result.status} | {result.row_count} | "
            f"{result.title} | {result.detail_file or '-'} |"
        )
    report_lines.extend([
        "",
        "## Hinweise",
        "",
        "- `FINDING`: konkrete Daten- oder Logiktreffer wurden gefunden.",
        "- `RISK`: strukturelles Risiko ist im aktuellen Aufbau vorhanden.",
        "- `REVIEW`: fachliche Entscheidung für den späteren Zielzustand erforderlich.",
        "- `SKIPPED`: Diagnose konnte wegen fehlender Tabelle nicht ausgeführt werden.",
        "- `ERROR`: Diagnoseabfrage selbst ist fehlgeschlagen; Detailprüfung erforderlich.",
        "",
        "Die Diagnose hat die DuckDB ausschließlich lesend geöffnet. Es wurden keine Rohdaten, Mappings, Exporte oder DuckDB-Tabellen verändert.",
    ])
    (ctx.output_dir / "README_DIAGNOSTIC_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    payload = dict(metadata)
    payload["status_counts"] = counts
    payload["checks"] = [asdict(result) for result in ctx.results]
    (ctx.output_dir / "metadata.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def get_git_head(project_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def run_diagnostics(db_path: Path, raw_dir: Path, output_dir: Path) -> Path:
    try:
        import duckdb  # imported lazily so syntax and installer verification work without DuckDB
    except ImportError as exc:
        raise RuntimeError(
            "Python-Modul 'duckdb' fehlt. Bitte das Skript mit der Projekt-.venv ausführen."
        ) from exc

    if not db_path.exists():
        raise RuntimeError(f"DuckDB-Datei fehlt: {db_path}")

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        ctx = DiagnosticContext(con=con, output_dir=output_dir, raw_dir=raw_dir)
        write_inventory(ctx)
        check_mapping_overlap(ctx)
        check_core_join_multiplication(ctx)
        check_hidden_blocked_days(ctx)
        check_export_false_without_findings(ctx)
        check_holder_mapping_mismatch(ctx)
        check_actual_overlap_without_r011(ctx)
        check_r011_without_actual_overlap(ctx)
        check_uncertain_gap_duration(ctx)
        check_non_de_gap_findings(ctx)
        check_gap_cockpit_duplicates(ctx)
        check_raw_import_row_counts(ctx)
        check_foreign_segment_expansion(ctx)
        check_invisible_same_place_stands(ctx)
        check_unsupported_gap_transitions(ctx)
        check_cutoff_bypass(ctx)
        check_r012_transportdetail_asymmetry(ctx)
        check_source_row_identity(ctx)
        check_global_blocker_scope(ctx)
        check_exact_overlap_rounding(ctx)
        check_info_blocking_movements(ctx)
        run_sql_check(
            ctx,
            check_id="D021",
            priority="P1",
            title="Zentrale Segmenttabelle für CSV und XLSX vorhanden",
            description="Phase 6C verwendet core_usage_assignment_segments als gemeinsame fachliche Wahrheit.",
            required_tables=["core_usage_assignment_segments", "core_usage_assignment_segment_movements"],
            sql="""select * from core_usage_assignment_segments where segment_end_utc <= segment_start_utc""",
        )
        metadata = {
            "phase_id": PHASE_ID,
            "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "db_path": str(db_path.resolve()),
            "raw_dir": str(raw_dir.resolve()),
            "output_dir": str(output_dir.resolve()),
            "git_head": get_git_head(ROOT),
            "read_only": True,
        }
        write_summary(ctx, metadata)
        return output_dir
    finally:
        con.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Rule Engine Diagnostic Phase 6A")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir or (DEFAULT_LOG_DIR / f"rule_engine_diagnostic_phase6a_{stamp}")
    try:
        report_dir = run_diagnostics(
            db_path=args.db_path.resolve(),
            raw_dir=args.raw_dir.resolve(),
            output_dir=output_dir.resolve(),
        )
        DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        LATEST_POINTER.write_text(str(report_dir.resolve()), encoding="utf-8")
        print("=" * 72)
        print("Rule Engine Diagnostic Phase 6A abgeschlossen")
        print("=" * 72)
        print(f"Bericht: {report_dir}")
        print(f"Zusammenfassung: {report_dir / 'summary.csv'}")
        print(f"Lesbarer Bericht: {report_dir / 'README_DIAGNOSTIC_REPORT.md'}")
        print("DuckDB wurde ausschließlich lesend geöffnet. Keine Fachdaten wurden verändert.")
        return 0
    except Exception as exc:
        print(f"FEHLER: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
