"""Curated per-country reservoir registries (``registry/<cc>.csv``).

The registry assigns our stable reservoir ids and holds facts the source feeds
don't carry (river basin district, coordinates).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

REGISTRY_DIR = Path(__file__).resolve().parents[2] / "registry"


def load_registry(country: str) -> pl.DataFrame:
    return pl.read_csv(REGISTRY_DIR / f"{country.lower()}.csv", infer_schema=False)


def load_rbds() -> pl.DataFrame:
    """WFD river basin districts: code, country, official local name."""
    return pl.read_csv(REGISTRY_DIR / "rbd.csv", infer_schema=False)


def attach_reservoir_ids(
    obs: pl.DataFrame, registry: pl.DataFrame
) -> tuple[pl.DataFrame, list[str]]:
    """Map source keys to reservoir ids. Returns (mapped rows, unknown source keys)."""
    ids = registry.select("id", "source_key")
    mapped = obs.join(ids, on="source_key", how="left")
    unknown = sorted(mapped.filter(pl.col("id").is_null())["source_key"].unique().to_list())
    return mapped.filter(pl.col("id").is_not_null()).rename({"id": "reservoir_id"}), unknown
