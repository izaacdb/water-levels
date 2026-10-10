"""Canonical observation store: one Parquet file, appended and de-duplicated each run."""

from __future__ import annotations

from pathlib import Path

import polars as pl

STORE_SCHEMA: dict[str, pl.DataType] = {
    "reservoir_id": pl.String(),
    "observed_on": pl.Date(),
    "volume_hm3": pl.Float64(),
    "capacity_hm3": pl.Float64(),
    "source_id": pl.String(),
    "fetched_at": pl.Datetime("us", "UTC"),
}
KEY = ["reservoir_id", "observed_on"]


def load(path: Path) -> pl.DataFrame:
    if not path.exists():
        return pl.DataFrame(schema=STORE_SCHEMA)
    return pl.read_parquet(path)


def save(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.sort(KEY).write_parquet(path, compression="zstd")


def merge(existing: pl.DataFrame, new: pl.DataFrame) -> pl.DataFrame:
    """Union two stores; for a repeated (reservoir, date) the most recent fetch wins."""
    return (
        pl.concat([existing, new])
        .sort("fetched_at")
        .unique(subset=KEY, keep="last", maintain_order=True)
        .sort(KEY)
    )
