"""Turn the observation store into the published static JSON contract."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from pipeline.adapters.base import SourceMeta
from pipeline.compute.aggregate import aggregate
from pipeline.compute.stale import is_stale, snapshot_week
from pipeline.compute.weekly import weekly_snapshot
from pipeline.contract import (
    Area,
    Areas,
    CountryStatus,
    Current,
    CurrentEntry,
    Manifest,
    SourceInfo,
)

# A reservoir that hasn't reported for this long has left the source's network
# (decommissioned, merged into a system, ...). Its history still counts in the
# weeks it reported, but it no longer appears in current views or coverage counts.
RETIRED_AFTER = timedelta(days=365)

COUNTRY_NAMES = {
    "ES": "Spain",
    "PT": "Portugal",
    "BG": "Bulgaria",
    "CY": "Cyprus",
    "CZ": "Czechia",
}


def _reservoirs(registries: dict[str, pl.DataFrame]) -> pl.DataFrame:
    return pl.concat(
        [
            reg.select(
                pl.col("id").alias("reservoir_id"),
                pl.lit(country).alias("country"),
                "rbd_code",
                "name",
                pl.col("lat").cast(pl.Float64, strict=False),
                pl.col("lon").cast(pl.Float64, strict=False),
            )
            for country, reg in registries.items()
        ]
    )


def membership(reservoirs: pl.DataFrame) -> pl.DataFrame:
    """Every (reservoir, area) pair: its country, its river basin district and itself."""
    return pl.concat(
        [
            reservoirs.select("reservoir_id", pl.col(col).alias("area_id"))
            for col in ("country", "rbd_code", "reservoir_id")
        ]
    )


def area_catalogue(
    reservoirs: pl.DataFrame, rbds: pl.DataFrame, source_for_country: dict[str, str]
) -> dict[str, Area]:
    areas: dict[str, Area] = {}
    for country in reservoirs["country"].unique().sort():
        areas[country] = Area(
            id=country,
            level="country",
            name=COUNTRY_NAMES.get(country, country),
            country=country,
            capacity_hm3=0,
            source_id=source_for_country[country],
        )
    rbd_names = dict(rbds.select("code", "name").iter_rows())
    centres = reservoirs.group_by("rbd_code", "country").agg(
        pl.col("lon").mean().round(3), pl.col("lat").mean().round(3)
    )
    for row in centres.iter_rows(named=True):
        located = row["lon"] is not None and row["lat"] is not None
        areas[row["rbd_code"]] = Area(
            id=row["rbd_code"],
            level="region",
            name=rbd_names.get(row["rbd_code"], row["rbd_code"]),
            country=row["country"],
            parent_id=row["country"],
            capacity_hm3=0,
            source_id=source_for_country[row["country"]],
            centroid=[row["lon"], row["lat"]] if located else None,
        )
    for row in reservoirs.iter_rows(named=True):
        located = row["lon"] is not None and row["lat"] is not None
        areas[row["reservoir_id"]] = Area(
            id=row["reservoir_id"],
            level="reservoir",
            name=row["name"],
            country=row["country"],
            parent_id=row["rbd_code"],
            capacity_hm3=0,
            source_id=source_for_country[row["country"]],
            centroid=[row["lon"], row["lat"]] if located else None,
        )
    return areas


def build_outputs(
    store: pl.DataFrame,
    registries: dict[str, pl.DataFrame],
    rbds: pl.DataFrame,
    sources: list[SourceMeta],
    now: datetime,
) -> tuple[Manifest, Areas, Current]:
    today = now.date()
    reservoirs = _reservoirs(registries)
    last_seen = store.group_by("reservoir_id").agg(pl.col("observed_on").max().alias("last_seen"))
    active = reservoirs.join(last_seen, on="reservoir_id").filter(
        pl.col("last_seen") >= today - RETIRED_AFTER
    )
    by_area = aggregate(weekly_snapshot(store), membership(reservoirs), counted=membership(active))
    latest = (
        by_area.sort("week")
        .group_by("area_id", maintain_order=True)
        .last()
        .filter(pl.col("area_id").is_in(membership(active)["area_id"].unique().implode()))
    )
    snapshot = snapshot_week(latest["as_of"].to_list(), today=today)
    catalogue = area_catalogue(reservoirs, rbds, {s.country: s.id for s in sources})

    areas: list[Area] = []
    current: dict[str, CurrentEntry] = {}
    for row in latest.sort("area_id").iter_rows(named=True):
        area = catalogue[row["area_id"]].model_copy(
            update={"capacity_hm3": round(row["capacity_hm3"], 1)}
        )
        areas.append(area)
        current[area.id] = CurrentEntry(
            pct=round(row["pct"], 1),
            as_of=row["as_of"],
            stale=is_stale(row["as_of"], snapshot, today=today),
            n_reporting=row["n_reporting"],
            n_total=row["n_total"],
        )

    published = dict(store.group_by("source_id").agg(pl.col("observed_on").max()).iter_rows())
    manifest = Manifest(
        generated_at=now,
        snapshot_week=snapshot,
        countries=[
            CountryStatus(
                code=a.id,
                name=a.name,
                status="stale" if current[a.id].stale else "active",
            )
            for a in areas
            if a.level == "country"
        ],
        sources=[
            SourceInfo(
                id=s.id,
                country=s.country,
                name=s.name,
                url=s.url,
                last_fetched=now,
                last_published=published.get(s.id),
            )
            for s in sources
        ],
    )
    return manifest, Areas(areas), Current(current)


def write_outputs(manifest: Manifest, areas: Areas, current: Current, out_dir: Path) -> None:
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    for name, model in (("manifest", manifest), ("areas", areas), ("current", current)):
        (data_dir / f"{name}.json").write_text(
            model.model_dump_json(by_alias=True, exclude_none=True)
        )
