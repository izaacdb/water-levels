"""B24: which week the app represents, and which areas have fallen behind it."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from pipeline.compute.weekly import iso_week_label

MAX_AGE = timedelta(days=14)


def snapshot_week(latest_dates: Iterable[date], today: date) -> str:
    """The most recent week any source has published for, never beyond the current week."""
    return iso_week_label(min(max(latest_dates), today))


def is_stale(as_of: date, snapshot: str, today: date) -> bool:
    return iso_week_label(as_of) < snapshot or today - as_of > MAX_AGE
