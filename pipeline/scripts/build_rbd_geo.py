"""Write web/public/geo/rbd.geojson and registry/rbd.csv from the EEA WISE WFD 2022 layer.

Source (CC BY 4.0, EEA): WISE_WFD/WFD2022_RiverBasinDistrict_WM MapServer layer 0,
queried for our countries with outSR=4326, maxAllowableOffset=0.01, f=geojson and
saved as registry/rbd-source.geojson.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "pipeline" / "registry" / "rbd-source.geojson"
SMALL = {"y", "e", "de", "do", "da", "del", "la", "las", "los", "and"}


def official_name(raw: str) -> str:
    """Official local-language name, title-cased (E10).

    'TINTO, ODIEL Y PIEDRAS' -> 'Tinto, Odiel y Piedras'

    Greek is left as published: title-casing capitals would drop the accents that
    lower-case Greek requires ('ΑΤΤΙΚΗ' is right; 'Αττικη' is misspelt).
    """
    if any("\u0370" <= ch <= "\u03ff" for ch in raw):
        return raw
    words = raw.lower().split(" ")
    return " ".join(
        w if (i and w in SMALL) else "-".join(p[:1].upper() + p[1:] for p in w.split("-"))
        for i, w in enumerate(words)
    )


def main() -> None:
    src = json.loads(SOURCE.read_text())
    features, rows = [], []
    for f in src["features"]:
        p = f["properties"]
        code, name = p["thematicIdIdentifier"], official_name(p["nameText"])
        features.append(
            {
                "type": "Feature",
                "id": code,
                "properties": {"id": code, "name": name, "country": p["countryCode"]},
                "geometry": f["geometry"],
            }
        )
        rows.append({"code": code, "country": p["countryCode"], "name": name})
    out = ROOT / "web" / "public" / "geo" / "rbd.geojson"
    out.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    with (ROOT / "pipeline" / "registry" / "rbd.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "country", "name"], lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["code"]))
    print(f"{len(features)} districts")


if __name__ == "__main__":
    main()
