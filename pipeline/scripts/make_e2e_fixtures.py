"""Deterministic two-country dataset for the web app's end-to-end tests.

Built with the real publish code, so the fixture always matches the contract.
Usage: uv run python scripts/make_e2e_fixtures.py ../web/e2e/fixtures
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from pipeline.adapters.base import SourceMeta
from pipeline.publish import build_outputs, write_outputs
from pipeline.store import STORE_SCHEMA

NOW = datetime(2026, 10, 10, 6, tzinfo=UTC)
SOURCES = [
    SourceMeta("es-test", "ES", "Test source (Spain)", "https://example.org/es"),
    SourceMeta("pt-test", "PT", "Test source (Portugal)", "https://example.org/pt"),
]
RESERVOIRS = [
    # id, name, rbd, lat, lon, capacity, phase
    ("ES-alpha", "Alpha", "ES030", 40.4, -3.7, 300.0, 0.0),
    ("ES-beta", "Beta", "ES030", 40.0, -4.5, 100.0, 1.0),
    ("ES-gamma", "Gamma", "ES050", 37.9, -4.8, 500.0, 2.0),
    ("PT-delta", "Delta", "PTRH3", 41.1, -7.6, 200.0, 0.5),
    ("PT-epsilon", "Epsilon", "PTRH5A", 39.5, -8.0, 400.0, 1.5),
]


def main(out: str) -> None:
    rows = []
    start = date(2020, 10, 6)  # six years of weekly Tuesdays
    for rid, _, _, _, _, cap, phase in RESERVOIRS:
        day = start
        while day <= date(2026, 10, 6):
            season = 0.5 + 0.3 * math.sin(day.timetuple().tm_yday / 365 * 2 * math.pi + phase)
            trend = 0.1 if day.year == 2026 else 0.0
            rows.append(
                {
                    "reservoir_id": rid,
                    "observed_on": day,
                    "volume_hm3": round(cap * min(season + trend, 0.98), 1),
                    "capacity_hm3": cap,
                    "source_id": "es-test" if rid.startswith("ES") else "pt-test",
                    "fetched_at": NOW,
                }
            )
            day += timedelta(days=7)
    store = pl.DataFrame(rows, schema=STORE_SCHEMA)
    registries = {
        country: pl.DataFrame(
            {
                "id": [r[0] for r in RESERVOIRS if r[0].startswith(country)],
                "source_key": [r[0] for r in RESERVOIRS if r[0].startswith(country)],
                "name": [r[1] for r in RESERVOIRS if r[0].startswith(country)],
                "rbd_code": [r[2] for r in RESERVOIRS if r[0].startswith(country)],
                "lat": [str(r[3]) for r in RESERVOIRS if r[0].startswith(country)],
                "lon": [str(r[4]) for r in RESERVOIRS if r[0].startswith(country)],
            }
        )
        for country in ("ES", "PT")
    }
    rbds = pl.DataFrame(
        {
            "code": ["ES030", "ES050", "PTRH3", "PTRH5A"],
            "country": ["ES", "ES", "PT", "PT"],
            "name": ["Tajo", "Guadalquivir", "Douro", "Tejo e Ribeiras do Oeste"],
        }
    )
    write_outputs(build_outputs(store, registries, rbds, SOURCES, now=NOW), Path(out))
    print(f"wrote fixtures to {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
