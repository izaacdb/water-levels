"""Curated per-country reservoir registries (``registry/<cc>.csv``).

The registry assigns our stable reservoir ids and holds facts the source feeds
don't carry (river basin district, coordinates).
"""

from __future__ import annotations

import logging
from pathlib import Path

import polars as pl

from pipeline.adapters.base import PCT_FULL

log = logging.getLogger(__name__)

REGISTRY_DIR = Path(__file__).resolve().parents[2] / "registry"


def load_registry(country: str) -> pl.DataFrame:
    return pl.read_csv(REGISTRY_DIR / f"{country.lower()}.csv", infer_schema=False)


def load_rbds() -> pl.DataFrame:
    """WFD river basin districts: code, country, official local name."""
    return pl.read_csv(REGISTRY_DIR / "rbd.csv", infer_schema=False)


def attach_reservoir_ids(
    obs: pl.DataFrame, registry: pl.DataFrame, source_id: str | None = None
) -> tuple[pl.DataFrame, list[str]]:
    """Map source keys to reservoir ids. Returns (mapped rows, unknown source keys).

    A country with several sources has a ``source_id`` column, and each source maps
    only to its own rows (D6). Sources that publish only % full, or only volume, are
    completed with the registry's ``capacity_hm3`` (D7); rows that still lack a volume
    or capacity are dropped.
    """
    if source_id is not None and "source_id" in registry.columns:
        registry = registry.filter(pl.col("source_id") == source_id)
    capacity = (
        pl.col("capacity_hm3").cast(pl.Float64, strict=False)
        if "capacity_hm3" in registry.columns
        else pl.lit(None, dtype=pl.Float64)
    )
    ids = registry.select("id", "source_key", capacity.alias("registry_capacity"))
    mapped = obs.join(ids, on="source_key", how="left")
    unknown = sorted(mapped.filter(pl.col("id").is_null())["source_key"].unique().to_list())
    pct = pl.col(PCT_FULL) if PCT_FULL in obs.columns else pl.lit(None, dtype=pl.Float64)
    completed = (
        mapped.filter(pl.col("id").is_not_null())
        .with_columns(pl.coalesce("capacity_hm3", "registry_capacity").alias("capacity_hm3"))
        .with_columns(pl.coalesce("volume_hm3", pct / 100 * pl.col("capacity_hm3")))
    )
    incomplete = completed.filter(pl.col("volume_hm3").is_null() | pl.col("capacity_hm3").is_null())
    if incomplete.height:
        log.warning(
            "dropping %d rows without a volume or capacity: %s",
            incomplete.height,
            sorted(incomplete["source_key"].unique().to_list()),
        )
    return (
        completed.filter(pl.col("volume_hm3").is_not_null() & pl.col("capacity_hm3").is_not_null())
        .drop("registry_capacity", PCT_FULL, strict=False)
        .rename({"id": "reservoir_id"}),
        unknown,
    )


def _country_notes(status: str) -> dict[str, str]:
    path = REGISTRY_DIR / "countries.csv"
    if not path.exists():
        return {}
    rows = pl.read_csv(path, infer_schema=False)
    return dict(rows.filter(pl.col("status") == status).select("code", "note").iter_rows())


def load_withdrawn() -> dict[str, str]:
    """E6: countries that no longer meet the inclusion bar, with the note shown to users."""
    return _country_notes("withdrawn")


def load_coverage() -> dict[str, str]:
    """B1a: what part of a partly covered country the figures cover."""
    return _country_notes("active")
