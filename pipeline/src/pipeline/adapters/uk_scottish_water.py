"""United Kingdom (Scotland): Scottish Water's weekly water resource levels.

Scottish Water publishes only % full for all its reservoirs together (and for four
areas), not per reservoir and without volumes. B25: the total is shown as the
Scotland river basin district's figure, kept out of the UK total and out of
reservoir lists. In the registry it is a single row of kind "total".
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PCT_FULL, SourceMeta

URL = (
    "https://www.scottishwater.co.uk/Your-Home/Your-Water/Managing-Water-Resources/"
    "Scotlands-Water-Resource-Levels"
)
TOTAL_KEY = "scottish-water-total"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140 Safari/537.36 water-levels"
)


def _cells(row: str) -> list[str]:
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
        for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)
    ]


def parse_levels(page: str) -> pl.DataFrame:
    rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", page, re.S)]
    total = next((r for r in rows if len(r) >= 2 and r[0] == "Total"), None)
    dated = next((r for r in rows if r and re.fullmatch(r"\d{1,2} \w+ \d{4}", r[0])), None)
    if total is None or dated is None:
        raise ValueError("no total or date on the Scottish Water levels page")
    return pl.DataFrame(
        [
            {
                "source_key": TOTAL_KEY,
                "name": "Scottish Water published total",
                "group": "Scottish Water",
                "observed_on": datetime.strptime(dated[0], "%d %B %Y").date(),
                "volume_hm3": None,
                "capacity_hm3": None,
                PCT_FULL: float(total[1].rstrip("%")),
            }
        ],
        schema={**OBSERVATION_SCHEMA, PCT_FULL: pl.Float64()},
    )


class ScottishWaterAdapter:
    meta = SourceMeta(
        id="uk-scottish-water",
        country="UK",
        name="Scottish Water — Scotland's water resource levels",
        url=URL,
        cadence="weekly",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        response = client.get(
            URL, headers={"User-Agent": _BROWSER_UA}, timeout=60, follow_redirects=True
        )
        response.raise_for_status()
        return response.content

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_levels(raw.decode("utf-8", errors="replace"))
