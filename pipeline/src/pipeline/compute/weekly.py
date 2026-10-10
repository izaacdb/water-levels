"""B3: put every reservoir on a common ISO-week snapshot."""

from __future__ import annotations

from datetime import date

import polars as pl


def iso_week_label(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_expr(col: str = "observed_on") -> pl.Expr:
    return pl.format(
        "{}-W{}",
        pl.col(col).dt.iso_year(),
        pl.col(col).dt.week().cast(pl.String).str.zfill(2),
    )


def weekly_snapshot(store: pl.DataFrame) -> pl.DataFrame:
    """One row per reservoir per ISO week: the most recent value published in that week."""
    return (
        store.with_columns(week_expr().alias("week"))
        .sort("observed_on")
        .group_by("reservoir_id", "week", maintain_order=True)
        .last()
        .select("reservoir_id", "week", "observed_on", "volume_hm3", "capacity_hm3", "source_id")
        .sort("reservoir_id", "week")
    )
