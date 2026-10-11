"""Write registry/de.csv: Saxony's reservoirs (Talsperren) run by the LTV.

Usage: uv run python scripts/build_de_registry.py

- Reservoirs: every "TS" on the LTV overview page (pipeline.adapters.de_ltv).
- Capacity: each dam's own page (tsz/pegel/<id>.html), "Stauraumaufteilung nach
  Wasserwirtschaftsplan": the cumulative content at the top of the operating zone,
  excluding flood-retention space.
- Coordinates: OpenStreetMap (Nominatim, "Talsperre <name>" in Saxony), one request a
  second as its usage policy asks. Hand fixes in registry/de_overrides.csv win.
- District: the WFD district containing the point (web/public/geo/rbd.geojson).
"""

from __future__ import annotations

import csv
import json
import re
import time
from pathlib import Path

import httpx
from shapely.geometry import Point, shape

from pipeline.adapters.base import slugify
from pipeline.adapters.de_ltv import URL, parse_storage_zones

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "pipeline" / "registry" / "de.csv"
OVERRIDES = ROOT / "pipeline" / "registry" / "de_overrides.csv"
RBD = ROOT / "web" / "public" / "geo" / "rbd.geojson"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
SAXONY = "11.8,51.7,15.1,50.1"  # lon/lat viewbox
UA = "water-levels registry builder (github.com/izaacdb/water-levels)"


def _locate(client: httpx.Client, name: str) -> tuple[float, float] | None:
    for query in (f"Talsperre {name}", name):
        time.sleep(1.1)
        found = client.get(
            NOMINATIM,
            params={"q": query, "format": "json", "limit": 1, "viewbox": SAXONY, "bounded": 1},
            headers={"User-Agent": UA},
        ).json()
        if found:
            return float(found[0]["lon"]), float(found[0]["lat"])
    return None


def main() -> None:
    geo = json.loads(RBD.read_text())
    districts = [
        (f["id"], shape(f["geometry"])) for f in geo["features"] if f["id"].startswith("DE")
    ]
    overrides = {}
    if OVERRIDES.exists():
        with OVERRIDES.open() as fh:
            overrides = {r["id"]: r for r in csv.DictReader(fh)}
    rows = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        overview = client.get(URL).content.decode("iso-8859-1")
        dams = re.findall(r'<option value="(\d+)">TS ([^<]+)</option>', overview)
        for dam_id, name in dams:
            name = name.strip()
            page = client.get(f"{URL}pegel/{dam_id}.html").content.decode("iso-8859-1")
            row = {
                "id": f"DE-{slugify(name)}",
                "source_key": slugify(name),
                "name": name,
                "group": "LTV Sachsen",
                "rbd_code": "",
                "lat": "",
                "lon": "",
                "capacity_hm3": "",
                "ltv_id": dam_id,
            }
            try:
                row["capacity_hm3"] = f"{parse_storage_zones(page):.3f}"
            except ValueError:
                print(f"no storage zones for {name}")
            if (position := _locate(client, name)) is not None:
                row["lon"], row["lat"] = f"{position[0]:.4f}", f"{position[1]:.4f}"
            row.update({k: v for k, v in overrides.get(row["id"], {}).items() if v and k in row})
            if row["lat"]:
                point = Point(float(row["lon"]), float(row["lat"]))
                row["rbd_code"] = min(districts, key=lambda d: d[1].distance(point))[0]
            rows.append(row)
    with REGISTRY.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["id"]))
    print(f"{len(rows)} Saxon reservoirs")


if __name__ == "__main__":
    main()
