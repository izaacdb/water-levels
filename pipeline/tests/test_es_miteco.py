import shutil
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA
from pipeline.adapters.es_miteco import MitecoAdapter, parse_csv

FIXTURE = Path(__file__).parent / "fixtures" / "es" / "bd-embalses-sample.csv"


@pytest.fixture
def parsed() -> pl.DataFrame:
    return parse_csv(FIXTURE.read_text())


def test_output_matches_observation_schema(parsed: pl.DataFrame) -> None:
    assert dict(parsed.schema) == OBSERVATION_SCHEMA


def test_golden_rows(parsed: pl.DataFrame) -> None:
    row = parsed.filter(
        (pl.col("source_key") == "albarellos") & (pl.col("observed_on") == date(2026, 10, 6))
    ).to_dicts()
    assert row == [
        {
            "source_key": "albarellos",
            "name": "Albarellos",
            "group": "Miño - Sil",
            "observed_on": date(2026, 10, 6),
            "volume_hm3": 22.0,
            "capacity_hm3": 91.0,
        }
    ]


def test_source_key_is_ascii_slug(parsed: pl.DataFrame) -> None:
    assert "guistolas" in parsed["source_key"].to_list()


def test_drops_empty_and_zero_capacity_rows(parsed: pl.DataFrame) -> None:
    pajares_dates = parsed.filter(pl.col("source_key") == "pajares")["observed_on"].to_list()
    assert pajares_dates  # its non-empty weeks survive
    assert date(2003, 5, 13) not in pajares_dates
    assert date(2003, 5, 27) not in pajares_dates
    assert "cenza" not in parsed["source_key"].to_list()
    assert parsed["capacity_hm3"].min() > 0  # type: ignore[operator]


def test_keeps_over_capacity_rows_for_downstream_flagging(parsed: pl.DataFrame) -> None:
    over = parsed.filter(pl.col("volume_hm3") > pl.col("capacity_hm3"))
    assert over.height > 0


def test_adapter_metadata() -> None:
    meta = MitecoAdapter().meta
    assert (meta.id, meta.country) == ("es-miteco", "ES")
    assert meta.url.startswith("https://www.miteco.gob.es/")


@pytest.mark.skipif(shutil.which("mdb-export") is None, reason="mdbtools not installed")
def test_extract_csv_from_zip_round_trips(tmp_path: Path) -> None:
    """Build a zip containing a non-mdb file to prove we surface a clear error."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no database here")
    with pytest.raises(ValueError, match=r"\.mdb"):
        MitecoAdapter().parse(buf.getvalue())
