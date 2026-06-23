"""
Strukturvertragstest fuer build_core / core_loco_timeline
=========================================================

Prueft statisch (Quellcode-Analyse), dass die strukturellen Invarianten von
build_core und der extrahierten _build_core_timeline_sql erhalten bleiben.

Diese Tests schuetzen vor Regressionen wie:
- Verlust der MP-Lookup-Vorberechnung (_build_performing_ru_mp_lookup)
- Verlust der Extraktion in _build_core_timeline_sql
- Fehlen kritischer CTEs (mapped, ordered_movements, movement_rows, gap_*)
- Fehlen von gap_relevant_de (fachlich kritisch fuer GAP-Reporting)
- Fehlendem display_sequence_no (Sortierreihenfolge fuer UI)
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# build_core / _build_core_timeline_sql — Strukturinvarianten
# ---------------------------------------------------------------------------

def test_build_core_calls_mp_lookup_before_sql():
    """
    build_core muss _build_performing_ru_mp_lookup aufrufen, damit
    normalize_company_name() einmal je distinct performing_ru vorberechnet wird.
    """
    src = _src("scripts/run_all.py")
    build_core_start = src.index("def build_core(")
    next_fn = re.search(r"\ndef \w", src[build_core_start + 1:])
    build_core_body = src[build_core_start: build_core_start + 1 + (next_fn.start() if next_fn else len(src))]
    assert "_build_performing_ru_mp_lookup(con)" in build_core_body, (
        "_build_performing_ru_mp_lookup fehlt im Rumpf von build_core. "
        "normalize_company_name() wird dann fuer jede Zeile statt einmal je distinct-Wert aufgerufen."
    )


def test_build_core_calls_timeline_sql_helper():
    """
    build_core muss _build_core_timeline_sql aufrufen (refaktorierter SQL-Block).
    """
    src = _src("scripts/run_all.py")
    build_core_start = src.index("def build_core(")
    next_fn = re.search(r"\ndef \w", src[build_core_start + 1:])
    build_core_body = src[build_core_start: build_core_start + 1 + (next_fn.start() if next_fn else len(src))]
    assert "_build_core_timeline_sql(con, run_id)" in build_core_body, (
        "_build_core_timeline_sql fehlt im Rumpf von build_core. "
        "Der SQL-Block muss als private Hilfsfunktion extrahiert bleiben."
    )


def test_core_loco_timeline_is_materialized_table():
    """
    core_loco_timeline muss als 'create or replace table' angelegt werden,
    nicht als View oder CTE-Alias.
    """
    src = _src("scripts/run_all.py")
    assert "create or replace table core_loco_timeline as" in src, (
        "core_loco_timeline ist kein 'create or replace table'. "
        "Als View oder CTE wird sie bei jedem Zugriff neu berechnet."
    )


def test_required_ctes_present_in_order():
    """
    Die SQL-Kette muss alle semantisch notwendigen CTEs in der richtigen Reihenfolge enthalten.
    """
    src = _src("scripts/run_all.py")
    cte_start = src.index("create or replace table core_loco_timeline as")
    # Naechste top-level Funktion nach der SQL = Ende des Blocks
    sql_block = src[cte_start: cte_start + 30_000]

    required_ctes = ["mapped", "ordered_movements", "movement_rows", "gap_pre", "gap_calc", "gap_rows", "all_rows"]
    last_pos = 0
    for cte in required_ctes:
        pos = sql_block.find(f"{cte} as (", last_pos)
        assert pos >= 0, (
            f"CTE '{cte}' fehlt oder steht nicht in der erwarteten Reihenfolge in core_loco_timeline. "
            "Die SQL-Struktur darf nicht veraendert werden."
        )
        last_pos = pos


def test_gap_relevant_de_flag_in_timeline_sql():
    """
    gap_relevant_de ist ein fachlich kritisches Feld. Ohne es koennen keine
    DE-relevanten GAPs identifiziert werden.
    """
    src = _src("scripts/run_all.py")
    cte_start = src.index("create or replace table core_loco_timeline as")
    sql_block = src[cte_start: cte_start + 30_000]
    assert "gap_relevant_de" in sql_block, (
        "gap_relevant_de fehlt in core_loco_timeline. "
        "Ohne dieses Feld koennen DE-relevante GAPs nicht identifiziert werden."
    )


def test_display_sequence_no_via_row_number():
    """
    display_sequence_no muss per row_number() berechnet werden (Sortierung fuer UI).
    """
    src = _src("scripts/run_all.py")
    cte_start = src.index("create or replace table core_loco_timeline as")
    sql_block = src[cte_start: cte_start + 30_000]
    assert "display_sequence_no" in sql_block, (
        "display_sequence_no fehlt in core_loco_timeline."
    )
    assert "row_number()" in sql_block, (
        "display_sequence_no wird nicht per row_number() berechnet."
    )


def test_gap_rows_have_row_type_gap():
    """
    GAP-Zeilen muessen row_type = 'GAP' haben (unterscheidet sie von MOVEMENT-Zeilen).
    """
    src = _src("scripts/run_all.py")
    cte_start = src.index("create or replace table core_loco_timeline as")
    sql_block = src[cte_start: cte_start + 30_000]
    assert "'GAP'" in sql_block, (
        "GAP-Zeilen haben kein row_type = 'GAP'. Die Unterscheidung MOVEMENT/GAP ist verloren."
    )


def test_union_all_combines_movement_and_gap_rows():
    """
    all_rows CTE muss UNION ALL von movement_rows und gap_rows sein.
    """
    src = _src("scripts/run_all.py")
    cte_start = src.index("create or replace table core_loco_timeline as")
    sql_block = src[cte_start: cte_start + 30_000]
    all_rows_pos = sql_block.index("all_rows as (")
    all_rows_body = sql_block[all_rows_pos: all_rows_pos + 300]
    assert "movement_rows" in all_rows_body, "all_rows CTE muss movement_rows enthalten."
    assert "union all" in all_rows_body.lower(), "all_rows CTE muss UNION ALL verwenden."
    assert "gap_rows" in all_rows_body, "all_rows CTE muss gap_rows enthalten."
