"""Cyprus: Water Development Department dam monitoring system (dams.wdd.moa.gov.cy).

`/api/latest` carries each dam's capacity and coordinates plus daily storage for
the current month. `/api/historical/storage?dam=` carries the long record (1st
and 15th of each month since 1988); for the current month it holds a
month-keyed placeholder, so history stops where the daily figures begin.
Volumes are in million m³ (= hm³).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta, slugify

BASE = "https://dams.wdd.moa.gov.cy"


class WddAdapter:
    meta = SourceMeta(
        id="cy-wdd",
        country="CY",
        name="Water Development Department — Dam monitoring system",
        url="https://dams.wdd.moa.gov.cy/",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        response = client.get(f"{BASE}/api/latest", timeout=60)
        response.raise_for_status()
        return response.content

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        latest = json.loads(self.fetch(client))
        month_start = date.fromisoformat(f"{latest['monthKey']}-01")
        for dam in latest["dams"]:
            response = client.get(
                f"{BASE}/api/historical/storage", params={"dam": dam["name"]}, timeout=60
            )
            response.raise_for_status()
            series = response.json().get(dam["name"], [])
            yield json.dumps(
                {
                    "dams": [dam],
                    "history": [p for p in series if date.fromisoformat(p["date"]) < month_start],
                }
            ).encode()

    def parse(self, raw: bytes) -> pl.DataFrame:
        payload = json.loads(raw)
        rows = []
        for dam in payload["dams"]:
            name, capacity = dam["name"], float(dam["capacity"])
            if "history" in payload:
                points = [(date.fromisoformat(p["date"]), p["value"]) for p in payload["history"]]
            else:
                year, month = map(int, payload["monthKey"].split("-"))
                daily = payload["daily"].get(name, {})
                points = [(date(year, month, int(day)), value) for day, value in daily.items()]
            rows += [
                {
                    "source_key": slugify(name),
                    "name": name,
                    "group": dam.get("project", ""),
                    "observed_on": day,
                    "volume_hm3": float(value),
                    "capacity_hm3": capacity,
                }
                for day, value in points
                if value is not None
            ]
        return pl.DataFrame(rows, schema=OBSERVATION_SCHEMA)
