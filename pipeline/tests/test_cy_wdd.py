import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA
from pipeline.adapters.cy_wdd import WddAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "cy"
LATEST = (FIXTURES / "latest-2026-10.json").read_bytes()
HISTORICAL = json.loads((FIXTURES / "historical-kouris.json").read_text())


def test_latest_gives_one_row_per_dam_per_reported_day() -> None:
    obs = WddAdapter().parse(LATEST)
    assert dict(obs.schema) == OBSERVATION_SCHEMA
    kouris = obs.filter(pl.col("source_key") == "kouris").sort("observed_on").to_dicts()
    assert kouris == [
        {
            "source_key": "kouris",
            "name": "Kouris",
            "group": "esna",
            "observed_on": date(2026, 10, d),
            "volume_hm3": v,
            "capacity_hm3": 115.0,
        }
        for d, v in ((5, 42.657), (6, 42.57))
    ]
    assert obs["source_key"].n_unique() == 21


def test_history_keeps_genuine_dates_before_the_current_month() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest":
            return httpx.Response(200, content=LATEST)
        dam = request.url.params["dam"]
        return httpx.Response(200, json=HISTORICAL if dam == "Kouris" else {dam: []})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://x") as client:
        batches = list(WddAdapter().fetch_history(client))
    obs = pl.concat([WddAdapter().parse(b) for b in batches])
    dates = obs.filter(pl.col("source_key") == "kouris")["observed_on"].to_list()
    assert date(2024, 12, 1) in dates
    assert max(dates) < date(2026, 10, 1)  # the month-keyed "2026-10-15" entry is dropped
