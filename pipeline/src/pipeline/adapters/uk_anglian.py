"""United Kingdom: Anglian Water's weekly reservoir levels table.

Anglian publishes each of its six key reservoirs' level as % full, updated at the
start of each week, with the date in the table header ("Reservoir (05/10/26)").
There are no volumes, so capacities come from the registry: the gross storage
capacities in Anglian's Drought Plan 2022, Appendix 4, Table 1.1 (D7).
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PCT_FULL, SourceMeta, slugify

URL = "https://www.anglianwater.co.uk/services/water-supply/monitoring-water-resources"
_HEADER_DATE = re.compile(r"Reservoir\s*\((\d{2}/\d{2}/\d{2})\)")
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140 Safari/537.36 water-levels"
)


def _cells(row: str) -> list[str]:
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
        for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)
    ]


def parse_levels_table(page: str) -> pl.DataFrame:
    rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", page, re.S)]
    header = next((r for r in rows if r and _HEADER_DATE.search(r[0])), None)
    if header is None:
        raise ValueError("no reservoir levels table on the Anglian Water page")
    match = _HEADER_DATE.search(header[0])
    assert match is not None
    day = datetime.strptime(match.group(1), "%d/%m/%y").date()
    out = []
    for row in rows[rows.index(header) + 1 :]:
        if len(row) < 2 or not row[0]:
            continue
        try:
            pct = float(row[1])
        except ValueError:
            continue
        out.append(
            {
                "source_key": slugify(row[0]),
                "name": row[0],
                "group": "Anglian Water",
                "observed_on": day,
                "volume_hm3": None,
                "capacity_hm3": None,
                PCT_FULL: pct,
            }
        )
    return pl.DataFrame(out, schema={**OBSERVATION_SCHEMA, PCT_FULL: pl.Float64()})


class AnglianAdapter:
    meta = SourceMeta(
        id="uk-anglian",
        country="UK",
        name="Anglian Water — Monitoring water resources",
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
        return parse_levels_table(raw.decode("utf-8", errors="replace"))
