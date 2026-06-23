"""
Strukturvertragstest fuer Quality-Gate-Tabellen
================================================

Prueft statisch (Quellcode-Analyse), dass die Quality-Gate-Pipeline die
korrekte Tabellenstruktur und Ausführungsreihenfolge einhält.

Geschuetzte Invarianten:
- build_quality_gate_tables erzeugt alle Pflicht-Tabellen
- apply_r016_to_quality_gate_tables laeuft nach build_quality_gate_tables
- finalize_quality_gate_phase6d laeuft nach apply_r016
- dq_export_gate enthaelt READY/WARNING/BLOCKED-Status-Logik
- dq_global_export_blockers wird erzeugt
- export_excluded_rows wird erzeugt (fuer Audit)
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# quality_gate_module.py — Tabellenstruktur
# ---------------------------------------------------------------------------

def test_build_quality_gate_creates_required_tables():
    """
    build_quality_gate_tables muss alle Pflicht-Tabellen anlegen.
    """
    src = _src("scripts/quality_gate_module.py")
    required = [
        "core_loco_day_coverage",
        "dq_export_gate",
        "dq_export_gate_ru",
        "dq_global_export_blockers",
        "export_excluded_rows",
    ]
    for table in required:
        assert f"create or replace table {table}" in src, (
            f"Tabelle {table} fehlt in quality_gate_module.py. "
            "Sie ist Teil des Quality-Gate-Vertrags."
        )


def test_dq_export_gate_has_status_logic():
    """
    dq_export_gate muss READY, WARNING und BLOCKED als Status kennen.
    """
    src = _src("scripts/quality_gate_module.py")
    gate_pos = src.index("create or replace table dq_export_gate")
    gate_section = src[gate_pos: gate_pos + 8000]
    for status in ("READY", "WARNING", "BLOCKED"):
        assert status in gate_section, (
            f"Status '{status}' fehlt in dq_export_gate. "
            "Das Gate muss alle drei Statuswerte koennen."
        )


def test_dq_export_gate_ru_references_export_gate():
    """
    dq_export_gate_ru muss aus dq_export_gate aggregieren (Zusammenfassung je RU).
    """
    src = _src("scripts/quality_gate_module.py")
    gate_ru_pos = src.index("create or replace table dq_export_gate_ru")
    gate_ru_section = src[gate_ru_pos: gate_ru_pos + 1000]
    assert "dq_export_gate" in gate_ru_section, (
        "dq_export_gate_ru liest nicht aus dq_export_gate. "
        "Die RU-Aggregation baut auf der Lok-Ebene auf."
    )


def test_export_excluded_rows_references_core_timeline():
    """
    export_excluded_rows (Audit-Tabelle) basiert auf core_loco_timeline
    und enthaelt alle Zeilen, die nicht exportfaehig sind.
    """
    src = _src("scripts/quality_gate_module.py")
    excl_pos = src.index("create or replace table export_excluded_rows")
    excl_section = src[excl_pos: excl_pos + 1000]
    assert "core_loco_timeline" in excl_section, (
        "export_excluded_rows liest nicht aus core_loco_timeline. "
        "Die Audit-Tabelle muss alle nicht-exportfaehigen Zeilen enthalten."
    )


# ---------------------------------------------------------------------------
# pipeline/quality_gate_incremental.py — apply_r016
# ---------------------------------------------------------------------------

def test_apply_r016_uses_update_not_rebuild():
    """
    apply_r016_to_quality_gate_tables muss per UPDATE arbeiten (inkrementell),
    nicht per CREATE OR REPLACE TABLE (vollstaendiger Rebuild).
    """
    src = _src("scripts/pipeline/quality_gate_incremental.py")
    fn_pos = src.index("def apply_r016_to_quality_gate_tables(")
    fn_body = src[fn_pos: fn_pos + 3000]
    assert "update" in fn_body.lower(), (
        "apply_r016_to_quality_gate_tables verwendet kein UPDATE. "
        "Der inkrementelle Update-Ansatz ist verloren gegangen."
    )
    assert "create or replace table dq_export_gate" not in fn_body, (
        "apply_r016_to_quality_gate_tables baut dq_export_gate komplett neu. "
        "Es soll nur R016-betroffene Zeilen inkrementell aktualisieren."
    )


def test_apply_r016_touches_export_gate():
    """
    apply_r016 muss dq_export_gate und dq_export_gate_ru aktualisieren.
    """
    src = _src("scripts/pipeline/quality_gate_incremental.py")
    assert "dq_export_gate" in src, (
        "apply_r016_to_quality_gate_tables referenziert dq_export_gate nicht."
    )


# ---------------------------------------------------------------------------
# full_rebuild_from_raw.py — Reihenfolge Quality-Gate-Pipeline
# ---------------------------------------------------------------------------

def test_quality_gate_pipeline_order_in_full_rebuild():
    """
    Die Reihenfolge muss sein:
    build_quality_gate_tables → apply_r016_to_quality_gate_tables → finalize_quality_gate_phase6d
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    pos_build = src.index("build_quality_gate_tables(")
    pos_r016 = src.index("apply_r016_to_quality_gate_tables(")
    pos_finalize = src.index("finalize_quality_gate_phase6d(")
    assert pos_build < pos_r016, (
        "apply_r016_to_quality_gate_tables kommt vor build_quality_gate_tables. "
        "Reihenfolge muss sein: build → apply_r016 → finalize."
    )
    assert pos_r016 < pos_finalize, (
        "finalize_quality_gate_phase6d kommt vor apply_r016_to_quality_gate_tables. "
        "Reihenfolge muss sein: build → apply_r016 → finalize."
    )


def test_finalize_phase6d_imported_in_full_rebuild():
    """
    finalize_quality_gate_phase6d muss in full_rebuild_from_raw importiert sein.
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    assert "finalize_quality_gate_phase6d" in src, (
        "finalize_quality_gate_phase6d fehlt in full_rebuild_from_raw. "
        "Der Quality-Gate-Abschlussschritt wird nicht ausgefuehrt."
    )


def test_insert_gap_only_day_findings_before_finalize():
    """
    insert_gap_only_day_findings_phase6d muss vor finalize_quality_gate_phase6d laufen.
    GAP-Only-Day-Findings muessen bekannt sein, bevor das Gate finalisiert wird.
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    pos_insert = src.index("insert_gap_only_day_findings_phase6d(")
    pos_finalize = src.index("finalize_quality_gate_phase6d(")
    assert pos_insert < pos_finalize, (
        "insert_gap_only_day_findings_phase6d kommt nach finalize_quality_gate_phase6d. "
        "GAP-Only-Day-Findings muessen vor der Finalisierung eingefuegt werden."
    )


# ---------------------------------------------------------------------------
# rule_engine_hardening_phase6d.py — Finalisierung
# ---------------------------------------------------------------------------

def test_finalize_phase6d_calls_feedback_rule_adjustments():
    """
    finalize_quality_gate_phase6d (oder der sitecustomize-Patch) muss
    apply_feedback_rule_adjustments_phase11i aufrufen.
    Der Patch in sitecustomize.py ist ein Sicherheitsnetz fuer diesen Aufruf.
    """
    scripts = ROOT / "scripts"
    # Entweder in phase6d direkt oder im sitecustomize-Patch
    phase6d_src = _src("scripts/rule_engine_hardening_phase6d.py")
    sitecustomize_src = _src("scripts/sitecustomize.py")
    combined = phase6d_src + sitecustomize_src
    assert "apply_feedback_rule_adjustments_phase11i" in combined, (
        "apply_feedback_rule_adjustments_phase11i wird weder in phase6d noch in "
        "sitecustomize.py aufgerufen. Die Feedback-Regelanpassungen fehlen."
    )
