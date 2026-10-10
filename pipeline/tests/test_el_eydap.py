from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from pipeline.adapters.el_eydap import EydapAdapter, parse_reserves

FIXTURES = Path(__file__).parent / "fixtures" / "el"
WEEK = (FIXTURES / "eydap-week-2026-10-09.html").read_text()
YEAR_2001 = (FIXTURES / "eydap-year-2001.html").read_text()


def test_daily_volumes_per_reservoir() -> None:
    obs = parse_reserves(WEEK)
    assert set(obs["source_key"]) == {"mornos", "evinos", "yliki", "marathonas"}
    assert obs["observed_on"].max() == date(2026, 10, 9)
    row = obs.filter(
        (pl.col("source_key") == "mornos") & (pl.col("observed_on") == date(2026, 10, 9))
    ).row(0, named=True)
    assert row["name"] == "Μόρνος"  # E10: the official name
    assert row["volume_hm3"] == pytest.approx(371.603)
    assert row["capacity_hm3"] is None  # from the registry (D7)


def test_evinos_is_not_imported_before_it_was_commissioned() -> None:
    """E12: EYDAP lists Evinos as 0 until it started filling in December 2001."""
    obs = parse_reserves(YEAR_2001)
    evinos = obs.filter(pl.col("source_key") == "evinos")
    assert evinos["observed_on"].min() == date(2001, 12, 27)
    assert (evinos["volume_hm3"] > 0).all()
    assert obs.filter(pl.col("source_key") == "mornos").height == 366


def test_an_empty_table_is_an_error() -> None:
    with pytest.raises(ValueError, match="no reserves"):
        parse_reserves("<table><tr><th>Ημερομηνία</th></tr></table>")


def test_live_fetch_asks_for_the_week_to_today_and_history_for_each_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pipeline.adapters.el_eydap.time.sleep", lambda _: None)
    monkeypatch.setattr("pipeline.adapters.el_eydap._today", lambda: date(2026, 10, 10))
    asked: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append((request.url.params["DaysSpan"], request.url.params["Date"]))
        return httpx.Response(200, text=WEEK)

    adapter = EydapAdapter()
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter.parse(adapter.fetch(client))
        history = list(adapter.fetch_history(client))
    assert asked[0] == ("Week", "10-10-2026")
    assert asked[1] == ("Year", "31-12-1985")
    assert asked[-2] == ("Year", "31-12-2025")
    assert asked[-1] == ("Year", "10-10-2026")  # this year so far
    assert len(history) == 42
