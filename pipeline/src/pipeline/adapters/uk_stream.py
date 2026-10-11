"""United Kingdom: water companies' reservoir storage on Stream, the industry's open-data portal.

Stream is an ArcGIS Hub. Each company publishes reservoir levels as feature services,
often one per year, all with the same fields (RESERVOIR_NAME, DATE, CAPACITY,
CURRENT_LEVEL, CURRENT_PERCENTAGE and their units). Datasets are found through the
Hub's search API, so a new year's dataset is picked up without a code change.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PCT_FULL, Cadence, SourceMeta, slugify

log = logging.getLogger(__name__)

HUB = "https://www.streamwaterdata.co.uk"
SEARCH = f"{HUB}/api/search/v1/collections/all/items"
PAGE = 2000

# Units seen on Stream, as hm³ per unit.
_TO_HM3 = {"ml": 1e-3, "tcm": 1e-3, "m3": 1e-6, "mcm": 1.0}
_SUFFIX = re.compile(r"\s+(IRE|ESR|Reservoir)$", re.IGNORECASE)
_YEAR = re.compile(r"(\d{4})\s*$")


@dataclass(frozen=True)
class StreamCompany:
    source_id: str
    name: str
    url: str
    dataset_prefix: str  # e.g. "Yorkshire Water Reservoir Levels" (+ a year, or nothing)
    owner: str
    cadence: Cadence = "weekly"
    # When a company's datasets overlap, read only these titles.
    titles: tuple[str, ...] = ()


YORKSHIRE = StreamCompany(
    source_id="uk-yorkshire",
    name="Yorkshire Water — Reservoir levels",
    url=f"{HUB}/search?q=Yorkshire%20Water%20Reservoir%20Levels",
    dataset_prefix="Yorkshire Water Reservoir Levels",
    owner="ywAGOLstreamData",
)
# These publish weekly or daily readings, but only every month or so (B3′, B24′).
WESSEX = StreamCompany(
    source_id="uk-wessex",
    name="Wessex Water — Reservoir levels",
    url=f"{HUB}/search?q=Wessex%20Water%20Reservoir%20Levels",
    dataset_prefix="Wessex Water Reservoir Levels",
    owner="WessexWaterData",
    cadence="monthly",
)
SOUTHERN = StreamCompany(
    source_id="uk-southern",
    name="Southern Water — Reservoir levels",
    url=f"{HUB}/search?q=Southern%20Water%20Monthly%20Reservoir%20Levels",
    dataset_prefix="Southern Water Monthly Reservoir Levels",
    owner="DSlidel_southernwater",
    cadence="monthly",
    titles=("Southern Water Monthly Reservoir Levels 2002 to Present",),
)
SOUTH_WEST = StreamCompany(
    source_id="uk-south-west",
    name="South West Water — Reservoir levels",
    url=f"{HUB}/search?q=South%20West%20Water%20Reservoir%20Levels",
    dataset_prefix="South West Water (SWB) Reservoir Levels",
    owner="JEvans_Pennon",
    cadence="monthly",
)
SES = StreamCompany(
    source_id="uk-ses",
    name="SES Water — Reservoir levels",
    url=f"{HUB}/search?q=SES%20Water%20Reservoir%20Levels",
    dataset_prefix="SES Water Reservoir Levels",
    owner="SESWater2",
    cadence="monthly",
)
# Not included: South Staffs Water (its feed ends in March 2026 and swaps day and
# month in some dates) and Dŵr Cymru Welsh Water (no data after December 2024).
STREAM_COMPANIES = [YORKSHIRE, WESSEX, SOUTHERN, SOUTH_WEST, SES]


def display_name(raw: str) -> str:
    """'SCAR HOUSE IRE' -> 'Scar House' (IRE: impounding reservoir)."""
    name = _SUFFIX.sub("", " ".join(raw.split()))
    return name.title() if name.isupper() else name


def _date(row: dict[str, object]) -> date | None:
    value = row.get("DATE_ISO") or row.get("DATE")
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value / 1000, UTC).date()
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
            return datetime.strptime(text, "%d/%m/%Y").date()
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None
    return None


def _float(value: object) -> float | None:
    try:
        return None if value is None else float(str(value))
    except ValueError:
        return None


def _hm3(value: object, units: object) -> float | None:
    amount, factor = _float(value), _TO_HM3.get(str(units or "").strip().lower())
    return None if amount is None or factor is None else amount * factor


def parse_rows(rows: list[dict[str, object]], group: str) -> pl.DataFrame:
    out = []
    for row in rows:
        name, day = str(row.get("RESERVOIR_NAME") or "").strip(), _date(row)
        pct = _float(row.get("CURRENT_PERCENTAGE"))
        if not name or day is None or pct is None:
            continue
        capacity = _hm3(row.get("CAPACITY"), row.get("CAPACITY_UNITS")) or None  # 0 = unknown
        # CURRENT_LEVEL is sometimes a height (ft, m below top water level), not a volume.
        volume = _hm3(row.get("CURRENT_LEVEL"), row.get("CURRENT_LEVEL_UNITS"))
        if volume is None and capacity is not None:
            volume = pct / 100 * capacity
        out.append(
            {
                "source_key": slugify(display_name(name)),
                "name": display_name(name),
                "group": group,
                "observed_on": day,
                "volume_hm3": volume,
                "capacity_hm3": capacity,
                PCT_FULL: pct,
            }
        )
    return pl.DataFrame(out, schema={**OBSERVATION_SCHEMA, PCT_FULL: pl.Float64()})


class StreamAdapter:
    def __init__(self, company: StreamCompany) -> None:
        self.company = company
        self.meta = SourceMeta(
            id=company.source_id,
            country="UK",
            name=company.name,
            url=company.url,
            cadence=company.cadence,
        )

    def _datasets(self, client: httpx.Client) -> list[str]:
        """The company's feature-service URLs, oldest first ('… 2002 to Present' last)."""
        response = client.get(
            SEARCH, params={"q": self.company.dataset_prefix, "limit": 100}, timeout=60
        )
        response.raise_for_status()
        found = []
        for feature in response.json()["features"]:
            p = feature["properties"]
            title = str(p.get("title") or "")
            if (
                p.get("type") == "Feature Service"
                and p.get("owner") == self.company.owner
                and title.startswith(self.company.dataset_prefix)
                and (not self.company.titles or title in self.company.titles)
            ):
                year = _YEAR.search(title)
                found.append((int(year.group(1)) if year else 9999, p["url"]))
        if not found:
            raise ValueError(f"no Stream datasets found for {self.company.dataset_prefix!r}")
        return [url for _, url in sorted(found)]

    def _rows(self, client: httpx.Client, service: str) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        while True:
            response = client.get(
                f"{service.rstrip('/')}/0/query",
                params={
                    "where": "1=1",
                    "outFields": "*",
                    "returnGeometry": "false",
                    "resultOffset": len(rows),
                    "resultRecordCount": PAGE,
                    "f": "json",
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise ValueError(f"{service}: {data['error']}")
            rows += [f["attributes"] for f in data["features"]]
            if not data.get("exceededTransferLimit") or not data["features"]:
                return rows

    def fetch(self, client: httpx.Client) -> bytes:
        return json.dumps(self._rows(client, self._datasets(client)[-1])).encode()

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        """Every earlier dataset, oldest first; the latest one is the live fetch."""
        for service in self._datasets(client)[:-1]:
            try:
                yield json.dumps(self._rows(client, service)).encode()
            except (httpx.HTTPError, ValueError) as err:
                log.warning("skipping Stream dataset %s: %s", service, err)

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_rows(json.loads(raw), self.company.name.split(" — ")[0])
