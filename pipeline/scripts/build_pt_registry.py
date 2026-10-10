"""Build registry/pt.csv from APA bulletins plus Wikidata coordinates.

Inputs: one or more bulletin PDFs (the reservoir list) and a Wikidata SPARQL JSON
export of dams/reservoirs in Portugal with coordinates (P625), e.g.:

  SELECT ?item ?label ?coord WHERE {
    VALUES ?type { wd:Q12323 wd:Q131681 }
    ?item wdt:P31/wdt:P279* ?type ; wdt:P17 wd:Q45 ; wdt:P625 ?coord .
    ?item rdfs:label ?label . FILTER(LANG(?label) IN ("pt","en")) }

Hand fixes live in registry/pt_overrides.csv.
Usage: uv run python scripts/build_pt_registry.py wikidata.json bulletin.pdf [...]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from pipeline.adapters.base import slugify
from pipeline.adapters.pt_apa import parse_bulletin

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "registry" / "pt.csv"
OVERRIDES = ROOT / "registry" / "pt_overrides.csv"

# APA basin label -> WFD river basin district
BASIN_RBD = {
    "LIMA": "PTRH1",
    "CÁVADO": "PTRH2",
    "AVE": "PTRH2",
    "DOURO": "PTRH3",
    "VOUGA": "PTRH4A",
    "MONDEGO": "PTRH4A",
    "R. DO OESTE": "PTRH5A",
    "RIBEIRAS DO OESTE": "PTRH5A",
    "TEJO": "PTRH5A",
    "RIBEIRAS DO OESTE E TEJO": "PTRH5A",
    "SADO": "PTRH6",
    "MIRA": "PTRH6",
    "R. C. ALENTEJO": "PTRH6",
    "RIBEIRAS DO ALENTEJO": "PTRH6",
    "GUADIANA": "PTRH7",
    "ARADE": "PTRH8",
    "R. BARLAVENTO": "PTRH8",
    "RIBEIRAS DO BARLAVENTO": "PTRH8",
    "R. SOTAVENTO": "PTRH8",
    "RIBEIRAS DO SOTAVENTO": "PTRH8",
}
PREFIX = re.compile(r"^(barragem|albufeira|açude|represa)\s+(dos|das|de|do|da)?\s*", re.IGNORECASE)
SUFFIX = re.compile(r"\s+(dam|reservoir)$", re.IGNORECASE)
CONNECTORS = re.compile(r"\b(de|do|da|dos|das|e)\b", re.IGNORECASE)


def key(label: str) -> str:
    return slugify(CONNECTORS.sub(" ", SUFFIX.sub("", PREFIX.sub("", label))))


def main(wikidata: str, *bulletins: str) -> None:
    coords: dict[str, tuple[float, float]] = {}
    for b in json.loads(Path(wikidata).read_text())["results"]["bindings"]:
        lon, lat = map(float, re.findall(r"-?\d+\.?\d*", b["coord"]["value"])[:2])
        coords.setdefault(key(b["label"]["value"]), (lat, lon))

    reservoirs: dict[str, dict[str, str]] = {}
    for path in bulletins:
        obs, _ = parse_bulletin(Path(path).read_bytes())
        for row in obs.sort("observed_on", descending=True).iter_rows(named=True):
            reservoirs.setdefault(
                row["source_key"],
                {"name": row["name"], "group": row["group"]},
            )

    overrides = {}
    if OVERRIDES.exists():
        overrides = {r["id"]: r for r in csv.DictReader(OVERRIDES.open())}

    rows, unmatched = [], []
    for skey, info in sorted(reservoirs.items()):
        rid = f"PT-{skey}"
        lat_lon = coords.get(skey)
        if rid in overrides:
            lat_lon = (float(overrides[rid]["lat"]), float(overrides[rid]["lon"]))
        if lat_lon is None:
            unmatched.append((rid, info["name"]))
        rows.append(
            {
                "id": rid,
                "source_key": skey,
                "name": info["name"],
                "group": info["group"],
                "rbd_code": BASIN_RBD[info["group"]],
                "lat": f"{lat_lon[0]:.4f}" if lat_lon else "",
                "lon": f"{lat_lon[1]:.4f}" if lat_lon else "",
            }
        )
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} reservoirs, {len(rows) - len(unmatched)} located")
    for u in unmatched:
        print("UNLOCATED", u)


if __name__ == "__main__":
    main(*sys.argv[1:])
