"""Czechia: the five state river-basin enterprises (Povodí ..., státní podnik).

Each publishes near-real-time reservoir volumes on the same portal software
("Objemy" page). We use the conservation storage (zásobní prostor): volume is
its filled part, capacity is filled + free. None of the portals offers
history, so the pipeline's own archive builds it from the day ingestion starts.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from urllib.parse import unquote

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PartialFetch, SourceMeta, slugify


@dataclass(frozen=True)
class Enterprise:
    slug: str
    name: str
    url: str


ENTERPRISES = [
    Enterprise("labe", "Povodí Labe", "https://www.pla.cz/portal/nadrze/cz/Objemy.aspx"),
    Enterprise("vltava", "Povodí Vltavy", "https://www.pvl.cz/portal/nadrze/cz/Objemy.aspx"),
    Enterprise("ohre", "Povodí Ohře", "https://sap.poh.cz/portal/nadrze/cz/Objemy.aspx"),
    Enterprise("odra", "Povodí Odry", "https://www.pod.cz/portal/Nadrze/cz/Objemy.aspx"),
    Enterprise("morava", "Povodí Moravy", "https://sap.pmo.cz/portal/nadrze/cz/Objemy.aspx"),
]
_STAMP = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140 Safari/537.36 water-levels"
)
_TIMER = "ctl00$ObsahCPH$RefreshTimer"  # the wait page's postback timer


def _cells(row: str) -> list[str]:
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
        for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)
    ]


def _num(text: str) -> float | None:
    try:
        return float(text.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def parse_volumes_page(page: str, enterprise: str) -> pl.DataFrame:
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", page, re.S):
        cells = _cells(tr)
        if len(cells) < 6 or not (stamp := _STAMP.match(cells[2])):
            continue
        filled, free = _num(cells[3]), _num(cells[5])
        if filled is None or free is None or filled + free <= 0:
            continue
        name = re.sub(r"^VD\s+", "", cells[0]).strip()
        day, month, year = map(int, stamp.groups())
        rows.append(
            {
                "source_key": slugify(name),
                "name": name,
                "group": enterprise,
                "observed_on": date(year, month, day),
                "volume_hm3": filled,
                "capacity_hm3": filled + free,
            }
        )
    return pl.DataFrame(rows, schema=OBSERVATION_SCHEMA)


def _delta_parts(text: str) -> Iterator[tuple[str, str, str]]:
    """(type, id, content) from an ASP.NET AJAX partial-postback response,
    which is a run of `length|type|id|content|` records."""
    i = 0
    try:
        while i < len(text):
            length_end = text.index("|", i)
            kind_end = text.index("|", length_end + 1)
            id_end = text.index("|", kind_end + 1)
            start, length = id_end + 1, int(text[i:length_end])
            yield (
                text[length_end + 1 : kind_end],
                text[kind_end + 1 : id_end],
                text[start : start + length],
            )
            i = start + length + 1
    except ValueError:
        return  # not a delta response


def _wait_out(client: httpx.Client, wait: httpx.Response, polls: int = 30) -> str | None:
    """Do what the wait page's own timer does in a browser: post back until the
    server answers with a redirect to the prepared page."""
    fields = {
        m.group(1): html.unescape(m.group(2))
        for m in re.finditer(r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', wait.text)
    }
    for _ in range(polls):
        time.sleep(1)
        response = client.post(
            wait.url,
            data={
                **fields,
                "ctl00$ObsahCPH$ScriptManager1": f"ctl00$ObsahCPH$UpdatePanel1|{_TIMER}",
                "__EVENTTARGET": _TIMER,
                "__EVENTARGUMENT": "",
                "__ASYNCPOST": "true",
            },
            headers={"User-Agent": _BROWSER_UA, "X-MicrosoftAjax": "Delta=true"},
            timeout=60,
        )
        response.raise_for_status()
        for kind, id_, content in _delta_parts(response.text):
            if kind == "hiddenField":
                fields[id_] = content
            elif kind == "pageRedirect":
                page = client.get(
                    wait.url.join(unquote(content)),
                    headers={"User-Agent": _BROWSER_UA},
                    timeout=60,
                    follow_redirects=True,
                )
                page.raise_for_status()
                return None if "WaitPage" in str(page.url) else page.text
    return None


def _fetch_page(client: httpx.Client, url: str, attempts: int = 6) -> str:
    """The portals bounce to WaitPage.aspx while they prepare data. Wait it out the
    way a browser does; failing that, start over without cookies."""
    for attempt in range(attempts):
        client.cookies.clear()
        response = client.get(
            url, headers={"User-Agent": _BROWSER_UA}, timeout=60, follow_redirects=True
        )
        response.raise_for_status()
        if "WaitPage" not in str(response.url):
            return response.text
        if (page := _wait_out(client, response)) is not None:
            return page
        time.sleep(2 + 2 * attempt)
    raise RuntimeError(f"{url} still showing its wait page after {attempts} attempts")


class PovodiAdapter:
    meta = SourceMeta(
        id="cz-povodi",
        country="CZ",
        name="Povodí state enterprises — reservoir conservation storage",
        url="https://www.pvl.cz/portal/nadrze/cz/index.htm",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        """All five enterprises' pages, bundled as JSON {enterprise name: html}.

        One portal being down mustn't hide the other four: their pages are
        published and the source is reported as partly failed."""
        pages: dict[str, str] = {}
        failures: dict[str, Exception] = {}
        for e in ENTERPRISES:
            try:
                pages[e.name] = _fetch_page(client, e.url)
            except (httpx.HTTPError, RuntimeError) as err:
                failures[e.name] = err
        if not pages:
            raise next(iter(failures.values()))
        raw = json.dumps(pages).encode()
        if failures:
            raise PartialFetch(raw, "; ".join(f"{name}: {err}" for name, err in failures.items()))
        return raw

    def parse(self, raw: bytes) -> pl.DataFrame:
        bundle: dict[str, str] = json.loads(raw)
        frames = [parse_volumes_page(page, name) for name, page in bundle.items()]
        return pl.concat(frames).unique(subset="source_key", keep="first", maintain_order=True)
