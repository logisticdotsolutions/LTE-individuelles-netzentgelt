from __future__ import annotations

from datetime import datetime, timedelta

SLOT = timedelta(minutes=15)
MICROSECOND = timedelta(microseconds=1)


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def actual_overlap(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> tuple[datetime, datetime] | None:
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    return (start, end) if start < end else None


def floor_quarter(value: datetime) -> datetime:
    return value.replace(minute=(value.minute // 15) * 15, second=0, microsecond=0)


def slots_for_overlap(interval: tuple[datetime, datetime]) -> list[datetime]:
    start, end = interval
    cursor = floor_quarter(start)
    last = end - MICROSECOND
    slots: list[datetime] = []
    while cursor <= last:
        slots.append(cursor)
        cursor += SLOT
    return slots


def main() -> None:
    adjacent_a = (parse("2026-06-06 03:46:00"), parse("2026-06-06 05:32:00"))
    adjacent_b = (parse("2026-06-06 05:32:00"), parse("2026-06-06 05:39:00"))
    assert actual_overlap(adjacent_a, adjacent_b) is None

    same_slot_a = (parse("2026-06-06 07:01:00"), parse("2026-06-06 07:05:00"))
    same_slot_b = (parse("2026-06-06 07:10:00"), parse("2026-06-06 07:14:00"))
    assert actual_overlap(same_slot_a, same_slot_b) is None

    real_a = (parse("2026-06-06 05:30:00"), parse("2026-06-06 05:45:00"))
    real_b = (parse("2026-06-06 05:40:00"), parse("2026-06-06 05:50:00"))
    overlap = actual_overlap(real_a, real_b)
    assert overlap is not None
    assert slots_for_overlap(overlap) == [parse("2026-06-06 05:30:00")]

    print("OK: Pure-Python-Logiktest: angrenzende Intervalle sind kein Overlap.")
    print("OK: Pure-Python-Logiktest: getrennte Intervalle im selben Slot sind kein Overlap.")
    print("OK: Pure-Python-Logiktest: echte Überschneidung bleibt als Slot sichtbar.")


if __name__ == "__main__":
    main()
