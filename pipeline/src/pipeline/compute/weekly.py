"""B3: put every reservoir on a common ISO-week snapshot."""

from __future__ import annotations

from datetime import date

import polars as pl


def iso_week_label(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_expr(col: str | pl.Expr = "observed_on") -> pl.Expr:
    day = pl.col(col) if isinstance(col, str) else col
    return pl.format(
        "{}-W{}",
        day.dt.iso_year(),
        day.dt.week().cast(pl.String).str.zfill(2),
    )


def weekly_snapshot(
    store: pl.DataFrame, carry: dict[str, int] | None = None, until: date | None = None
) -> pl.DataFrame:
    """One row per reservoir per ISO week: the most recent value published in that week (B3).

    B3′: for sources slower than weekly (``carry``: source id -> weeks), each reading
    also fills the following weeks until the next reading, for at most that many
    weeks and never beyond the week of ``until``. Carried rows keep their own
    ``observed_on``, so "as of" dates and staleness stay honest.
    """
    cols = ["reservoir_id", "week", "observed_on", "volume_hm3", "capacity_hm3", "source_id"]
    weekly = (
        store.with_columns(week_expr().alias("week"))
        .sort("observed_on")
        .group_by("reservoir_id", "week", maintain_order=True)
        .last()
        .select(cols)
    )
    if carry:
        horizon = iso_week_label(until) if until else None
        carried = [
            weekly.filter(pl.col("source_id") == source_id).with_columns(
                week_expr(pl.col("observed_on") + pl.duration(weeks=k)).alias("week"),
                pl.lit(k).alias("lag"),
            )
            for source_id, weeks in carry.items()
            for k in range(1, weeks + 1)
        ]
        candidates = pl.concat([weekly.with_columns(pl.lit(0).alias("lag")), *carried])
        if horizon:
            candidates = candidates.filter(pl.col("week") <= horizon)
        # The freshest reading wins each week: its own week first, then the shortest carry.
        weekly = (
            candidates.sort("lag", descending=True)
            .group_by("reservoir_id", "week", maintain_order=True)
            .last()
            .select(cols)
        )
    return weekly.sort("reservoir_id", "week")
