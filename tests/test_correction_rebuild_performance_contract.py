"""
Performance-Vertragstest für den CORRECTION_REBUILD-Pfad
=========================================================

Prüft statisch (Quellcode-Analyse), dass die implementierten
Leistungsoptimierungen strukturell erhalten bleiben und nicht
versehentlich rückgängig gemacht werden.

Diese Tests schützen vor Regressionen wie:
- Doppelter Quality-Gate-Rebuild
- Fehlendem timed_if_missing für stabile Tabellen
- Fehlendem DuckDB-Thread-Config
- Fehlendem build_transport_routes im Raw-Import
- Verlorenem tmp_movements_phase6c-Materialisierungsschritt
- Verlorener MP-Lookup-Vorberechnung
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PIPELINE = SCRIPTS / "pipeline"


def _src(relpath: str) -> str:
    return (ROOT / relpath).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# full_rebuild_from_raw.py — Correction-Rebuild-Architektur
# ---------------------------------------------------------------------------

def test_no_double_build_quality_gate_in_full_rebuild():
    """
    build_quality_gate_tables darf im full_rebuild_from_raw exakt einmal vorkommen,
    der zweite Rebuild muss apply_r016_to_quality_gate_tables sein.
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    count_full = src.count("build_quality_gate_tables(")
    count_incr = src.count("apply_r016_to_quality_gate_tables(")
    assert count_full == 1, (
        f"build_quality_gate_tables wird {count_full}× aufgerufen (erwartet: 1). "
        "Doppelter Rebuild spart ~50 % der Quality-Gate-Zeit."
    )
    assert count_incr >= 1, (
        "apply_r016_to_quality_gate_tables fehlt in full_rebuild_from_raw — "
        "der inkrementelle R016-Update ist verloren gegangen."
    )


def test_build_transport_routes_is_timed_if_missing():
    """
    build_transport_routes muss per timed_if_missing aufgerufen werden,
    damit der Raw-Import-Cache genutzt wird.
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    # Suche: timed_if_missing irgendwo in der Nähe von "build_transport_routes"
    matches_if_missing = [
        m.start() for m in re.finditer(r'timed_if_missing', src)
    ]
    found = any(
        '"build_transport_routes"' in src[m:m + 120]
        for m in matches_if_missing
    )
    assert found, (
        "build_transport_routes ist nicht per timed_if_missing aufgerufen. "
        "Der Raw-Import berechnet core_transport_route bereits vor – ohne "
        "timed_if_missing wird es bei jedem Correction-Rebuild erneut berechnet."
    )
    # Direkter timed()-Aufruf darf nicht existieren
    assert 'timed("build_transport_routes"' not in src, (
        "build_transport_routes wird per timed() (nicht timed_if_missing) aufgerufen. "
        "Der Caching-Mechanismus greift nicht."
    )


def test_write_csv_outputs_skipped_in_correction_rebuild():
    """
    run_ui_refresh übergibt write_csv_outputs=False an run_full_rebuild_from_raw.
    CSV-Export muss im CORRECTION_REBUILD-Pfad übersprungen werden.
    """
    src = _src("scripts/pipeline/ui_refresh.py")
    assert "write_csv_outputs=False" in src, (
        "ui_refresh.py setzt write_csv_outputs nicht auf False. "
        "Bei jedem Correction-Rebuild würden CSV-Dateien geschrieben."
    )


def test_stable_tables_use_timed_if_missing():
    """
    Alle stabilen Referenztabellen müssen per timed_if_missing aufgerufen werden.
    """
    src = _src("scripts/pipeline/full_rebuild_from_raw.py")
    required_if_missing = [
        "build_cancelled_transport_exclusions",
        "build_dummy_locomotive_catalog",
        "import_mapping",
        "import_market_partner_reference",
        "import_market_partner_mapping",
        "import_vens_tens_exception",
        "build_transport_routes",
    ]
    timed_if_missing_positions = [
        m.start() for m in re.finditer(r'timed_if_missing', src)
    ]
    for fn in required_if_missing:
        found = any(
            f'"{fn}"' in src[m:m + 120]
            for m in timed_if_missing_positions
        )
        assert found, (
            f"{fn} fehlt in timed_if_missing in full_rebuild_from_raw.py. "
            "Stabile Tabellen müssen im Raw-Snapshot gecacht und im Correction-Rebuild übersprungen werden."
        )


# ---------------------------------------------------------------------------
# raw_import.py — Raw-Import-Cache
# ---------------------------------------------------------------------------

def test_raw_import_pre_computes_transport_routes():
    """
    raw_import.py muss build_transport_routes aufrufen, damit core_transport_route
    im Raw-Snapshot vorliegt und im Correction-Rebuild übersprungen werden kann.
    """
    src = _src("scripts/pipeline/raw_import.py")
    assert "build_transport_routes" in src, (
        "raw_import.py ruft build_transport_routes nicht auf. "
        "core_transport_route fehlt dann im Raw-Snapshot und wird bei jedem "
        "Correction-Rebuild neu berechnet."
    )
    assert "from run_all import" in src and "build_transport_routes" in src, (
        "build_transport_routes ist nicht aus run_all importiert."
    )


# ---------------------------------------------------------------------------
# run_all.py — Einzelne Optimierungen
# ---------------------------------------------------------------------------

def test_duckdb_thread_config_in_main():
    """
    DuckDB-Thread-Konfiguration muss in main() von run_all.py gesetzt werden.
    """
    src = _src("scripts/run_all.py")
    assert "set threads to" in src, (
        "DuckDB-Thread-Konfiguration (set threads to) fehlt in run_all.py. "
        "Ohne Thread-Config nutzt DuckDB nur 1 Thread."
    )


def test_mp_lookup_precomputed_before_build_core():
    """
    _build_performing_ru_mp_lookup muss am Anfang von build_core() aufgerufen werden.
    """
    src = _src("scripts/run_all.py")
    # Suche den AUFRUF (nicht die Definition): keine führende "def "
    call_match = re.search(r'(?<!def )_build_performing_ru_mp_lookup\(con\)', src)
    assert call_match is not None, (
        "_build_performing_ru_mp_lookup(con) wird nicht aufgerufen. "
        "normalize_company_name() wird dann für jede Zeile statt einmal je distinct-Wert aufgerufen."
    )
    call_idx = call_match.start()
    build_core_idx = src.index("def build_core(")
    # Nächste Top-Level-Funktion nach build_core
    remaining = src[build_core_idx + len("def build_core("):]
    next_toplevel_fn = re.search(r'\ndef \w', remaining)
    next_def_idx = build_core_idx + len("def build_core(") + (
        next_toplevel_fn.start() if next_toplevel_fn else len(remaining)
    )
    assert build_core_idx < call_idx < next_def_idx, (
        "_build_performing_ru_mp_lookup ist nicht innerhalb von build_core() aufgerufen."
    )


def test_tmp_loco_prepared_materialized_in_build_loco_events():
    """
    build_loco_events muss tmp_loco_prepared als Temp-Table anlegen,
    um den Rohdaten-Scan nur einmal durchzuführen.
    """
    src = _src("scripts/run_all.py")
    assert "create or replace temp table tmp_loco_prepared" in src, (
        "tmp_loco_prepared fehlt in run_all.py. "
        "Ohne Materialisierung werden die Rohdaten mehrfach gescannt."
    )
    # stg_loco_events_skipped darf nicht mehr den Quell-Table scannen
    # (es muss tmp_loco_prepared verwenden)
    skipped_section_start = src.index("create or replace table stg_loco_events_skipped as")
    skipped_section = src[skipped_section_start:skipped_section_start + 1200]
    assert "tmp_loco_prepared" in skipped_section, (
        "stg_loco_events_skipped liest nicht aus tmp_loco_prepared. "
        "Der Rohdaten-Scan wird dadurch doppelt durchgeführt."
    )


def test_no_double_quality_gate_in_run_all():
    """
    In run_all.py::main() darf build_quality_gate_tables maximal einmal aufgerufen werden.
    Die zweite Aktualisierung muss apply_r016_to_quality_gate_tables sein.
    """
    src = _src("scripts/run_all.py")
    # Zähle nur Aufrufe in main(), nicht in Funktionsdefinitionen
    main_idx = src.index("def main(")
    main_src = src[main_idx:]
    count_full = main_src.count("build_quality_gate_tables(")
    count_incr = main_src.count("apply_r016_to_quality_gate_tables(")
    assert count_full <= 1, (
        f"build_quality_gate_tables in main() wird {count_full}× aufgerufen. "
        "Das verdoppelt die Quality-Gate-Berechnungszeit."
    )
    assert count_incr >= 1, (
        "apply_r016_to_quality_gate_tables fehlt in main(). "
        "R016-Findings werden nicht inkrementell nachgezogen."
    )


# ---------------------------------------------------------------------------
# rule_engine_hardening_phase6c.py — Phase-6C-Optimierungen
# ---------------------------------------------------------------------------

def test_tmp_movements_phase6c_materialized():
    """
    prepare_timeline_context_phase6c muss tmp_movements_phase6c als
    physische Temp-Table anlegen, bevor der Self-Join darauf arbeitet.
    """
    src = _src("scripts/rule_engine_hardening_phase6c.py")
    assert "create or replace temp table tmp_movements_phase6c" in src, (
        "tmp_movements_phase6c-Materialisierung fehlt. "
        "Der Self-Join würde dann den core_loco_timeline-CTE mehrfach scannen."
    )


def test_adjacency_uses_self_join_not_lateral():
    """
    tmp_phase6c_adjacency muss per Self-Join (Hash-Join + ROW_NUMBER) auf
    tmp_movements_phase6c arbeiten, nicht per Lateral Join (Nested Loop).
    Self-Join + ROW_NUMBER ist für große Datasets ~3x schneller.
    """
    src = _src("scripts/rule_engine_hardening_phase6c.py")
    adjacency_idx = src.index("tmp_phase6c_adjacency")
    adjacency_section = src[adjacency_idx:adjacency_idx + 3000]
    assert "from tmp_movements_phase6c c" in adjacency_section, (
        "tmp_phase6c_adjacency liest nicht aus tmp_movements_phase6c c. "
        "Die Materialisierungsoptimierung ist verloren gegangen."
    )
    assert "join tmp_movements_phase6c n" in adjacency_section, (
        "tmp_phase6c_adjacency verwendet keinen Self-Join auf tmp_movements_phase6c. "
        "Der Self-Join + ROW_NUMBER-Ansatz ist verloren gegangen."
    )
    assert "row_number()" in adjacency_section, (
        "ROW_NUMBER() fehlt im Adjacency-Block. "
        "Die Ranking-Logik (Ersatz für LATERAL LIMIT 1) ist verloren gegangen."
    )
    # Lateral Join darf nicht verwendet werden
    assert "left join lateral" not in adjacency_section, (
        "tmp_phase6c_adjacency verwendet einen Lateral Join statt Self-Join + ROW_NUMBER. "
        "Der Lateral Join ist ~3x langsamer (Nested Loop vs. Hash-Join)."
    )
    assert "from core_loco_timeline" not in adjacency_section, (
        "tmp_phase6c_adjacency liest direkt aus core_loco_timeline statt "
        "aus der materialisierten tmp_movements_phase6c."
    )
