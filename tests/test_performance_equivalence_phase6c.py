"""
Algorithmus-Dokumentation: Running-Max vs. Lateral-Join für GAP-Nachfolger
=========================================================================

Dokumentiert für welche Szenarien der Running-Max-Window-Function-Ansatz
äquivalent zum Lateral-Join ist, und wo er abweicht.

ERGEBNIS: Für "Ketten verschachtelter Ereignisse" liefert der Running-Max
den falschen Nachfolger (er verwendet den globalen max(arr) aller Vorgänger
statt des individuellen C.arr je Vorgänger C). Daher bleibt
prepare_timeline_context_phase6c() beim Lateral-Join über die materialisierte
Tabelle tmp_movements_phase6c.

Getestete Szenarien:
- Normalkette ohne Überschneidungen → beide Algorithmen identisch
- Einzeln verschachteltes Ereignis → beide identisch
- Teilüberschneidung → beide identisch
- KETTE verschachtelter Ereignisse (M2 und M3 in M1) → Algorithmen UNTERSCHIEDLICH
- Null-Ankunftszeit → beide identisch
- Null-Abfahrtszeit beim Nachfolger → beide identisch
- Mehrere Loks → beide identisch
"""
from __future__ import annotations

from datetime import datetime

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Hilfsfunktionen: Lateral-Join-Referenzimplementierung
# ---------------------------------------------------------------------------

def _lateral_join_adjacency(con) -> list[tuple]:
    """Original-Lateral-Join-Logik als Referenz (unverändert aus Phase 6C v1)."""
    return con.execute("""
        with movements as (
            select * from tmp_movements_phase6c
        ), ordered as (
            select
                c.loco_no,
                c.movement_sequence_no,
                c.actual_arrival_ts,
                c.destination_name,
                n.movement_sequence_no as next_movement_sequence_no,
                n.actual_departure_ts as next_actual_departure_ts,
                n.origin_name as next_origin_name
            from movements c
            left join lateral (
                select candidate.*
                from movements candidate
                where candidate.loco_no is not distinct from c.loco_no
                  and candidate.movement_sequence_no > c.movement_sequence_no
                  and (
                        c.actual_arrival_ts is null
                     or candidate.actual_departure_ts is null
                     or candidate.actual_departure_ts >= c.actual_arrival_ts
                  )
                order by
                    case when candidate.actual_departure_ts is null then 1 else 0 end,
                    candidate.actual_departure_ts asc nulls last,
                    candidate.movement_sequence_no asc,
                    candidate.source_row_id asc
                limit 1
            ) n on true
        )
        select
            loco_no,
            movement_sequence_no,
            next_movement_sequence_no,
            next_actual_departure_ts
        from ordered
        order by loco_no, movement_sequence_no
    """).fetchall()


def _window_fn_adjacency(con) -> list[tuple]:
    """Window-Function-Implementierung (der neue Algorithmus)."""
    return con.execute("""
        with
        with_running_max as (
            select
                *,
                max(actual_arrival_ts) over (
                    partition by loco_no
                    order by movement_sequence_no asc, source_row_id asc
                    rows between unbounded preceding and 1 preceding
                ) as max_prev_arrival_ts
            from tmp_movements_phase6c
        ),
        with_eligibility as (
            select
                *,
                case
                    when actual_departure_ts is null then true
                    when max_prev_arrival_ts is null then true
                    when actual_departure_ts >= max_prev_arrival_ts then true
                    else false
                end as is_eligible_successor
            from with_running_max
        ),
        eligible_ranked as (
            select
                *,
                sum(case when is_eligible_successor then 1 else 0 end) over (
                    partition by loco_no
                    order by movement_sequence_no asc, source_row_id asc
                    rows between unbounded preceding and current row
                ) as eligible_rank
            from with_eligibility
        ),
        ordered as (
            select
                c.loco_no,
                c.movement_sequence_no,
                c.actual_arrival_ts,
                c.destination_name,
                n.movement_sequence_no as next_movement_sequence_no,
                n.actual_departure_ts as next_actual_departure_ts,
                n.origin_name as next_origin_name
            from eligible_ranked c
            left join eligible_ranked n
                on n.loco_no = c.loco_no
                and n.eligible_rank = c.eligible_rank + 1
                and n.is_eligible_successor = true
        )
        select
            loco_no,
            movement_sequence_no,
            next_movement_sequence_no,
            next_actual_departure_ts
        from ordered
        order by loco_no, movement_sequence_no
    """).fetchall()


# ---------------------------------------------------------------------------
# Fixture-Aufbau
# ---------------------------------------------------------------------------

def _make_con():
    con = duckdb.connect(":memory:")
    con.execute("""
        create table tmp_movements_phase6c (
            loco_no varchar,
            movement_sequence_no bigint,
            actual_departure_ts timestamp,
            actual_arrival_ts timestamp,
            period_start_utc timestamp,
            sequence_ts timestamp,
            origin_name varchar,
            destination_name varchar,
            transport_number varchar,
            report_scope varchar,
            de_event_label varchar,
            source_table varchar,
            source_row_id bigint
        )
    """)
    return con


def _insert(con, rows: list[dict]) -> None:
    for r in rows:
        con.execute("""
            insert into tmp_movements_phase6c values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            r.get("loco_no", "L1"),
            r["seq"],
            r.get("dep"),
            r.get("arr"),
            r.get("dep"),
            r.get("dep"),
            r.get("origin", "A"),
            r.get("dest", "B"),
            r.get("transport", f"T{r['seq']}"),
            r.get("scope", "IN_REPORT"),
            r.get("label", "In DE"),
            "raw_locomotivemovement",
            r["seq"],
        ])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normal_chain_no_overlaps():
    """Normalkette: M1→M2→M3, keine Überschneidungen."""
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 9)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 10), "arr": datetime(2026, 6, 1, 11)},
        {"seq": 3, "dep": datetime(2026, 6, 1, 12), "arr": datetime(2026, 6, 1, 13)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Normal chain: {lateral} != {window}"


def test_nested_event_is_skipped():
    """
    Verschachteltes Ereignis: M2 liegt komplett innerhalb M1.
    Der Nachfolger von M1 muss M3 sein, nicht M2.

      M1: 08:00–12:00
      M2: 09:00–10:00  ← nested in M1, wird übersprungen
      M3: 13:00–14:00  ← korrekter Nachfolger
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 12)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 9), "arr": datetime(2026, 6, 1, 10)},
        {"seq": 3, "dep": datetime(2026, 6, 1, 13), "arr": datetime(2026, 6, 1, 14)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Nested event: {lateral} != {window}"
    # M1 must point to M3
    m1_next = next(r for r in window if r[1] == 1)
    assert m1_next[2] == 3, f"M1 successor should be seq=3, got {m1_next[2]}"


def test_partial_overlap_is_skipped():
    """
    Teilüberschneidung: M2 beginnt vor Ende von M1 (overlapping, kein nesting).

      M1: 08:00–12:00
      M2: 11:00–13:00  ← startet vor M1.arr → überschneidet
      M3: 14:00–15:00  ← korrekter Nachfolger für M1
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 12)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 11), "arr": datetime(2026, 6, 1, 13)},
        {"seq": 3, "dep": datetime(2026, 6, 1, 14), "arr": datetime(2026, 6, 1, 15)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Partial overlap: {lateral} != {window}"
    m1_next = next(r for r in window if r[1] == 1)
    assert m1_next[2] == 3, f"M1 successor should be seq=3, got {m1_next[2]}"


def test_chain_of_nested_events_lateral_correct():
    """
    Kette von nested events: M2 und M3 sind beide nested in M1.

      M1: 08:00–16:00
      M2: 09:00–10:00  ← nested in M1
      M3: 11:00–12:00  ← nested in M1, aber NACH M2
      M4: 17:00–18:00  ← nach M1

    LATERAL JOIN (korrekt):
      M1→M4  (M2 und M3 überlappen mit M1.arr=16:00)
      M2→M3  (M3.dep=11:00 >= M2.arr=10:00 ✓ — lokale Mini-Kette innerhalb M1)
      M3→M4  (M4.dep=17:00 >= M3.arr=12:00 ✓)

    RUNNING-MAX (fehlerhaft für diesen Fall):
      M1→M4  ✓
      M2→M4  ✗ (Running-Max sieht M1.arr=16:00; M3.dep=11:00 < 16:00 → als nicht eligible markiert)
      M3→M4  ✓

    BEGRÜNDUNG: Der Running-Max-Ansatz verwendet global max(arr aller Vorgänger)
    als Schwellenwert. Für M2 ist max_prev_arr = M1.arr = 16:00. M3.dep=11:00 < 16:00
    → M3 wird als nicht-eligible eingestuft, obwohl M2.arr=10:00 als
    individueller Schwellenwert M3 korrekt zulassen würde.

    KONSEQUENZ: prepare_timeline_context_phase6c bleibt beim Lateral-Join
    über die materialisierte Tabelle tmp_movements_phase6c.
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 16)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 9), "arr": datetime(2026, 6, 1, 10)},
        {"seq": 3, "dep": datetime(2026, 6, 1, 11), "arr": datetime(2026, 6, 1, 12)},
        {"seq": 4, "dep": datetime(2026, 6, 1, 17), "arr": datetime(2026, 6, 1, 18)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)

    # Die Algorithmen UNTERSCHEIDEN sich hier — das ist dokumentiertes Verhalten.
    assert lateral != window, "Algorithms must differ for nested chains — update test if behavior changes"

    # Lateral-Join-Ergebnis ist fachlich korrekt.
    m1_next_l = next(r for r in lateral if r[1] == 1)
    m2_next_l = next(r for r in lateral if r[1] == 2)
    m3_next_l = next(r for r in lateral if r[1] == 3)
    assert m1_next_l[2] == 4, "Lateral: M1 → M4"
    assert m2_next_l[2] == 3, "Lateral: M2 → M3 (lokaler Nachfolger innerhalb M1)"
    assert m3_next_l[2] == 4, "Lateral: M3 → M4"

    # Running-Max-Ergebnis für M2 ist FALSCH.
    m2_next_w = next(r for r in window if r[1] == 2)
    assert m2_next_w[2] == 4, "Window: M2 zeigt fälschlicherweise auf M4 (M3 wird durch M1.arr blockiert)"


def test_null_arrival_always_eligible():
    """
    Null-Ankunftszeit: M1 hat kein arr. M2 ist immer qualifiziert als Nachfolger.
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": None},
        {"seq": 2, "dep": datetime(2026, 6, 1, 10), "arr": datetime(2026, 6, 1, 11)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Null arrival: {lateral} != {window}"
    m1_next = next(r for r in window if r[1] == 1)
    assert m1_next[2] == 2, f"M1 successor should be seq=2, got {m1_next[2]}"


def test_null_departure_on_successor():
    """
    Null-Abfahrt beim Nachfolger: M2 hat kein dep. Per Lateral-Join-Logik
    wird M2 als qualifizierter Nachfolger akzeptiert (null dep = immer eligible).
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 9)},
        {"seq": 2, "dep": None, "arr": datetime(2026, 6, 1, 11)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Null departure successor: {lateral} != {window}"


def test_multiple_locos_isolated():
    """
    Zwei Loks: Die Nachfolger-Suche darf nicht loküberschreitend arbeiten.
    """
    con = _make_con()
    # Lok L1
    con.execute("""
        insert into tmp_movements_phase6c values
        ('L1', 1, '2026-06-01 08:00', '2026-06-01 09:00',
         '2026-06-01 08:00', '2026-06-01 08:00', 'A', 'B', 'T1',
         'IN_REPORT', 'In DE', 'raw_locomotivemovement', 1),
        ('L1', 2, '2026-06-01 10:00', '2026-06-01 11:00',
         '2026-06-01 10:00', '2026-06-01 10:00', 'B', 'C', 'T2',
         'IN_REPORT', 'In DE', 'raw_locomotivemovement', 2)
    """)
    # Lok L2
    con.execute("""
        insert into tmp_movements_phase6c values
        ('L2', 1, '2026-06-01 08:00', '2026-06-01 12:00',
         '2026-06-01 08:00', '2026-06-01 08:00', 'X', 'Y', 'T3',
         'IN_REPORT', 'In DE', 'raw_locomotivemovement', 3),
        ('L2', 2, '2026-06-01 13:00', '2026-06-01 14:00',
         '2026-06-01 13:00', '2026-06-01 13:00', 'Y', 'Z', 'T4',
         'IN_REPORT', 'In DE', 'raw_locomotivemovement', 4)
    """)
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Multiple locos: {lateral} != {window}"


def test_last_movement_has_no_successor():
    """Die letzte Bewegung einer Lok hat keinen Nachfolger (next_seq = None)."""
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 9)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window
    assert window[0][2] is None, "Last movement must have no successor"


def test_exact_boundary_not_an_overlap():
    """
    Exakt aneinander grenzende Ereignisse: M2.dep == M1.arr ist KEINE
    Überschneidung, sondern korrekter Nachfolger.
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 9)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 9), "arr": datetime(2026, 6, 1, 10)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window
    m1_next = next(r for r in window if r[1] == 1)
    assert m1_next[2] == 2, "Exact boundary must not be treated as overlap"


def test_nested_followed_by_normal():
    """
    Kombination: nested event, dann normale Fortsetzung.

      M1: 08:00–14:00
      M2: 09:00–10:00  ← nested in M1
      M3: 14:00–15:00  ← Nachfolger von M1
      M4: 16:00–17:00  ← Nachfolger von M3
    """
    con = _make_con()
    _insert(con, [
        {"seq": 1, "dep": datetime(2026, 6, 1, 8), "arr": datetime(2026, 6, 1, 14)},
        {"seq": 2, "dep": datetime(2026, 6, 1, 9), "arr": datetime(2026, 6, 1, 10)},
        {"seq": 3, "dep": datetime(2026, 6, 1, 14), "arr": datetime(2026, 6, 1, 15)},
        {"seq": 4, "dep": datetime(2026, 6, 1, 16), "arr": datetime(2026, 6, 1, 17)},
    ])
    lateral = _lateral_join_adjacency(con)
    window = _window_fn_adjacency(con)
    assert lateral == window, f"Nested + normal: {lateral} != {window}"
    # M1 → M3, M3 → M4
    m1_next = next(r for r in window if r[1] == 1)
    m3_next = next(r for r in window if r[1] == 3)
    assert m1_next[2] == 3
    assert m3_next[2] == 4
