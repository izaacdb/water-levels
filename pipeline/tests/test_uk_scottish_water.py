from datetime import date
from pathlib import Path

import pytest

from pipeline.adapters.base import PCT_FULL
from pipeline.adapters.uk_scottish_water import TOTAL_KEY, ScottishWaterAdapter, parse_levels

PAGE = (Path(__file__).parent / "fixtures" / "uk" / "scottish-water-2026-10-05.html").read_text()


def test_only_the_published_total_is_read() -> None:
    """B25: Scottish Water publishes a total and four areas, never per-reservoir figures."""
    obs = parse_levels(PAGE)
    assert obs.height == 1
    row = obs.row(0, named=True)
    assert (row["source_key"], row["observed_on"], row[PCT_FULL]) == (
        TOTAL_KEY,
        date(2026, 10, 5),
        79.0,
    )
    assert (row["volume_hm3"], row["capacity_hm3"]) == (None, None)


def test_a_changed_page_is_an_error() -> None:
    with pytest.raises(ValueError, match="no total"):
        parse_levels("<table><tr><td>5 October 2026</td></tr></table>")


def test_metadata() -> None:
    meta = ScottishWaterAdapter().meta
    assert (meta.id, meta.country, meta.cadence) == ("uk-scottish-water", "UK", "weekly")
