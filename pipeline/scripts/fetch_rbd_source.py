"""Add river basin districts from EEA WISE to registry/rbd-source.geojson.

Usage: uv run python scripts/fetch_rbd_source.py <layer> <code> [<code> ...]
  e.g. scripts/fetch_rbd_source.py WFD2016 UK01 UK02 ... UK12
       scripts/fetch_rbd_source.py WFD2022 EL06 EL07

The UK left the EU before the 2022 reporting cycle, so its districts come from the
WFD2016 layer. The server's own simplification can produce invalid rings, so
geometries are repaired here (buffer(0)) and simplified locally. Districts already
in the file with the same code are replaced. Run build_rbd_geo.py afterwards.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "pipeline" / "registry" / "rbd-source.geojson"
SERVICE = (
    "https://water.discomap.eea.europa.eu/arcgis/rest/services/WISE_WFD/"
    "{layer}_RiverBasinDistrict_WM/MapServer/0/query"
)


def fetch(layer: str, codes: list[str]) -> list[dict[str, object]]:
    quoted = ",".join(f"'{c}'" for c in codes)
    response = httpx.get(
        SERVICE.format(layer=layer),
        params={
            "where": f"thematicIdIdentifier IN ({quoted})",
            "outFields": "thematicIdIdentifier,nameText,countryCode",
            "outSR": 4326,
            "f": "geojson",
        },
        timeout=300,
    )
    response.raise_for_status()
    features = response.json()["features"]
    for f in features:
        geom = shape(f["geometry"])
        geom = (geom if geom.is_valid else geom.buffer(0)).simplify(0.01, preserve_topology=True)
        f["geometry"] = json.loads(
            json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), 3)
        )
        f.pop("id", None)
    return features


def main(layer: str, codes: list[str]) -> None:
    current = json.loads(SOURCE.read_text())
    added = fetch(layer, codes)
    found = {f["properties"]["thematicIdIdentifier"] for f in added}
    if missing := set(codes) - found:
        raise SystemExit(f"not found in {layer}: {sorted(missing)}")
    kept = [f for f in current["features"] if f["properties"]["thematicIdIdentifier"] not in found]
    current["features"] = kept + added
    SOURCE.write_text(json.dumps(current, separators=(",", ":"), ensure_ascii=False))
    print(f"{len(added)} districts added from {layer}; {len(current['features'])} in total")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
