"""Vergleichslogik fuer Golden-Master-Aequivalenztests der Pipeline-Ausgaben.

Dieses Modul stellt Hilfsfunktionen bereit, um zwei DuckDB-Verbindungen
(eine Referenz-DB und eine Kandidaten-DB) auf fachliche Aequivalenz zu pruefen.
Die "Mindest-Kennzahlen" aus dem Performance-Vertrag sind hier als pruefbare
Assertions implementiert.

Verwendung:
    from pipeline.equivalence_checks import assert_core_loco_timeline_equivalent

    assert_core_loco_timeline_equivalent(ref_con, candidate_con)

Implementierungsvoraussetzungen:
- Beide Verbindungen muessen core_loco_timeline (oder die jeweilige Tabelle) enthalten.
- Die Funktion vergleicht nur Kennzahlen, keine byte-identischen Dumps.
- Fuer Byte-Identitaet: Golden-Master-Export als CSV und direkter Vergleich.
"""

from __future__ import annotations


def _kpi(con, table: str, col: str, agg: str = "count(*)") -> object:
    """Einfache KPI-Abfrage auf eine Tabelle."""
    return con.execute(f"select {agg} from {table} where {col}").fetchone()[0]  # type: ignore[index]


def assert_tables_row_count_equal(ref_con, cand_con, table: str) -> None:
    """Prueft, dass beide Verbindungen gleich viele Zeilen in <table> haben."""
    ref = ref_con.execute(f"select count(*) from {table}").fetchone()[0]
    cand = cand_con.execute(f"select count(*) from {table}").fetchone()[0]
    assert ref == cand, (
        f"{table}: Zeilenzahl weicht ab. Referenz={ref}, Kandidat={cand}. "
        "Performance-Optimierung hat fachliche Aenderung eingefuehrt."
    )


def assert_distinct_loco_count_equal(ref_con, cand_con, table: str) -> None:
    """Prueft, dass beide Verbindungen gleich viele eindeutige Loknummern haben."""
    ref = ref_con.execute(f"select count(distinct loco_no) from {table}").fetchone()[0]
    cand = cand_con.execute(f"select count(distinct loco_no) from {table}").fetchone()[0]
    assert ref == cand, (
        f"{table}: Anzahl eindeutiger Loks weicht ab. Referenz={ref}, Kandidat={cand}."
    )


def assert_finding_counts_by_rule_equal(ref_con, cand_con) -> None:
    """Prueft, dass die Anzahl Findings je rule_id identisch ist."""
    ref = dict(ref_con.execute(
        "select rule_id, count(*) from dq_findings group by rule_id order by rule_id"
    ).fetchall())
    cand = dict(cand_con.execute(
        "select rule_id, count(*) from dq_findings group by rule_id order by rule_id"
    ).fetchall())
    assert ref == cand, (
        f"dq_findings: Findings-Verteilung weicht ab.\nReferenz: {ref}\nKandidat: {cand}"
    )


def assert_export_gate_status_counts_equal(ref_con, cand_con) -> None:
    """Prueft, dass die Gate-Status-Verteilung (READY/WARNING/BLOCKED) gleich ist."""
    ref = dict(ref_con.execute(
        "select gate_status, count(*) from dq_export_gate group by gate_status order by gate_status"
    ).fetchall())
    cand = dict(cand_con.execute(
        "select gate_status, count(*) from dq_export_gate group by gate_status order by gate_status"
    ).fetchall())
    assert ref == cand, (
        f"dq_export_gate: Status-Verteilung weicht ab.\nReferenz: {ref}\nKandidat: {cand}"
    )


def assert_global_blocker_count_equal(ref_con, cand_con) -> None:
    """Prueft, dass die Anzahl globaler Exportblocker gleich ist."""
    ref = ref_con.execute("select count(*) from dq_global_export_blockers").fetchone()[0]
    cand = cand_con.execute("select count(*) from dq_global_export_blockers").fetchone()[0]
    assert ref == cand, (
        f"dq_global_export_blockers: Anzahl Blocker weicht ab. Referenz={ref}, Kandidat={cand}."
    )


def assert_core_loco_timeline_equivalent(ref_con, cand_con) -> None:
    """Prueft alle Mindest-Kennzahlen fuer core_loco_timeline."""
    assert_tables_row_count_equal(ref_con, cand_con, "core_loco_timeline")
    assert_distinct_loco_count_equal(ref_con, cand_con, "core_loco_timeline")


def assert_quality_gate_equivalent(ref_con, cand_con) -> None:
    """Prueft alle Mindest-Kennzahlen fuer Quality-Gate-Tabellen."""
    assert_tables_row_count_equal(ref_con, cand_con, "dq_export_gate")
    assert_tables_row_count_equal(ref_con, cand_con, "dq_export_gate_ru")
    assert_global_blocker_count_equal(ref_con, cand_con)
    assert_export_gate_status_counts_equal(ref_con, cand_con)


def assert_findings_equivalent(ref_con, cand_con) -> None:
    """Prueft alle Mindest-Kennzahlen fuer dq_findings."""
    assert_tables_row_count_equal(ref_con, cand_con, "dq_findings")
    assert_finding_counts_by_rule_equal(ref_con, cand_con)
