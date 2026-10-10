import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA
from pipeline.adapters.bg_moew import MoewAdapter, bulletin_date_from_slug, parse_html, parse_pdf

FIXTURES = Path(__file__).parent / "fixtures" / "bg"


@pytest.fixture(scope="module")
def current() -> pl.DataFrame:
    return parse_html((FIXTURES / "bulletin-2026-10-06.html").read_bytes())


@pytest.fixture(scope="module")
def older() -> pl.DataFrame:
    return parse_pdf((FIXTURES / "bulletin-2022-03-01.pdf").read_bytes())


def test_current_bulletin(current: pl.DataFrame) -> None:
    assert dict(current.schema) == OBSERVATION_SCHEMA
    iskar = current.filter(pl.col("source_key") == "iskar").to_dicts()
    assert iskar == [
        {
            "source_key": "iskar",
            "name": "Искър",
            "group": "БДДР",
            "observed_on": date(2026, 10, 6),
            "volume_hm3": 518.345,
            "capacity_hm3": 655.252,
        }
    ]


def test_reservoirs_without_daily_information_are_skipped(current: pl.DataFrame) -> None:
    assert "kokalyane" not in current["source_key"].to_list()


def test_cascade_subtotals_are_not_counted_as_reservoirs(current: pl.DataFrame) -> None:
    keys = current["source_key"].to_list()
    assert "belmeken" in keys and "chaira" in keys
    assert "belmeken-chaira" not in keys
    assert current.height >= 48


def test_sc2_country_total_matches_the_bulletin_headline(current: pl.DataFrame) -> None:
    """SC2: the bulletin states 4271,5 hm³ available across the significant reservoirs."""
    assert current["volume_hm3"].sum() == pytest.approx(4271.5, abs=1.0)


def test_older_pdf_bulletin(older: pl.DataFrame) -> None:
    assert older["observed_on"].unique().to_list() == [date(2022, 3, 1)]
    row = older.filter(pl.col("source_key") == "asenovets").row(0, named=True)
    assert (row["volume_hm3"], row["capacity_hm3"]) == (20.28, 28.2)
    assert older.height >= 45


def test_bulletin_date_from_page_slug() -> None:
    assert bulletin_date_from_slug(
        "ejedneven-byuletin-za-sustoyanieto-na-vodite-za-06-oktomvri-2026"
    ) == date(2026, 10, 6)
    assert bulletin_date_from_slug(
        "ejedneven-byuletin-za-sustoyanieto-na-vodite-za-1-dekemvri-2023-g"
    ) == date(2023, 12, 1)
    assert bulletin_date_from_slug(
        "ejedneven-byuletin-za-sustoyanieto-na-vodite-za-04-maj-2020"
    ) == date(2020, 5, 4)


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_parse_detects_word_documents() -> None:
    with pytest.raises(ValueError, match="bulletin"):
        MoewAdapter().parse(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 512)


def test_history_skips_truncated_captures_and_carries_the_file_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    monkeypatch.setattr("pipeline.adapters.bg_moew.time.sleep", lambda _: None)
    good = (FIXTURES / "bulletin-2022-03-01.pdf").read_bytes()
    folder = "moew.government.bg/static/media/ups/tiny/Daily%20Bulletin/"
    cdx = [
        ["timestamp", "original"],
        ["20220302000000", f"https://www.{folder}02032022_Bulletin_Daily.pdf"],  # truncated
        ["20220301000000", f"https://www.{folder}01032022_Bulletin_Daily.pdf"],  # same week, ok
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cdx/search/cdx":
            in_old_folder = "Water" not in request.url.params["url"]
            return httpx.Response(200, json=cdx if in_old_folder else [["timestamp", "original"]])
        if "02032022" in str(request.url):
            return httpx.Response(200, content=good[: len(good) // 2])
        return httpx.Response(200, content=good)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batches = list(MoewAdapter().fetch_history(client))
    assert len(batches) == 1
    obs = MoewAdapter().parse(batches[0])
    assert obs["observed_on"].unique().to_list() == [date(2022, 3, 1)]


def test_file_date_is_used_when_the_text_has_none() -> None:
    import base64
    import json

    pdf = (FIXTURES / "bulletin-2022-03-01.pdf").read_bytes()
    envelope = json.dumps({"date": "2022-03-01", "content": base64.b64encode(pdf).decode()})
    obs = MoewAdapter().parse(envelope.encode())
    assert obs["observed_on"].unique().to_list() == [date(2022, 3, 1)]


def test_names_clipped_by_old_pdf_cells_resolve_by_prefix_and_capacity() -> None:
    """Archived PDFs clip long names at the cell edge ('Ивайловград' -> 'ivaylovgra');
    'studen' could be Студена or Студен кладенец, so capacity breaks the tie."""
    from pipeline.adapters.bg_moew import resolve_clipped_names

    obs = pl.DataFrame(
        [
            {
                "source_key": k,
                "name": k,
                "group": "БДИБР",
                "observed_on": date(2022, 3, 1),
                "volume_hm3": 1.0,
                "capacity_hm3": cap,
            }
            for k, cap in [
                ("ivaylovgra", 156.702),
                ("studen", 387.772),
                ("studen", 25.2),
                ("iskar", 655.252),
                ("nowhere", 1.0),
            ]
        ],
        schema=OBSERVATION_SCHEMA,
    )
    resolved = resolve_clipped_names(obs)["source_key"].to_list()
    assert resolved == ["ivaylovgrad", "studen-kladenets", "studena", "iskar", "nowhere"]
