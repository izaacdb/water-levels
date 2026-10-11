"""Germany (Saxony): the state reservoir authority's control centre.

The Landestalsperrenverwaltung des Freistaates Sachsen (LTV) publishes, several
times a day, each of its dams' current content ("Inhalt", Mio m³) on one overview
page. Only reservoirs (TS, Talsperre) are kept: flood-retention basins (HRB) are
empty by design. Content only: capacities come from the registry (D7), built from
each dam's own page, which lists its storage zones under the water management plan.
There is no published history, so ours starts with the first run (like Czechia).
"""

from __future__ import annotations

import html
import re
from datetime import datetime

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta, slugify

URL = "https://www.ltv.sachsen.de/tsz/"
_TABLE = re.compile(r'<table[^>]*id="Tab_(\d+)".*?</table>', re.S)
_HEADER = re.compile(r"^(TS|HRB|WS) (.+?) Messwerte vom: (\d{2}\.\d{2}\.\d{4})")
_CONTENT = re.compile(r"Inhalt \[Mio\.? ?m³\] ([\d.,]+)")
_ZONE = re.compile(
    r"(Totraum|Reserveraum|Betriebsraum|[\w\- ]*Hochwasser[\w\- ]*raum) ([\d,]+) ([\d,]+)"
)


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _number(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def parse_overview(page: str) -> pl.DataFrame:
    out, seen = [], set()
    for match in _TABLE.finditer(page):
        text = _text(match.group(0))
        header, content = _HEADER.match(text), _CONTENT.search(text)
        if not header or not content or header.group(1) != "TS":
            continue
        name = header.group(2).strip()
        key = slugify(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_key": key,
                "name": name,
                "group": "LTV Sachsen",
                "observed_on": datetime.strptime(header.group(3), "%d.%m.%Y").date(),
                "volume_hm3": _number(content.group(1)),  # Mio m³ = hm³
                "capacity_hm3": None,
            }
        )
    if not out:
        raise ValueError("no reservoir contents on the LTV overview page")
    return pl.DataFrame(out, schema=OBSERVATION_SCHEMA)


def parse_storage_zones(page: str) -> float:
    """A dam page's full-supply storage: the cumulative content at the top of its
    highest zone below the flood-retention space (usually the Betriebsraum)."""
    text = _text(page)
    start = text.find("Stauraumaufteilung")
    zones = _ZONE.findall(text[start : start + 1000]) if start >= 0 else []
    below_flood = [_number(cumulative) for name, _, cumulative in zones if "Hochwasser" not in name]
    if not below_flood:
        raise ValueError("no storage zones on the dam page")
    return max(below_flood)


class LtvAdapter:
    meta = SourceMeta(
        id="de-ltv",
        country="DE",
        name="Landestalsperrenverwaltung Sachsen — Talsperrensteuerzentrale",
        url=URL,
        cadence="daily",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        response = client.get(URL, timeout=60, follow_redirects=True)
        response.raise_for_status()
        return response.content

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_overview(raw.decode("iso-8859-1"))
