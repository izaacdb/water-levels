"""B24: which week the app represents, and which areas have fallen behind it."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from pipeline.compute.weekly import iso_week_label

MAX_AGE = timedelta(days=14)
# B24′: a monthly source is out of date only once it has missed about two releases' worth.
MONTHLY_MAX_AGE = timedelta(days=62)


def snapshot_week(latest_dates: Iterable[date], today: date) -> str:
    """The most recent week any source has published for, never beyond the current week."""
    return iso_week_label(min(max(latest_dates), today))


def is_stale(as_of: date, snapshot: str, today: date, cadence: str = "weekly") -> bool:
    """B24: out of date if the source missed a whole completed week of the snapshot.

    B24′: monthly sources are judged by age alone (more than 62 days).

    Sources publish on different days (daily vs weekly). Judging against the last
    *completed* week stops a weekly source looking stale for a day or two every week
    once daily sources have rolled into the new one.
    """
    if cadence == "monthly":
        return today - as_of > MONTHLY_MAX_AGE
    last_completed = iso_week_label(today - timedelta(days=7))
    return iso_week_label(as_of) < min(snapshot, last_completed) or today - as_of > MAX_AGE
