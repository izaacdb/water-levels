from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from pipeline.adapters.de_ltv import LtvAdapter, parse_overview, parse_storage_zones

FIXTURES = Path(__file__).parent / "fixtures" / "de"
OVERVIEW = (FIXTURES / "ltv-tsz-2026-10-10.html").read_bytes().decode("iso-8859-1")
EIBENSTOCK = (FIXTURES / "ltv-pegel-403.html").read_bytes().decode("iso-8859-1")


def test_reads_each_reservoirs_content_and_reading_date() -> None:
    obs = parse_overview(OVERVIEW)
    bautzen = obs.filter(pl.col("source_key") == "bautzen").row(0, named=True)
    assert (bautzen["name"], bautzen["observed_on"], bautzen["group"]) == (
        "Bautzen",
        date(2026, 10, 10),
        "LTV Sachsen",
    )
    assert bautzen["volume_hm3"] == pytest.approx(19.008)
    assert bautzen["capacity_hm3"] is None  # from the registry (D7)
    klingenberg = obs.filter(pl.col("source_key") == "klingenberg")["volume_hm3"].item()
    assert klingenberg == pytest.approx(11.789)  # "Inhalt [Mio.m³]" is spelt both ways


def test_only_reservoirs_are_kept() -> None:
    """Flood-retention basins (HRB) are empty by design and side storages (WS) aren't
    reservoirs in their own right, so neither belongs in a % full comparison."""
    obs = parse_overview(OVERVIEW)
    assert 25 <= obs.height <= 33
    assert "liebstadt" not in obs["source_key"].to_list()  # HRB Liebstadt
    assert "borna-nebenschluss" not in obs["source_key"].to_list()  # WS Borna
    assert obs["source_key"].is_unique().all()


def test_storage_zones_give_the_full_supply_capacity() -> None:
    """Capacity is the top of the operating zone: flood-retention space isn't 'full'."""
    assert parse_storage_zones(EIBENSTOCK) == pytest.approx(64.636)


def test_fetch_and_metadata() -> None:
    raw = (FIXTURES / "ltv-tsz-2026-10-10.html").read_bytes()
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=raw))
    with httpx.Client(transport=transport) as client:
        adapter = LtvAdapter()
        assert adapter.parse(adapter.fetch(client)).height > 20
    assert (adapter.meta.id, adapter.meta.country, adapter.meta.cadence) == (
        "de-ltv",
        "DE",
        "daily",
    )
