"""United Kingdom: Severn Trent and Hafren Dyfrdwy weekly raw water storage pages.

Both companies publish a page per week ("Raw water storage levels <date>") with each
reservoir's capacity and current storage in megalitres. Group rows (for example
"Derwent Valley", "including" Howden, Derwent and Ladybower) are subtotals of the
rows beneath them, so only the member reservoirs are kept. Every past week stays
online, which gives history back to January 2023.
"""

from __future__ import annotations

import base64
import calendar
import html
import json
import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PCT_FULL, SourceMeta, slugify

log = logging.getLogger(__name__)

_MONTHS = {calendar.month_name[i].lower(): i for i in range(1, 13)}
_SLUG_DATE = re.compile(r"-(\d{1,2})-([a-z]+)-(\d{4})")
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140 Safari/537.36 water-levels"
)


@dataclass(frozen=True)
class StorageSite:
    source_id: str
    name: str
    site: str
    # Published here but owned by another company we also cover (E11).
    exclude: frozenset[str] = field(default_factory=frozenset)

    @property
    def listing(self) -> str:
        return f"{self.site}/about-us/reservoir-levels/"


SEVERN_TRENT = StorageSite(
    source_id="uk-severn-trent",
    name="Severn Trent — Raw water storage levels",
    site="https://www.stwater.co.uk",
    exclude=frozenset({"clywedog"}),  # Llyn Clywedog: Hafren Dyfrdwy's
)
HAFREN_DYFRDWY = StorageSite(
    source_id="uk-hafren-dyfrdwy",
    name="Hafren Dyfrdwy — Raw water storage levels",
    site="https://www.hdcymru.co.uk",
)


def page_date(slug: str) -> date:
    """'raw-water-storage-levels-05-october-2026' -> 2026-10-05 (also copes with '20231')."""
    m = _SLUG_DATE.search(slug)
    if not m or m.group(2) not in _MONTHS:
        raise ValueError(f"no date in {slug!r}")
    return date(int(m.group(3)[:4]), _MONTHS[m.group(2)], int(m.group(1)))


def _cells(row: str) -> list[str]:
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
        for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)
    ]


def _number(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _name(raw: str) -> str:
    return raw.title() if raw.isupper() else raw


def parse_storage_page(page: str, day: date, site: StorageSite) -> pl.DataFrame:
    rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", page, re.S)]
    # A reservoir row: [name, member name, capacity Ml, storage %, storage Ml, ...].
    data = [r for r in rows if len(r) >= 5 and _number(r[2]) is not None]
    out = []
    for i, row in enumerate(data):
        name = row[0] or row[1]
        if not name or name.upper() == "TOTALS":
            continue
        has_members = bool(row[0]) and i + 1 < len(data) and not data[i + 1][0]
        if has_members:
            continue  # a group subtotal; its member rows follow
        key = slugify(name)
        capacity, pct, storage = _number(row[2]), _number(row[3]), _number(row[4])
        if key in site.exclude or capacity is None or storage is None:
            continue
        out.append(
            {
                "source_key": key,
                "name": _name(name),
                "group": site.name.split(" — ")[0],
                "observed_on": day,
                "volume_hm3": storage / 1000,  # Ml -> hm³
                "capacity_hm3": capacity / 1000,
                PCT_FULL: pct,
            }
        )
    return pl.DataFrame(out, schema={**OBSERVATION_SCHEMA, PCT_FULL: pl.Float64()})


class StoragePagesAdapter:
    def __init__(self, site: StorageSite) -> None:
        self.site = site
        self.meta = SourceMeta(
            id=site.source_id, country="UK", name=site.name, url=site.listing, cadence="weekly"
        )

    def _get(self, client: httpx.Client, url: str) -> str:
        response = client.get(
            url, headers={"User-Agent": _BROWSER_UA}, timeout=60, follow_redirects=True
        )
        response.raise_for_status()
        return response.text

    def _pages(self, client: httpx.Client) -> list[tuple[date, str]]:
        """Every weekly page, oldest first."""
        listing = self._get(client, self.site.listing)
        paths = set(
            re.findall(r'href="(/about-us/reservoir-levels/raw-water-storage-[^"]+)"', listing)
        )
        dated = []
        for path in paths:
            try:
                dated.append((page_date(path), path))
            except ValueError:
                log.warning("%s: no date in %s", self.meta.id, path)
        if not dated:
            raise ValueError(f"no weekly pages listed on {self.site.listing}")
        return sorted(dated)

    def _envelope(self, client: httpx.Client, day: date, path: str) -> bytes:
        page = self._get(client, self.site.site + path)
        return json.dumps(
            {"date": day.isoformat(), "html": base64.b64encode(page.encode()).decode()}
        ).encode()

    def fetch(self, client: httpx.Client) -> bytes:
        day, path = self._pages(client)[-1]
        return self._envelope(client, day, path)

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        for day, path in self._pages(client)[:-1]:
            time.sleep(1)  # be gentle with the company's site
            try:
                yield self._envelope(client, day, path)
            except httpx.HTTPError as err:
                log.warning("%s: skipping %s: %s", self.meta.id, path, err)

    def parse(self, raw: bytes) -> pl.DataFrame:
        envelope = json.loads(raw)
        page = base64.b64decode(envelope["html"]).decode()
        return parse_storage_page(page, date.fromisoformat(envelope["date"]), self.site)
