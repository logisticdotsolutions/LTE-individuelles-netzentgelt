from __future__ import annotations

import tempfile
from pathlib import Path

import duckdb


def overlap_rows(con):
    return con.execute(
        """
        with movement_intervals as (
            select
                row_number() over () as overlap_row_no,
                loco_no,
                period_start_utc,
                period_end_utc
            from core_loco_timeline
            where row_type = 'MOVEMENT'
              and report_scope = 'IN_REPORT'
              and nullif(trim(loco_no), '') is not null
              and period_start_utc is not null
              and period_end_utc is not null
              and period_end_utc > period_start_utc
        ),
        actual_overlap_intervals as (
            select
                a.loco_no,
                greatest(a.period_start_utc, b.period_start_utc) as overlap_start_utc,
                least(a.period_end_utc, b.period_end_utc) as overlap_end_utc
            from movement_intervals a
            join movement_intervals b
              on b.loco_no = a.loco_no
             and b.overlap_row_no > a.overlap_row_no
             and a.period_start_utc < b.period_end_utc
             and b.period_start_utc < a.period_end_utc
        ),
        duplicate_slots as (
            select distinct
                o.loco_no,
                cast(slots.slot_start_utc as date) as coverage_date,
                slots.slot_start_utc
            from actual_overlap_intervals o
            cross join unnest(
                generate_series(
                    date_trunc('hour', o.overlap_start_utc)
                        + cast(floor(date_part('minute', o.overlap_start_utc) / 15) as bigint)
                          * interval '15 minutes',
                    o.overlap_end_utc - interval '1 microsecond',
                    interval '15 minutes'
                )
            ) as slots(slot_start_utc)
            where o.overlap_end_utc > o.overlap_start_utc
        )
        select loco_no, coverage_date, count(*) as overlap_slot_count
        from duplicate_slots
        group by loco_no, coverage_date
        order by loco_no, coverage_date
        """
    ).fetchall()


def create_table(con):
    con.execute(
        """
        create table core_loco_timeline (
            loco_no varchar,
            row_type varchar,
            report_scope varchar,
            period_start_utc timestamp,
            period_end_utc timestamp
        )
        """
    )


def add(con, loco, start, end):
    con.execute("insert into core_loco_timeline values (?, 'MOVEMENT', 'IN_REPORT', ?, ?)", [loco, start, end])


def main():
    con = duckdb.connect(":memory:")
    create_table(con)

    # Angrenzende Intervalle im selben Viertelstunden-Slot: fachlich KEIN Overlap.
    add(con, "ADJ", "2026-06-06 03:46:00", "2026-06-06 05:32:00")
    add(con, "ADJ", "2026-06-06 05:32:00", "2026-06-06 05:39:00")
    add(con, "ADJ", "2026-06-06 05:39:00", "2026-06-06 06:25:00")
    assert not [row for row in overlap_rows(con) if row[0] == "ADJ"], overlap_rows(con)

    # Echte Überschneidung von fünf Minuten: konservativ ein betroffener 15-Minuten-Slot.
    add(con, "REAL", "2026-06-06 05:30:00", "2026-06-06 05:45:00")
    add(con, "REAL", "2026-06-06 05:40:00", "2026-06-06 05:50:00")
    real = [row for row in overlap_rows(con) if row[0] == "REAL"]
    assert len(real) == 1 and real[0][2] == 1, real

    # Getrennte Intervalle innerhalb desselben Slots: ebenfalls KEIN Overlap.
    add(con, "SAME_SLOT", "2026-06-06 07:01:00", "2026-06-06 07:05:00")
    add(con, "SAME_SLOT", "2026-06-06 07:10:00", "2026-06-06 07:14:00")
    assert not [row for row in overlap_rows(con) if row[0] == "SAME_SLOT"], overlap_rows(con)

    print("OK: Angrenzende Intervalle erzeugen keinen Fehlalarm.")
    print("OK: Getrennte Intervalle im selben Slot erzeugen keinen Fehlalarm.")
    print("OK: Echte zeitliche Überschneidung bleibt blockierend sichtbar.")


if __name__ == "__main__":
    main()
