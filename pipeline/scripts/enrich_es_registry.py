"""Fill rbd_code/lat/lon in registry/es.csv from official MITECO sources.

Inputs (downloaded by hand, see README in this folder):
  1. MITECO Inventario de Embalses shapefile (egis_embalse_geoetrs89.shp)
  2. The bulletin history CSV exported from BD-Embalses.mdb (for capacity)

Bulletin names don't match the inventory exactly, so each reservoir is matched
within its own basin district by name similarity, using capacity as a
tie-breaker. Rows with no confident match are left blank and reported, to be
filled by hand (see registry/es_overrides.csv).

Usage: uv run python scripts/enrich_es_registry.py <shp> <bulletin.csv>
"""

from __future__ import annotations

import csv
import difflib
import re
import sys
import unicodedata
from pathlib import Path

import polars as pl
import shapefile  # type: ignore[import-untyped]

from pipeline.adapters.es_miteco import parse_csv

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "registry" / "es.csv"
OVERRIDES = ROOT / "registry" / "es_overrides.csv"

# Bulletin "ámbito" -> (inventory DEMARC, WFD river basin district code)
AMBITO = {
    "Miño - Sil": ("MIÑO-SIL", "ES010"),
    "Galicia Costa": ("GALICIA-COSTA", "ES014"),
    "Cantábrico Oriental": ("CANTABRICO ORIENTAL", "ES017"),
    "Cuencas Internas del País Vasco": ("CANTABRICO ORIENTAL", "ES017"),
    "Cantábrico Occidental": ("CANTABRICO OCCIDENTAL", "ES018"),
    "Duero": ("DUERO", "ES020"),
    "Tajo": ("TAJO", "ES030"),
    "Guadiana": ("GUADIANA", "ES040"),
    "Guadalquivir": ("GUADALQUIVIR", "ES050"),
    "Cuenca Mediterránea Andaluza": ("CUENCAS MEDITERRANEAS ANDALUZAS", "ES060"),
    "Guadalete-Barbate": ("GUADALETE Y BARBATE", "ES063"),
    "Tinto, Odiel y Piedras": ("TINTO, ODIEL Y PIEDRAS", "ES064"),
    "Segura": ("SEGURA", "ES070"),
    "Júcar": ("JUCAR", "ES080"),
    "Ebro": ("EBRO", "ES091"),
    "Cuencas Internas de Cataluña": ("CUENCAS INTERNAS DE CATALUÑA", "ES100"),
}
STOP = r"\b(embalse|presa|azud|de|del|la|el|los|las|y|nª|sª|na|sa|lago|as|o|a)\b"


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[()]", " ", s)
    s = re.sub(STOP, " ", s)
    return " ".join(re.findall(r"[a-z0-9]+", s))


def score(bulletin: str, inventory: str, cap: float, inv_cap: float | None) -> float:
    a, b = norm(bulletin), norm(inventory)
    if not a or not b:
        return 0.0
    tokens_a, tokens_b = set(a.split()), set(b.split())
    overlap = len(tokens_a & tokens_b) / len(tokens_a)
    sim = max(difflib.SequenceMatcher(None, a, b).ratio(), overlap)
    if inv_cap and cap:
        ratio = min(cap, inv_cap) / max(cap, inv_cap)
        sim += 0.25 * ratio
    return sim


def main(shp_path: str, bulletin_csv: str) -> None:
    obs = parse_csv(Path(bulletin_csv).read_text())
    latest_cap = dict(
        obs.sort("observed_on")
        .group_by("source_key")
        .agg(pl.col("capacity_hm3").last())
        .iter_rows()
    )
    inventory: dict[str, list[tuple[str, float | None, float, float]]] = {}
    for sr in shapefile.Reader(shp_path, encoding="latin1").iterShapeRecords():
        rec, pts = sr.record.as_dict(), sr.shape.points
        if not pts:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        centre = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        inventory.setdefault(rec["DEMARC"] or "", []).append(
            (rec["NOMBRE"] or "", rec["NMN_CAPAC"], round(centre[0], 4), round(centre[1], 4))
        )

    overrides = {}
    if OVERRIDES.exists():
        overrides = {r["id"]: r for r in csv.DictReader(OVERRIDES.open())}

    rows = list(csv.DictReader(REGISTRY.open()))
    unmatched = []
    for row in rows:
        demarc, rbd = AMBITO[row["group"]]
        row["rbd_code"] = rbd
        if row["id"] in overrides:
            row["lat"], row["lon"] = overrides[row["id"]]["lat"], overrides[row["id"]]["lon"]
            continue
        cap = latest_cap.get(row["source_key"], 0.0)
        candidates = inventory.get(demarc, [])
        best = max(candidates, key=lambda c: score(row["name"], c[0], cap, c[1]), default=None)
        if best and score(row["name"], best[0], cap, best[1]) >= 0.85:
            row["lon"], row["lat"] = str(best[2]), str(best[3])
        else:
            row["lat"] = row["lon"] = ""
            unmatched.append((row["id"], row["name"], row["group"], cap, best[0] if best else None))

    with REGISTRY.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"matched {len(rows) - len(unmatched)}/{len(rows)}")
    for u in unmatched:
        print("UNMATCHED", u)


if __name__ == "__main__":
    main(*sys.argv[1:])
