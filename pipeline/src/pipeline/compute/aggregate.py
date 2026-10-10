"""B5/E1/E4: roll reservoir weeks up into any area (country, region, reservoir itself)."""

from __future__ import annotations

import polars as pl


def plausible() -> pl.Expr:
    """E4: values outside [0, capacity] are shown as published but never aggregated."""
    return (pl.col("volume_hm3") >= 0) & (pl.col("volume_hm3") <= pl.col("capacity_hm3"))


def aggregate(weekly: pl.DataFrame, membership: pl.DataFrame) -> pl.DataFrame:
    """Per area and week: total volume / total capacity across reporting reservoirs.

    ``membership`` has one row per (reservoir_id, area_id) pair; a reservoir
    belongs to its country, its region and its own reservoir area.
    """
    totals = membership.group_by("area_id").agg(pl.len().cast(pl.Int64).alias("n_total"))
    return (
        weekly.filter(plausible())
        .join(membership, on="reservoir_id")
        .group_by("area_id", "week")
        .agg(
            pl.col("volume_hm3").sum(),
            pl.col("capacity_hm3").sum(),
            pl.len().cast(pl.Int64).alias("n_reporting"),
            pl.col("observed_on").max().alias("as_of"),
        )
        .with_columns((pl.col("volume_hm3") / pl.col("capacity_hm3") * 100).alias("pct"))
        .join(totals, on="area_id")
        .sort("area_id", "week")
    )
