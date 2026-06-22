"""Load the full 30-day locomotive context independently from the daily task filter."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TIMELINE_PATH = ROOT / "data" / "03_exports" / "core_loco_timeline.csv"
LOOKBACK_DAYS = 30


def _read_timeline(path: Path = TIMELINE_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for kwargs in (
        {"sep": ";", "encoding": "utf-8-sig"},
        {"sep": None, "engine": "python", "encoding": "utf-8-sig"},
    ):
        try:
            return pd.read_csv(path, **kwargs)
        except Exception:
            continue
    return pd.DataFrame()


def load_case_timeline_context(path: Path = TIMELINE_PATH, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Return the latest 30 calendar days from the generated timeline export."""
    timeline = _read_timeline(path)
    if timeline.empty:
        return timeline
    candidates = [
        column for column in ("period_start_utc", "actual_departure_ts", "ActualDeparture", "sequence_ts")
        if column in timeline.columns
    ]
    if not candidates:
        return timeline
    timestamps = pd.Series(pd.NaT, index=timeline.index, dtype="datetime64[ns]")
    for column in candidates:
        parsed = pd.to_datetime(timeline[column], errors="coerce", utc=True).dt.tz_localize(None)
        timestamps = timestamps.fillna(parsed)
    latest = timestamps.dropna().max()
    if pd.isna(latest):
        return timeline
    cutoff = latest.normalize() - pd.Timedelta(days=max(int(lookback_days), 1) - 1)
    return timeline[timestamps.isna() | (timestamps >= cutoff)].copy()
