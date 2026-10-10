"""Add UK water companies' reservoirs to registry/uk.csv.

Usage: uv run python scripts/build_uk_registry.py <source_id> [<source_id> ...]

Names come from each company's live publication. For Stream companies, coordinates
come from their own datasets (the latest position published for each reservoir).
For the others, coordinates and (for %-only companies) capacities are hand-set in
registry/uk_overrides.csv, with the source of each value noted there (reservoirs only
in a company's history are listed in registry/uk_extra.csv); overrides win
over generated values. The river basin district is the WFD district containing the
reservoir (web/public/geo/rbd.geojson). Existing rows for other sources are kept;
rows for the named sources are rebuilt.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from shapely.geometry import Point, shape

from pipeline import http
from pipeline.adapters.base import slugify
from pipeline.adapters.uk_anglian import AnglianAdapter
from pipeline.adapters.uk_scottish_water import ScottishWaterAdapter
from pipeline.adapters.uk_severn_trent import HAFREN_DYFRDWY, SEVERN_TRENT, StoragePagesAdapter
from pipeline.adapters.uk_stream import STREAM_COMPANIES, StreamAdapter, display_name

PAGE_ADAPTERS = {
    "uk-severn-trent": lambda: StoragePagesAdapter(SEVERN_TRENT),
    "uk-hafren-dyfrdwy": lambda: StoragePagesAdapter(HAFREN_DYFRDWY),
    "uk-anglian": AnglianAdapter,
    "uk-scottish-water": ScottishWaterAdapter,
}

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "pipeline" / "registry" / "uk.csv"
OVERRIDES = ROOT / "pipeline" / "registry" / "uk_overrides.csv"
# Reservoirs that appear only in a company's history (e.g. Thornton, listed by Severn
# Trent until mid-2023): kept so their history isn't dropped. publish.py retires them
# from current views after a year without readings.
EXTRA = ROOT / "pipeline" / "registry" / "uk_extra.csv"
RBD = ROOT / "web" / "public" / "geo" / "rbd.geojson"
FIELDS = [
    "id",
    "source_id",
    "source_key",
    "name",
    "group",
    "rbd_code",
    "lat",
    "lon",
    "capacity_hm3",
    "kind",
]


def _district(lon: float, lat: float, districts: list[tuple[str, object]]) -> str:
    point = Point(lon, lat)
    inside = [code for code, geom in districts if geom.contains(point)]  # type: ignore[attr-defined]
    if inside:
        return inside[0]
    # Coastal reservoirs can fall just outside a simplified outline: take the nearest.
    return min(districts, key=lambda d: d[1].distance(point))[0]  # type: ignore[attr-defined]


def _page_rows(source_id: str) -> list[dict[str, str]]:
    adapter = PAGE_ADAPTERS[source_id]()
    with http.client() as client:
        obs = adapter.parse(adapter.fetch(client))
    return [
        {
            "id": f"UK-{key}",
            "source_id": source_id,
            "source_key": key,
            "name": name,
            "group": group,
            "rbd_code": "",
            "lat": "",
            "lon": "",
            "capacity_hm3": "",
            "kind": "",
        }
        for key, name, group in sorted(set(obs.select("source_key", "name", "group").iter_rows()))
    ]


def _rows(source_id: str, districts: list[tuple[str, object]]) -> list[dict[str, str]]:
    if source_id in PAGE_ADAPTERS:
        return _page_rows(source_id)
    company = next(c for c in STREAM_COMPANIES if c.source_id == source_id)
    adapter = StreamAdapter(company)
    with http.client() as client:
        services = adapter._datasets(client)
        raw = [r for s in services for r in adapter._rows(client, s)]
    position: dict[str, tuple[float, float]] = {}
    for row in raw:  # oldest first, so the latest published position wins
        if row.get("LATITUDE") is not None and row.get("LONGITUDE") is not None:
            key = slugify(display_name(str(row["RESERVOIR_NAME"])))
            position[key] = (float(row["LONGITUDE"]), float(row["LATITUDE"]))  # type: ignore[arg-type]
    obs = adapter.parse(json.dumps(raw).encode())
    out = []
    for key, name in sorted(set(zip(obs["source_key"], obs["name"], strict=True))):
        lon, lat = position.get(key, (None, None))
        out.append(
            {
                "id": f"UK-{key}",
                "source_id": source_id,
                "source_key": key,
                "name": name,
                "group": company.name.split(" — ")[0],
                "rbd_code": _district(lon, lat, districts)
                if lat is not None and lon is not None
                else "",
                "lat": f"{lat:.4f}" if lat is not None else "",
                "lon": f"{lon:.4f}" if lon is not None else "",
                "capacity_hm3": "",
                "kind": "",
            }
        )
    return out


def main(source_ids: list[str]) -> None:
    geo = json.loads(RBD.read_text())
    districts = [
        (f["id"], shape(f["geometry"]))
        for f in geo["features"]
        if f["properties"]["country"] == "UK"
    ]
    rows: list[dict[str, str]] = []
    if REGISTRY.exists():
        with REGISTRY.open() as fh:
            rows = [
                {f: r.get(f, "") for f in FIELDS}
                for r in csv.DictReader(fh)
                if r["source_id"] not in source_ids
            ]
    for source_id in source_ids:
        rows += _rows(source_id, districts)
    if EXTRA.exists():
        with EXTRA.open() as fh:
            rows += [
                {f: r.get(f, "") for f in FIELDS}
                for r in csv.DictReader(fh)
                if r["source_id"] in source_ids
            ]
    if OVERRIDES.exists():
        with OVERRIDES.open() as fh:
            for fix in csv.DictReader(fh):
                for row in rows:
                    if row["id"] == fix["id"]:
                        row.update({k: v for k, v in fix.items() if v and k in FIELDS[1:]})
    for row in rows:
        if not row["rbd_code"] and row["lat"] and row["lon"]:
            row["rbd_code"] = _district(float(row["lon"]), float(row["lat"]), districts)
    with REGISTRY.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["id"]))
    print(f"{len(rows)} UK reservoirs")


if __name__ == "__main__":
    main(sys.argv[1:])
