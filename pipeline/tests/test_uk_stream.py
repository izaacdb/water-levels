import json
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from pipeline.adapters.base import OBSERVATION_SCHEMA, PCT_FULL
from pipeline.adapters.uk_stream import YORKSHIRE, StreamAdapter, display_name, parse_rows

FIXTURES = Path(__file__).parent / "fixtures" / "uk"
SEARCH = json.loads((FIXTURES / "stream-search-yorkshire.json").read_text())
LATEST = json.loads((FIXTURES / "yorkshire-2026-latest.json").read_text())


def _rows() -> list[dict[str, object]]:
    return [f["attributes"] for f in LATEST["features"]]


def test_parses_observations_with_volume_from_the_published_storage() -> None:
    obs = parse_rows(_rows(), "Yorkshire Water")
    assert {k: obs.schema[k] for k in OBSERVATION_SCHEMA} == OBSERVATION_SCHEMA
    row = obs.filter(
        (pl.col("source_key") == "scar-house") & (pl.col("observed_on") == date(2026, 10, 5))
    ).row(0, named=True)
    assert (row["name"], row["group"]) == ("Scar House", "Yorkshire Water")
    # TCM (thousand m³) -> hm³.
    assert row["volume_hm3"] == pytest.approx(3.36863)
    assert row["capacity_hm3"] == pytest.approx(9.41396)
    assert row[PCT_FULL] == pytest.approx(35.78)


def test_sc9_percentages_match_the_published_ones() -> None:
    obs = parse_rows(_rows(), "Yorkshire Water")
    ours = obs["volume_hm3"] / obs["capacity_hm3"] * 100
    assert ((ours - obs[PCT_FULL]).abs() < 0.5).all()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SCAR HOUSE IRE", "Scar House"),
        ("THORNTON STWD ESR", "Thornton Stwd"),
        ("Bough Beech Reservoir", "Bough Beech"),
    ],
)
def test_display_names(raw: str, expected: str) -> None:
    assert display_name(raw) == expected


def _row(name: str, day: object, capacity: object, level: object, pct: object, **kw: object):  # type: ignore[no-untyped-def]
    cap_units, level_units = kw.pop("units", ("Ml", "Ml"))  # type: ignore[misc]
    return {
        "RESERVOIR_NAME": name,
        kw.pop("date_field", "DATE"): day,
        "CAPACITY": capacity,
        "CAPACITY_UNITS": cap_units,
        "CURRENT_LEVEL": level,
        "CURRENT_LEVEL_UNITS": level_units,
        "CURRENT_PERCENTAGE": pct,
    }


def test_units_dates_and_percent_only_rows() -> None:
    rows = [
        # SES: capacity in m³, level is a height in feet, date as epoch ms.
        _row("Bough Beech Reservoir", 1780189200000, 10_000_000, 210.2, 89.7, units=("M3", "ft")),
        # Southern: % only, ISO date string.
        _row("Darwell", "2023-07-27", None, None, "54.61", units=("ML", "ML")),
        # Northumbrian: Ml and a dd/mm/yyyy date.
        _row("Abberton", "05/01/2025", 41375, 31285, 75.61),
        # Wessex: DATE_ISO instead of DATE, level is a height.
        _row(
            "Sutton Bingham",
            "2026-08-03",
            2133.84,
            -2.1,
            58.14,
            units=("Ml", "m"),
            date_field="DATE_ISO",
        ),
    ]
    obs = {r["source_key"]: r for r in parse_rows(rows, "X").to_dicts()}
    bough = obs["bough-beech"]
    assert bough["observed_on"] == date(2026, 5, 31)
    assert bough["capacity_hm3"] == pytest.approx(10.0)
    assert bough["volume_hm3"] == pytest.approx(8.97)  # from %, as the level is a height
    darwell = obs["darwell"]
    assert (darwell["volume_hm3"], darwell["capacity_hm3"], darwell[PCT_FULL]) == (
        None,
        None,
        54.61,
    )
    assert obs["abberton"]["observed_on"] == date(2025, 1, 5)
    assert obs["abberton"]["volume_hm3"] == pytest.approx(31.285)
    assert obs["sutton-bingham"]["observed_on"] == date(2026, 8, 3)


def _transport(datasets: dict[str, list[dict[str, object]]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/search/v1/collections/all/items"):
            return httpx.Response(200, json=SEARCH)
        title = next(
            t for t in datasets if t.replace(" ", "%20") in str(request.url.raw_path, "ascii")
        )
        rows = datasets[title]
        offset = int(request.url.params.get("resultOffset", 0))
        page = rows[offset : offset + 2]
        more = offset + 2 < len(rows)
        return httpx.Response(
            200, json={"features": [{"attributes": a} for a in page], "exceededTransferLimit": more}
        )

    return httpx.MockTransport(handler)


def test_fetch_reads_the_latest_dataset_across_pages() -> None:
    rows = _rows()[:5]
    datasets = {f"Yorkshire Water Reservoir Levels {y}": [] for y in (2022, 2023, 2024, 2025)}
    datasets["Yorkshire Water Reservoir Levels 2026"] = rows
    with httpx.Client(transport=_transport(datasets)) as client:
        obs = StreamAdapter(YORKSHIRE).parse(StreamAdapter(YORKSHIRE).fetch(client))
    assert obs.height == 5


def test_history_yields_every_earlier_yearly_dataset_oldest_first() -> None:
    datasets = {
        f"Yorkshire Water Reservoir Levels {y}": [{**_rows()[0], "DATE": f"{y}-03-01"}]
        for y in (2022, 2023, 2024, 2025, 2026)
    }
    with httpx.Client(transport=_transport(datasets)) as client:
        adapter = StreamAdapter(YORKSHIRE)
        years = [adapter.parse(raw)["observed_on"][0].year for raw in adapter.fetch_history(client)]
    assert years == [2022, 2023, 2024, 2025]  # 2026 is the live fetch


def test_metadata() -> None:
    meta = StreamAdapter(YORKSHIRE).meta
    assert (meta.id, meta.country, meta.cadence) == ("uk-yorkshire", "UK", "weekly")
