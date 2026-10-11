"""Greece (Athens): EYDAP's raw water reserves.

EYDAP, the state-controlled Athens water and sewerage company, publishes the daily
volume (m³) in each of the four reservoirs that supply Athens: Mornos, Evinos, Yliki
and Marathon. Its "raw water reserves" page loads a table from a plain GET endpoint,
for a day, week, month or year ending on a given date, back to 1985. Volumes only:
capacities come from the registry (D7).
"""

from __future__ import annotations

import html
import logging
import re
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta

log = logging.getLogger(__name__)

DATA = "https://www.eydap.gr/en/Controls/GeneralControls/SavingsDetailsDataHub.aspx"
FIRST_YEAR = 1985
# Column header -> (our key, official name). E10: names as EYDAP publishes them.
RESERVOIRS = {
    "ΜΟΡΝΟΣ": ("mornos", "Μόρνος"),
    "ΕΥΗΝΟΣ": ("evinos", "Εύηνος"),
    "ΥΛΙΚΗ": ("yliki", "Υλίκη"),
    "ΜΑΡΑΘΩΝΑΣ": ("marathonas", "Μαραθώνας"),
}
# E12: EYDAP lists Evinos as 0 until it started filling.
COMMISSIONED = {"evinos": date(2001, 12, 27)}
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140 Safari/537.36 water-levels"
)


def _today() -> date:
    return datetime.now(UTC).date()


def _cells(row: str) -> list[str]:
    return [
        " ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())
        for c in re.findall(r"<t[dh][^>]*>.*?</t[dh]>", row, re.S)
    ]


def parse_reserves(page: str) -> pl.DataFrame:
    rows = [_cells(r) for r in re.findall(r"<tr.*?</tr>", page, re.S)]
    if len(rows) < 2:
        raise ValueError("no reserves in the EYDAP table")
    header = rows[0]
    out = []
    for row in rows[1:]:
        day = datetime.strptime(row[0], "%d/%m/%Y").date()
        for column, value in zip(header[1:], row[1:], strict=False):
            if column not in RESERVOIRS:
                continue  # "Σύνολο": the total
            key, name = RESERVOIRS[column]
            if (key in COMMISSIONED and day < COMMISSIONED[key]) or not value:
                continue  # E12, or a day EYDAP left blank
            out.append(
                {
                    "source_key": key,
                    "name": name,
                    "group": "ΕΥΔΑΠ",
                    "observed_on": day,
                    "volume_hm3": float(value.replace(",", "")) / 1e6,  # m³ -> hm³
                    "capacity_hm3": None,
                }
            )
    return pl.DataFrame(out, schema=OBSERVATION_SCHEMA).unique(
        subset=["source_key", "observed_on"], keep="last", maintain_order=True
    )


class EydapAdapter:
    meta = SourceMeta(
        id="el-eydap",
        country="EL",
        name="ΕΥΔΑΠ — Αποθέματα ταμιευτήρων (raw water reserves)",
        url="https://www.eydap.gr/en/TheCompany/Water/Savings/",
        cadence="daily",
    )

    def _table(self, client: httpx.Client, span: str, day: date) -> bytes:
        response = client.get(
            DATA,
            params={"DaysSpan": span, "Date": f"{day:%d-%m-%Y}"},
            headers={"User-Agent": _BROWSER_UA},
            timeout=120,
        )
        response.raise_for_status()
        return response.content

    def fetch(self, client: httpx.Client) -> bytes:
        return self._table(client, "Week", _today())

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        """One table per calendar year, oldest first, then the year to today."""
        ends = [date(year, 12, 31) for year in range(FIRST_YEAR, _today().year)] + [_today()]
        for end in ends:
            time.sleep(1)
            try:
                yield self._table(client, "Year", end)
            except httpx.HTTPError as err:
                log.warning("el-eydap: skipping the year to %s: %s", end, err)

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_reserves(raw.decode("utf-8", errors="replace"))
