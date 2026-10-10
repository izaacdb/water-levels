"""Common shape for every official source adapter."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx
import polars as pl

# Every adapter's parse() returns rows in exactly this shape: one row per
# reservoir per published date, in the source's own units converted to hm³.
OBSERVATION_SCHEMA: dict[str, pl.DataType] = {
    "source_key": pl.String(),
    "name": pl.String(),
    "group": pl.String(),  # the source's own grouping (basin, directorate, ...)
    "observed_on": pl.Date(),
    "volume_hm3": pl.Float64(),
    "capacity_hm3": pl.Float64(),
}
# Sources that publish only % full may add this column; volume and capacity are then
# completed from the registry's capacity when the rows are mapped (D7).
PCT_FULL = "pct_full"

Cadence = Literal["daily", "weekly", "monthly"]


@dataclass(frozen=True)
class SourceMeta:
    id: str
    country: str
    name: str
    url: str
    cadence: Cadence = "weekly"


class PartialFetch(Exception):
    """Only part of a source was reachable: `raw` holds what arrived and can be parsed."""

    def __init__(self, raw: bytes, cause: object) -> None:
        super().__init__(str(cause))
        self.raw = raw


class SourceAdapter(Protocol):
    meta: SourceMeta

    def fetch(self, client: httpx.Client) -> bytes:
        """Download the raw publication."""
        ...

    def parse(self, raw: bytes) -> pl.DataFrame:
        """Turn a raw publication into rows matching OBSERVATION_SCHEMA."""
        ...


def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
