"""B5/E1/E4: roll reservoir weeks up into any area (country, region, reservoir itself)."""

from __future__ import annotations

import polars as pl


def flag() -> pl.Expr:
    """E4: values outside [0, capacity] are implausible."""
    return (
        pl.when(pl.col("volume_hm3") < 0)
        .then(pl.lit("negative"))
        .when(pl.col("volume_hm3") > pl.col("capacity_hm3"))
        .then(pl.lit("over_capacity"))
        .otherwise(pl.lit(None, dtype=pl.String))
    )


def _summarise(rows: pl.LazyFrame | pl.DataFrame) -> pl.DataFrame:
    return (
        rows.lazy()
        .group_by("area_id", "week")
        .agg(
            pl.col("volume_hm3").sum(),
            pl.col("capacity_hm3").sum(),
            pl.len().cast(pl.Int64).alias("n_reporting"),
            pl.col("observed_on").max().alias("as_of"),
            pl.col("flag").first(),
        )
        .collect()
    )


def aggregate(
    weekly: pl.DataFrame, membership: pl.DataFrame, counted: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Per area and week: total volume / total capacity across reporting reservoirs.

    ``membership`` has one row per (reservoir_id, area_id) pair; a reservoir
    belongs to its country, its region and its own reservoir area. ``counted``
    (default: ``membership``) is the subset that makes up ``n_total`` (E1).

    E4: implausible readings never enter a country or region total, but a
    reservoir's own area shows them as published, with ``flag`` set.
    """
    totals = (
        (membership if counted is None else counted)
        .group_by("area_id")
        .agg(pl.len().cast(pl.Int64).alias("n_total"))
    )
    flagged = weekly.with_columns(flag().alias("flag")).join(membership, on="reservoir_id")
    own = pl.col("area_id") == pl.col("reservoir_id")
    rows = pl.concat(
        [
            _summarise(flagged.filter(own)),
            _summarise(flagged.filter(~own & pl.col("flag").is_null())),
        ]
    )
    return (
        rows.with_columns((pl.col("volume_hm3") / pl.col("capacity_hm3") * 100).alias("pct"))
        .join(totals, on="area_id")
        .sort("area_id", "week")
    )
