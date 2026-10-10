from datetime import date
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA
from pipeline.adapters.pt_apa import ApaAdapter, archived_captures, parse_bulletin

FIXTURES = Path(__file__).parent / "fixtures" / "pt"
CURRENT = FIXTURES / "semanal-2026-10-06-tables.pdf"
OLD = FIXTURES / "semanal-2020-02-21.pdf"


@pytest.fixture(scope="module")
def current() -> tuple[pl.DataFrame, pl.DataFrame]:
    return parse_bulletin(CURRENT.read_bytes())


def test_matches_observation_schema(current: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    obs, _ = current
    assert dict(obs.schema) == OBSERVATION_SCHEMA


def test_golden_row(current: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    obs, _ = current
    row = obs.filter(pl.col("source_key") == "alto-lindoso").to_dicts()
    assert row == [
        {
            "source_key": "alto-lindoso",
            "name": "Alto Lindoso",
            "group": "LIMA",
            "observed_on": date(2026, 10, 6),
            "volume_hm3": 133.0,
            "capacity_hm3": 379.0,
        }
    ]


def test_basin_carries_down_and_reservoirs_listed_twice_are_kept_once(
    current: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    obs, _ = current
    assert obs.filter(pl.col("source_key") == "touvedo")["group"].item() == "LIMA"
    beliche = obs.filter(pl.col("source_key") == "beliche")
    assert beliche.height == 1
    assert beliche["group"].item() == "GUADIANA"


def test_reservoirs_without_a_reading_are_skipped(
    current: tuple[pl.DataFrame, pl.DataFrame],
) -> None:
    obs, _ = current
    assert "povoa" not in obs["source_key"].to_list()
    assert obs.height > 70


def test_sc2_percentages_match_the_bulletin(current: tuple[pl.DataFrame, pl.DataFrame]) -> None:
    """SC2: our % full for every reservoir matches APA's own published whole-number %.

    APA truncates rather than rounds (Fagilde: 1 940 / 3 841 dam³ = 50.5% is printed
    as 50%), so "within rounding" means under one point.
    """
    obs, published = current
    joined = obs.join(published, on="source_key")
    assert joined.height == obs.height
    ours = joined["volume_hm3"] / joined["capacity_hm3"] * 100
    assert ((ours - joined["published_pct"]).abs() < 1).all()


def test_older_layout_is_parsed_too() -> None:
    obs, _ = parse_bulletin(OLD.read_bytes())
    assert obs["observed_on"].unique().to_list() == [date(2020, 2, 21)]
    row = obs.filter(pl.col("source_key") == "alto-lindoso").row(0, named=True)
    assert (row["name"], row["volume_hm3"], row["capacity_hm3"]) == ("Alto Lindoso", 223.0, 390.0)
    assert obs.filter(pl.col("source_key") == "rabagao").height == 0  # keyed as alto-rabagao
    assert obs.filter(pl.col("source_key") == "alto-rabagao").height == 1


def test_archived_captures_parses_the_cdx_index() -> None:
    cdx = [["timestamp", "original"], ["20240305210633", "https://x/Semanal.pdf"]]
    assert archived_captures(cdx) == [
        "https://web.archive.org/web/20240305210633id_/https://x/Semanal.pdf"
    ]


def test_adapter_metadata() -> None:
    meta = ApaAdapter().meta
    assert (meta.id, meta.country) == ("pt-apa", "PT")
