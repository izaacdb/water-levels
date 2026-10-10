from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline.adapters.base import PCT_FULL
from pipeline.adapters.uk_anglian import AnglianAdapter, parse_levels_table

PAGE = (Path(__file__).parent / "fixtures" / "uk" / "anglian-2026-10-05.html").read_bytes()


def test_percent_only_rows_with_the_table_date() -> None:
    obs = parse_levels_table(PAGE.decode())
    by_key = {r["source_key"]: r for r in obs.to_dicts()}
    assert set(by_key) == {"alton", "ardleigh", "covenham", "grafham", "pitsford", "rutland"}
    rutland = by_key["rutland"]
    assert (rutland["name"], rutland["observed_on"], rutland[PCT_FULL]) == (
        "Rutland",
        date(2026, 10, 5),
        67.64,
    )
    # % only: volume and capacity come from the registry (D7).
    assert (rutland["volume_hm3"], rutland["capacity_hm3"]) == (None, None)


def test_a_page_without_the_table_is_an_error() -> None:
    with pytest.raises(ValueError, match="no reservoir levels table"):
        parse_levels_table("<html><table><tr><td>Property List</td></tr></table></html>")


def test_fetch_and_metadata() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=PAGE))
    with httpx.Client(transport=transport) as client:
        adapter = AnglianAdapter()
        assert adapter.parse(adapter.fetch(client)).height == 6
    assert (adapter.meta.id, adapter.meta.country, adapter.meta.cadence) == (
        "uk-anglian",
        "UK",
        "weekly",
    )
