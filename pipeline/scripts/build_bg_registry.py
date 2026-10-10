"""Build registry/bg.csv from MOEW bulletins plus Wikidata coordinates.

Inputs: a Wikidata SPARQL JSON export of dams/reservoirs in Bulgaria (Q219) with
coordinates (same query shape as build_pt_registry.py), then bulletin files
(LibreOffice HTML or PDF). Hand fixes live in registry/bg_overrides.csv.
Usage: uv run python scripts/build_bg_registry.py wikidata.json bulletin.html [...]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from pipeline.adapters.bg_moew import bg_key, parse_html, parse_pdf

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "registry" / "bg.csv"
OVERRIDES = ROOT / "registry" / "bg_overrides.csv"

# Basin directorate -> WFD river basin district
DIRECTORATE_RBD = {"БДДР": "BG1000", "БДЧР": "BG2000", "БДИБР": "BG3000", "БДЗБР": "BG4000"}
PREFIX = re.compile(r"^(язовир|яз\.)\s+", re.IGNORECASE)
SUFFIX = re.compile(r"\s+(dam|reservoir|lake)$", re.IGNORECASE)


def key(label: str) -> str:
    label = SUFFIX.sub("", PREFIX.sub("", label.strip()))
    return (
        bg_key(label)
        if re.search("[а-яА-Я]", label)
        else re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    )


def main(wikidata: str, *bulletins: str) -> None:
    coords: dict[str, tuple[float, float]] = {}
    for b in json.loads(Path(wikidata).read_text())["results"]["bindings"]:
        lon, lat = map(float, re.findall(r"-?\d+\.?\d*", b["coord"]["value"])[:2])
        coords.setdefault(key(b["label"]["value"]), (lat, lon))

    reservoirs: dict[str, dict[str, str]] = {}
    for path in bulletins:
        raw = Path(path).read_bytes()
        obs = parse_pdf(raw) if raw.startswith(b"%PDF") else parse_html(raw)
        for row in obs.iter_rows(named=True):
            reservoirs.setdefault(
                row["source_key"],
                {"name": row["name"], "group": row["group"], "capacity": row["capacity_hm3"]},
            )

    overrides = {r["id"]: r for r in csv.DictReader(OVERRIDES.open())} if OVERRIDES.exists() else {}
    rows, unmatched = [], []
    for skey, info in sorted(reservoirs.items()):
        rid = f"BG-{skey}"
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
                "rbd_code": DIRECTORATE_RBD[info["group"]],
                "lat": f"{lat_lon[0]:.4f}" if lat_lon else "",
                "lon": f"{lat_lon[1]:.4f}" if lat_lon else "",
                # Resolves names clipped in archived PDFs (bg_moew.resolve_clipped_names).
                "capacity_hm3": f"{info['capacity']:.3f}",
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
