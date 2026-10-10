import json
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA, PartialFetch
from pipeline.adapters.cz_povodi import (
    ENTERPRISES,
    PovodiAdapter,
    _fetch_page,
    parse_volumes_page,
)

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


WAIT_PAGE = """<form name="aspnetForm" method="post" action="./WaitPage.aspx?id=abc&amp;z=p">
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="v1" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="e1" />
</form>"""


def _delta(*parts: tuple[str, str, str]) -> str:
    """An ASP.NET AJAX partial-postback response: length|type|id|content| repeated."""
    return "".join(f"{len(content)}|{kind}|{id_}|{content}|" for kind, id_, content in parts)


def test_fetch_polls_the_wait_page_like_a_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wait page's timer posts back until the server answers with a redirect."""
    import httpx

    monkeypatch.setattr("pipeline.adapters.cz_povodi.time.sleep", lambda _: None)
    labe = ENTERPRISES[0]
    posts: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST":
            form = dict(httpx.QueryParams(request.content.decode()))
            posts.append(form)
            if len(posts) < 3:  # still preparing: the timer keeps running
                return httpx.Response(200, text=_delta(("hiddenField", "__VIEWSTATE", "v2")))
            return httpx.Response(
                200, text=_delta(("pageRedirect", "", "%2fportal%2fnadrze%2fcz%2fObjemy.aspx"))
            )
        if "WaitPage" in url:
            return httpx.Response(200, text=WAIT_PAGE)
        if not posts:
            return httpx.Response(302, headers={"Location": "/portal/nadrze/cz/pc/WaitPage.aspx"})
        return httpx.Response(200, text=(FIXTURES / "labe.html").read_text())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        page = _fetch_page(client, labe.url)
    assert "Bedřichov" in page
    assert posts[0]["__EVENTTARGET"] == "ctl00$ObsahCPH$RefreshTimer"
    assert posts[0]["__VIEWSTATE"] == "v1"
    assert posts[1]["__VIEWSTATE"] == "v2"  # state carried forward from the last delta


def test_one_unreachable_portal_keeps_the_other_four(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr("pipeline.adapters.cz_povodi.time.sleep", lambda _: None)
    pages = {e.url: (FIXTURES / f"{e.slug}.html").read_text() for e in ENTERPRISES}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.pla.cz":
            return httpx.Response(503)
        return httpx.Response(200, text=pages[str(request.url)])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with client, pytest.raises(PartialFetch) as caught:
        PovodiAdapter().fetch(client)
    assert "Povodí Labe" in str(caught.value)
    obs = PovodiAdapter().parse(caught.value.raw)
    assert set(obs["group"].unique()) == {e.name for e in ENTERPRISES[1:]}


def test_all_portals_unreachable_is_a_plain_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr("pipeline.adapters.cz_povodi.time.sleep", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    with client, pytest.raises(httpx.HTTPStatusError):
        PovodiAdapter().fetch(client)
