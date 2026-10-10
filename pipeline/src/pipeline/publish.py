"""Turn the observation store into the published static JSON contract."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import polars as pl

from pipeline.adapters.base import SourceMeta
from pipeline.compute.aggregate import aggregate
from pipeline.compute.normal import WINDOW_YEARS, with_normals
from pipeline.compute.stale import is_stale, snapshot_week
from pipeline.compute.weekly import weekly_snapshot
from pipeline.contract import (
    Area,
    Areas,
    CountryStatus,
    Current,
    CurrentEntry,
    Manifest,
    Series,
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


class Outputs(NamedTuple):
    manifest: Manifest
    areas: Areas
    current: Current
    series: dict[str, Series]


def _series(by_area: pl.DataFrame, area_ids: list[str], snapshot: str) -> dict[str, Series]:
    """B6: each area's weekly history over the 10 years ending at the snapshot week."""
    year, week = snapshot.split("-W")
    start = f"{int(year) - WINDOW_YEARS}-W{week}"
    window = by_area.filter(
        (pl.col("week") >= start) & (pl.col("week") <= snapshot) & pl.col("area_id").is_in(area_ids)
    ).sort("area_id", "week")
    out: dict[str, Series] = {}
    for (area_id,), rows in window.group_by("area_id", maintain_order=True):
        out[str(area_id)] = Series(
            area_id=str(area_id),
            weeks=rows["week"].to_list(),
            pct=rows["pct"].round(1).to_list(),
            normal=rows["normal_pct"].round(1).to_list(),
            p10=rows["normal_p10"].round(1).to_list(),
            p90=rows["normal_p90"].round(1).to_list(),
            n=rows["n_reporting"].to_list(),
        )
    return out


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def build_outputs(
    store: pl.DataFrame,
    registries: dict[str, pl.DataFrame],
    rbds: pl.DataFrame,
    sources: list[SourceMeta],
    now: datetime,
) -> Outputs:
    today = now.date()
    reservoirs = _reservoirs(registries)
    last_seen = store.group_by("reservoir_id").agg(pl.col("observed_on").max().alias("last_seen"))
    active = reservoirs.join(last_seen, on="reservoir_id").filter(
        pl.col("last_seen") >= today - RETIRED_AFTER
    )
    by_area = with_normals(
        aggregate(weekly_snapshot(store), membership(reservoirs), counted=membership(active))
    )
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
            normal_pct=_round(row["normal_pct"]),
            anomaly_pts=_round(row["anomaly_pts"]),
            normal_years=row["normal_years"],
            as_of=row["as_of"],
            stale=is_stale(row["as_of"], snapshot, today=today),
            n_reporting=row["n_reporting"],
            n_total=row["n_total"],
            flags=[row["flag"]] if row["flag"] else [],
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
    series = _series(by_area, [a.id for a in areas], snapshot)
    return Outputs(manifest, Areas(areas), Current(current), series)


def write_outputs(outputs: Outputs, out_dir: Path) -> None:
    data_dir = out_dir / "data"
    series_dir = data_dir / "series"
    series_dir.mkdir(parents=True, exist_ok=True)
    for stale_file in series_dir.glob("*.json"):
        stale_file.unlink()
    files: list[tuple[Path, Manifest | Areas | Current | Series]] = [
        (data_dir / "manifest.json", outputs.manifest),
        (data_dir / "areas.json", outputs.areas),
        (data_dir / "current.json", outputs.current),
        *((series_dir / f"{area_id}.json", s) for area_id, s in outputs.series.items()),
    ]
    for path, model in files:
        # Series keep their nulls: array positions must stay aligned.
        keep_nulls = isinstance(model, Series)
        path.write_text(model.model_dump_json(by_alias=True, exclude_none=not keep_nulls))
