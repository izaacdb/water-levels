import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA
from pipeline.adapters.cz_povodi import ENTERPRISES, PovodiAdapter, parse_volumes_page

FIXTURES = Path(__file__).parent / "fixtures" / "cz"


def test_volumes_page() -> None:
    obs = parse_volumes_page((FIXTURES / "labe.html").read_text(), "Povodí Labe")
    assert dict(obs.schema) == OBSERVATION_SCHEMA
    row = obs.filter(pl.col("source_key") == "bedrichov").row(0, named=True)
    assert row["observed_on"] == date(2026, 10, 10)
    assert row["volume_hm3"] == pytest.approx(1.51)
    # Capacity is the conservation storage: filled + free.
    assert row["capacity_hm3"] == pytest.approx(1.71)
    assert row["group"] == "Povodí Labe"


def test_reservoirs_without_a_reading_are_skipped_and_vd_prefix_dropped() -> None:
    obs = parse_volumes_page((FIXTURES / "vltava.html").read_text(), "Povodí Vltavy")
    keys = obs["source_key"].to_list()
    assert "bilsko" not in keys  # listed without a measurement
    assert "hnevkovice" in keys
    assert obs.filter(pl.col("source_key") == "hnevkovice")["name"].item() == "Hněvkovice"


def test_adapter_combines_all_five_enterprises() -> None:
    bundle = {e.name: (FIXTURES / f"{e.slug}.html").read_text() for e in ENTERPRISES}
    obs = PovodiAdapter().parse(json.dumps(bundle).encode())
    assert set(obs["group"].unique()) == {e.name for e in ENTERPRISES}
    assert obs["source_key"].is_unique().all()
    assert obs.height > 90


def test_fetch_waits_out_the_portal_wait_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """The portals answer with WaitPage.aspx until their data is ready; retry the page."""
    import httpx

    monkeypatch.setattr("pipeline.adapters.cz_povodi.time.sleep", lambda _: None)
    calls: dict[str, int] = {}
    pages = {e.url: (FIXTURES / f"{e.slug}.html").read_text() for e in ENTERPRISES}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "WaitPage" in url:
            return httpx.Response(200, text="<html>please wait</html>")
        calls[url] = calls.get(url, 0) + 1
        if calls[url] == 1:  # first visit: bounced to the wait page
            return httpx.Response(
                302, headers={"Location": url.rsplit("/", 1)[0] + "/WaitPage.aspx"}
            )
        return httpx.Response(200, text=pages[url])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        obs = PovodiAdapter().parse(PovodiAdapter().fetch(client))
    assert set(obs["group"].unique()) == {e.name for e in ENTERPRISES}
