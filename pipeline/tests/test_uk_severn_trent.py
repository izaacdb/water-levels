from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from pipeline.adapters.uk_severn_trent import (
    HAFREN_DYFRDWY,
    SEVERN_TRENT,
    StoragePagesAdapter,
    page_date,
    parse_storage_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "uk"
ST_PAGE = (FIXTURES / "st-2026-10-05.html").read_text()
HD_PAGE = (FIXTURES / "hd-2026-10-05.html").read_text()


def test_groups_are_replaced_by_their_reservoirs() -> None:
    obs = parse_storage_page(ST_PAGE, date(2026, 10, 5), SEVERN_TRENT)
    keys = obs["source_key"].to_list()
    # "Derwent Valley (including Howden, Derwent, Ladybower)" is a subtotal, not a reservoir.
    assert {"howden", "derwent", "ladybower"} <= set(keys)
    assert "derwent-valley" not in keys
    assert {"foremark", "staunton", "swithland", "cropston", "carsington"} <= set(keys)
    assert "totals" not in keys
    # Clywedog is published by both companies; it's kept once, under Hafren Dyfrdwy (E11).
    assert "clywedog" not in keys
    row = obs.filter(pl.col("source_key") == "ladybower").row(0, named=True)
    assert (row["name"], row["observed_on"], row["group"]) == (
        "Ladybower",
        date(2026, 10, 5),
        "Severn Trent",
    )
    assert (row["volume_hm3"], row["capacity_hm3"]) == pytest.approx((9.587, 27.869))


def test_sc9_matches_the_published_percentages() -> None:
    obs = parse_storage_page(ST_PAGE, date(2026, 10, 5), SEVERN_TRENT)
    assert obs.height == 14
    ours = obs["volume_hm3"] / obs["capacity_hm3"] * 100
    assert ((ours - obs["pct_full"]).abs() < 0.1).all()


def test_hafren_dyfrdwy_page() -> None:
    obs = parse_storage_page(HD_PAGE, date(2026, 10, 5), HAFREN_DYFRDWY)
    by_key = {r["source_key"]: r for r in obs.to_dicts()}
    assert set(by_key) == {
        "ty-mawr",
        "cae-llwyd",
        "pendinas",
        "llyn-cyfynwy",
        "nant-y-ffrith",
        "pen-y-cae-upper",
        "pen-y-cae-lower",
        "marchwiel",
        "llyn-clywedog",
    }
    assert by_key["llyn-clywedog"]["capacity_hm3"] == pytest.approx(49.936)
    assert by_key["nant-y-ffrith"]["volume_hm3"] == 0.0


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("raw-water-storage-levels-05-october-2026", date(2026, 10, 5)),
        ("raw-water-storage-levels-9-march-2026", date(2026, 3, 9)),
        ("raw-water-storage-levels-01-may-20231", date(2023, 5, 1)),  # sic, on the site
    ],
)
def test_page_dates(slug: str, expected: date) -> None:
    assert page_date(slug) == expected


def _client(listing: str, page: str, pages: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.rstrip("/").endswith("reservoir-levels"):
            return httpx.Response(200, text=listing)
        pages.append(path)
        return httpx.Response(200, text=page)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_reads_the_newest_weekly_page() -> None:
    pages: list[str] = []
    adapter = StoragePagesAdapter(SEVERN_TRENT)
    with _client((FIXTURES / "st-listing.html").read_text(), ST_PAGE, pages) as client:
        obs = adapter.parse(adapter.fetch(client))
    assert pages == ["/about-us/reservoir-levels/raw-water-storage-levels-05-october-2026/"]
    assert obs["observed_on"].unique().to_list() == [date(2026, 10, 5)]


def test_history_walks_every_earlier_page_oldest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pipeline.adapters.uk_severn_trent.time.sleep", lambda _: None)
    pages: list[str] = []
    adapter = StoragePagesAdapter(SEVERN_TRENT)
    with _client((FIXTURES / "st-listing.html").read_text(), ST_PAGE, pages) as client:
        days = [adapter.parse(raw)["observed_on"][0] for raw in adapter.fetch_history(client)]
    assert len(days) == 195  # every page but the newest, which is the live fetch
    assert days == sorted(days)
    assert days[0] == date(2023, 1, 2)


def test_metadata() -> None:
    assert StoragePagesAdapter(SEVERN_TRENT).meta.id == "uk-severn-trent"
    assert StoragePagesAdapter(HAFREN_DYFRDWY).meta.country == "UK"
