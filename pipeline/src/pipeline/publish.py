"""Turn the observation store into the published static JSON contract."""

from __future__ import annotations

from datetime import datetime
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

COUNTRY_NAMES = {
    "ES": "Spain",
    "PT": "Portugal",
    "BG": "Bulgaria",
    "CY": "Cyprus",
    "CZ": "Czechia",
}


def _membership(registries: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Which areas each reservoir rolls up into."""
    frames = [
        reg.select(pl.col("id").alias("reservoir_id"), pl.lit(country).alias("area_id"))
        for country, reg in registries.items()
    ]
    return pl.concat(frames)


def build_outputs(
    store: pl.DataFrame,
    registries: dict[str, pl.DataFrame],
    sources: list[SourceMeta],
    now: datetime,
) -> tuple[Manifest, Areas, Current]:
    today = now.date()
    by_area = aggregate(weekly_snapshot(store), _membership(registries))
    latest = by_area.sort("week").group_by("area_id", maintain_order=True).last()
    snapshot = snapshot_week(latest["as_of"].to_list(), today=today)
    source_for_country = {s.country: s for s in sources}

    areas: list[Area] = []
    current: dict[str, CurrentEntry] = {}
    for row in latest.iter_rows(named=True):
        area_id = row["area_id"]
        areas.append(
            Area(
                id=area_id,
                level="country",
                name=COUNTRY_NAMES.get(area_id, area_id),
                country=area_id,
                capacity_hm3=round(row["capacity_hm3"], 1),
                source_id=source_for_country[area_id].id,
            )
        )
        current[area_id] = CurrentEntry(
            pct=round(row["pct"], 1),
            as_of=row["as_of"],
            stale=is_stale(row["as_of"], snapshot, today=today),
            n_reporting=row["n_reporting"],
            n_total=row["n_total"],
        )

    last_published = store.group_by("source_id").agg(pl.col("observed_on").max())
    published = dict(last_published.iter_rows())
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
