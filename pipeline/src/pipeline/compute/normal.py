"""B7/B8/E2/E9: what's normal for this area at this time of year, and how far off it is."""

from __future__ import annotations

import polars as pl

WINDOW_YEARS = 10
MIN_YEARS = 5


def _keyed(df: pl.DataFrame) -> pl.DataFrame:
    parts = pl.col("week").str.split_exact("-W", 1)
    return df.with_columns(
        parts.struct.field("field_0").cast(pl.Int32).alias("_year"),
        # E9: ISO week 53 is compared with the week-52 normal.
        parts.struct.field("field_1").cast(pl.Int32).clip(upper_bound=52).alias("_wk"),
    )


def with_normals(by_area: pl.DataFrame) -> pl.DataFrame:
    """Add normal_pct, normal_p10, normal_p90, normal_years and anomaly_pts.

    Normal for (area, week) is the mean % full for the same ISO week across the
    previous WINDOW_YEARS years (not including this one). It needs MIN_YEARS of
    history; otherwise it's null and the area reads "insufficient history".
    """
    keyed = _keyed(by_area)
    reference = keyed.select(
        "area_id", "_wk", pl.col("_year").alias("_ref_year"), pl.col("pct").alias("_ref")
    )
    stats = (
        keyed.select("area_id", "week", "_year", "_wk")
        .join(reference, on=["area_id", "_wk"])
        .filter(
            (pl.col("_ref_year") < pl.col("_year"))
            & (pl.col("_ref_year") >= pl.col("_year") - WINDOW_YEARS)
        )
        .group_by("area_id", "week")
        .agg(
            pl.col("_ref").mean().alias("_mean"),
            pl.col("_ref").quantile(0.1, interpolation="linear").alias("_p10"),
            pl.col("_ref").quantile(0.9, interpolation="linear").alias("_p90"),
            pl.col("_ref_year").n_unique().cast(pl.Int64).alias("normal_years"),
        )
    )
    enough = pl.col("normal_years") >= MIN_YEARS
    return (
        keyed.join(stats, on=["area_id", "week"], how="left")
        .with_columns(pl.col("normal_years").fill_null(0))
        .with_columns(
            pl.when(enough).then(pl.col("_mean")).alias("normal_pct"),
            pl.when(enough).then(pl.col("_p10")).alias("normal_p10"),
            pl.when(enough).then(pl.col("_p90")).alias("normal_p90"),
        )
        .with_columns((pl.col("pct") - pl.col("normal_pct")).alias("anomaly_pts"))
        .drop("_year", "_wk", "_mean", "_p10", "_p90")
    )
