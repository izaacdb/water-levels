"""Portugal: APA weekly reservoir bulletin (Boletim semanal de albufeiras).

The official per-reservoir figures are only published as a PDF that is
overwritten every week. SNIRH's data portal refuses automated access, so the
history is backfilled from Internet Archive captures of the same official
bulletin (two URLs over the years, two table layouts; both are handled).
"""

from __future__ import annotations

import io
import logging
import re
import time
from collections.abc import Iterator
from datetime import date

import httpx
import pdfplumber
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta, slugify

log = logging.getLogger(__name__)

BULLETIN_URL = (
    "https://apambiente.pt/sites/default/files/_SNIAMB_Agua/DRH/MonitorizacaoAvaliacao/"
    "BoletimAlbufeiras/Semanal.pdf"
)
ARCHIVED_URLS = [BULLETIN_URL, "https://snirh.apambiente.pt/snirh/download/semanal.pdf"]
CDX = "https://web.archive.org/cdx/search/cdx"

_CONNECTORS = re.compile(r"\b(de|do|da|dos|das|e)\b", re.IGNORECASE)
_NOTES = re.compile(r"\((?:B|\d+)\)")
_DATE = re.compile(r"(\d{2})[-/](\d{2})[-/](\d{2,4})")


class ApaAdapter:
    meta = SourceMeta(
        id="pt-apa",
        country="PT",
        name="APA — Boletim semanal de albufeiras",
        url="https://snirh.apambiente.pt/index.php?idMain=1&idItem=7",
    )

    def fetch(self, client: httpx.Client) -> bytes:
        response = client.get(BULLETIN_URL, follow_redirects=True, timeout=120)
        response.raise_for_status()
        return response.content

    def parse(self, raw: bytes) -> pl.DataFrame:
        return parse_bulletin(raw)[0]

    def fetch_history(self, client: httpx.Client) -> Iterator[bytes]:
        """Every distinct archived edition of the bulletin, oldest first."""
        for url in ARCHIVED_URLS:
            index = client.get(
                CDX,
                params={
                    "url": url.split("://", 1)[1],
                    "output": "json",
                    "filter": "statuscode:200",
                    "collapse": "digest",
                    "fl": "timestamp,original",
                },
                timeout=120,
            )
            index.raise_for_status()
            for capture in archived_captures(index.json()):
                try:
                    response = client.get(capture, follow_redirects=True, timeout=120)
                    response.raise_for_status()
                    yield response.content
                except httpx.HTTPError as err:
                    log.warning("skipping archived bulletin %s: %s", capture, err)
                time.sleep(1)  # be gentle with the Internet Archive


def archived_captures(cdx_rows: list[list[str]]) -> list[str]:
    """Raw-content URLs for each capture in a CDX JSON response (first row is the header)."""
    return [f"https://web.archive.org/web/{ts}id_/{original}" for ts, original in cdx_rows[1:]]


def display_name(raw: str) -> str:
    """'ALTO LINDOSO (B)' / 'Alto Lindoso' -> 'Alto Lindoso'."""
    name = " ".join(_NOTES.sub("", raw).split())
    if name.isupper():
        name = " ".join(
            w.lower() if w.lower() in {"de", "do", "da", "dos", "das", "e"} else w.capitalize()
            for w in name.split(" ")
        )
        name = "-".join(p[:1].upper() + p[1:] for p in name.split("-"))
    return name


def source_key(name: str) -> str:
    # Connector words vary between editions ("Vale de Gaio" / "Vale do Gaio").
    return slugify(_CONNECTORS.sub(" ", display_name(name)))


def _number(cell: str | None) -> float | None:
    text = (cell or "").replace(" ", "").replace(" ", "").replace(" ", "")
    text = text.replace("%", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _column(header: list[str], *needles: str, avoid: str = "\x00") -> int:
    for i, cell in enumerate(header):
        flat = cell.replace("\n", " ")
        if all(n in flat for n in needles) and avoid not in flat:
            return i
    raise ValueError(f"no column with {needles} in {header}")


def parse_bulletin(raw: bytes) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Returns (observations, published % per reservoir for reconciliation)."""
    rows: list[dict[str, object]] = []
    published: list[dict[str, object]] = []
    seen: set[str] = set()
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                header = [c or "" for c in table[0]]
                if not any("Albufeira" in c for c in header):
                    continue
                observed = _observed_on(header)
                i_basin = _column(header, "Bacia")
                i_name = _column(header, "Albufeira")
                i_cap = _column(header, "Capacidade")
                i_vol = _column(header, "dam", avoid="Capacidade")
                i_pct = _column(header, "%", avoid="Diferen")
                basin = ""
                for cells in table[1:]:
                    basin_cell = cells[i_basin]
                    if basin_cell:
                        basin = " ".join(basin_cell.split())
                    name = cells[i_name] or ""
                    key = source_key(name)
                    volume, capacity = _number(cells[i_vol]), _number(cells[i_cap])
                    if not key or key in seen or volume is None or not capacity:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "source_key": key,
                            "name": display_name(name),
                            "group": basin,
                            "observed_on": observed,
                            "volume_hm3": volume / 1000,  # dam³ -> hm³
                            "capacity_hm3": capacity / 1000,
                        }
                    )
                    published.append({"source_key": key, "published_pct": _number(cells[i_pct])})
    obs = pl.DataFrame(rows, schema=OBSERVATION_SCHEMA)
    return obs, pl.DataFrame(
        published, schema={"source_key": pl.String, "published_pct": pl.Float64}
    )


def _observed_on(header: list[str]) -> date:
    for cell in header:
        match = _DATE.search(cell)
        if match:
            day, month, year = match.groups()
            return date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    raise ValueError(f"no date in bulletin header {header}")
