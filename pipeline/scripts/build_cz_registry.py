"""Build registry/cz.csv from the Povodí pages plus Wikidata coordinates.

Each reservoir's WFD river basin district is found by point-in-polygon against
the EEA geometries (registry/rbd-source.geojson), not by enterprise: e.g.
Povodí Labe's Bedřichov drains to the Oder.
Usage: uv run python scripts/build_cz_registry.py wikidata.json <labe.html> ...
(page files named after the enterprise slug, as in tests/fixtures/cz).
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from shapely.geometry import Point, shape

from pipeline.adapters.base import slugify
from pipeline.adapters.cz_povodi import ENTERPRISES, parse_volumes_page

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "registry" / "cz.csv"
OVERRIDES = ROOT / "registry" / "cz_overrides.csv"
# Fallback when a reservoir can't be located: the enterprise's main basin.
ENTERPRISE_RBD = {
    "Povodí Labe": "CZ5000",
    "Povodí Vltavy": "CZ5000",
    "Povodí Ohře": "CZ5000",
    "Povodí Odry": "CZ6000",
    "Povodí Moravy": "CZ1000",
}
PREFIX = re.compile(r"^(vodní nádrž|přehradní nádrž|nádrž|vodní dílo|přehrada)\s+", re.IGNORECASE)
SUFFIX = re.compile(r"\s+(dam|reservoir)$", re.IGNORECASE)


def key(label: str) -> str:
    return slugify(SUFFIX.sub("", PREFIX.sub("", label.strip())))


def candidates(name: str) -> list[str]:
    """Bulletin names carry suffixes Wikidata labels don't ('F-M', '- přepočítaná', '(u X)')."""
    base = re.sub(r"\s+F-M$", "", name)
    out = [base, base.split(" - ")[0], re.sub(r"\s*\(.*?\)", "", base)]
    inner = re.search(r"\((.*?)\)", base)
    if inner:
        out.append(inner.group(1))
    out.append(re.sub(r"\s+1$", "", base))
    out.append(re.sub(r"\s+2$", " II", base))
    return [key(c) for c in dict.fromkeys(out)]


def main(wikidata: str, *pages: str) -> None:
    coords: dict[str, tuple[float, float]] = {}
    for b in json.loads(Path(wikidata).read_text())["results"]["bindings"]:
        lon, lat = map(float, re.findall(r"-?\d+\.?\d*", b["coord"]["value"])[:2])
        coords.setdefault(key(b["label"]["value"]), (lat, lon))
    districts = [
        (f["properties"]["thematicIdIdentifier"], shape(f["geometry"]))
        for f in json.loads((ROOT / "registry" / "rbd-source.geojson").read_text())["features"]
        if f["properties"]["countryCode"] == "CZ"
    ]
    names = {e.slug: e.name for e in ENTERPRISES}
    reservoirs: dict[str, dict[str, str]] = {}
    for path in pages:
        obs = parse_volumes_page(Path(path).read_text(), names[Path(path).stem])
        for row in obs.iter_rows(named=True):
            reservoirs.setdefault(row["source_key"], {"name": row["name"], "group": row["group"]})

    overrides = {r["id"]: r for r in csv.DictReader(OVERRIDES.open())} if OVERRIDES.exists() else {}
    rows, unmatched = [], []
    for skey, info in sorted(reservoirs.items()):
        rid = f"CZ-{skey}"
        lat_lon = next((coords[k] for k in candidates(info["name"]) if k in coords), None)
        if rid in overrides:
            lat_lon = (float(overrides[rid]["lat"]), float(overrides[rid]["lon"]))
        rbd = ""
        if lat_lon:
            point = Point(lat_lon[1], lat_lon[0])
            rbd = next((code for code, geom in districts if geom.contains(point)), "")
        if not lat_lon or not rbd:
            unmatched.append((rid, info["name"], info["group"]))
            rbd = rbd or ENTERPRISE_RBD[info["group"]]
        rows.append(
            {
                "id": rid,
                "source_key": skey,
                "name": info["name"],
                "group": info["group"],
                "rbd_code": rbd,
                "lat": f"{lat_lon[0]:.4f}" if lat_lon else "",
                "lon": f"{lat_lon[1]:.4f}" if lat_lon else "",
            }
        )
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} reservoirs, {len(rows) - len(unmatched)} located with a district")
    for u in unmatched:
        print("UNLOCATED", u)


if __name__ == "__main__":
    main(*sys.argv[1:])
