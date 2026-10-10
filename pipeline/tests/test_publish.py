import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import SourceMeta
from pipeline.contract import Areas, Current, Manifest, Series
from pipeline.publish import Outputs, build_outputs, write_outputs
from pipeline.store import STORE_SCHEMA

META = SourceMeta(id="es-miteco", country="ES", name="MITECO", url="https://www.miteco.gob.es/")
NOW = datetime(2026, 10, 10, 6, tzinfo=UTC)
REGISTRY = pl.DataFrame(
    {
        "id": ["ES-a", "ES-b", "ES-c"],
        "source_key": ["a", "b", "c"],
        "name": ["Alpha", "Beta", "Gamma"],
        "rbd_code": ["ES010", "ES010", "ES020"],
        "lat": ["42.0", "42.2", ""],
        "lon": ["-8.0", "-8.2", ""],
    }
)
RBDS = pl.DataFrame(
    {"code": ["ES010", "ES020"], "country": ["ES", "ES"], "name": ["Miño-Sil", "Duero"]}
)


def _store(rows: list[tuple[str, date, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "reservoir_id": r,
                "observed_on": d,
                "volume_hm3": v,
                "capacity_hm3": c,
                "source_id": "es-miteco",
                "fetched_at": NOW,
            }
            for r, d, v, c in rows
        ],
        schema=STORE_SCHEMA,
    )


@pytest.fixture
def outputs() -> Outputs:
    store = _store(
        [
            ("ES-a", date(2026, 9, 29), 10, 100),
            ("ES-a", date(2026, 10, 6), 30, 100),
            ("ES-b", date(2026, 10, 6), 50, 100),
            ("ES-c", date(2026, 9, 15), 5, 100),
        ]
    )
    return build_outputs(store, {"ES": REGISTRY}, RBDS, [META], now=NOW)


def test_manifest(outputs: Outputs) -> None:
    manifest = outputs.manifest
    assert manifest.snapshot_week == "2026-W41"
    assert [(c.code, c.status) for c in manifest.countries] == [("ES", "active")]
    assert manifest.sources[0].last_published == date(2026, 10, 6)


def test_country_area_and_current(outputs: Outputs) -> None:
    areas, current = outputs.areas, outputs.current
    spain = next(a for a in areas.root if a.id == "ES")
    assert (spain.level, spain.name, spain.capacity_hm3) == ("country", "Spain", 200)
    entry = current.root["ES"]
    assert entry.pct == pytest.approx(40.0)
    assert entry.as_of == date(2026, 10, 6)
    assert (entry.normal_pct, entry.anomaly_pts, entry.normal_years) == (None, None, 0)
    # Gamma is still in the network but missed this week (E1).
    assert (entry.n_reporting, entry.n_total, entry.stale) == (2, 3, False)


def test_region_and_reservoir_areas(outputs: Outputs) -> None:
    areas, current = outputs.areas, outputs.current
    by_id = {a.id: a for a in areas.root}
    region = by_id["ES010"]
    assert (region.level, region.name, region.parent_id, region.country) == (
        "region",
        "Miño-Sil",
        "ES",
        "ES",
    )
    assert region.centroid == pytest.approx([-8.1, 42.1])
    reservoir = by_id["ES-a"]
    assert (reservoir.level, reservoir.name, reservoir.parent_id) == ("reservoir", "Alpha", "ES010")
    assert reservoir.centroid == [-8.0, 42.0]
    assert current.root["ES-a"].pct == pytest.approx(30.0)
    assert (current.root["ES010"].n_reporting, current.root["ES010"].n_total) == (2, 2)
    # Gamma's region has nothing this week, so it shows its last value as stale (B24).
    assert current.root["ES020"].stale is True
    assert current.root["ES020"].as_of == date(2026, 9, 15)


def test_country_goes_stale_when_source_falls_behind() -> None:
    store = _store([("ES-a", date(2026, 9, 1), 30, 100)])
    out = build_outputs(store, {"ES": REGISTRY}, RBDS, [META], now=NOW)
    manifest, current = out.manifest, out.current
    assert current.root["ES"].stale is True
    assert manifest.countries[0].status == "stale"


def test_write_outputs_produces_valid_files(outputs: Outputs, tmp_path: Path) -> None:
    write_outputs(outputs, out_dir=tmp_path)
    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text())
    assert manifest["snapshotWeek"] == "2026-W41"
    Manifest.model_validate(manifest)
    Areas.model_validate_json((tmp_path / "data" / "areas.json").read_text())
    Current.model_validate_json((tmp_path / "data" / "current.json").read_text())
    series = Series.model_validate_json((tmp_path / "data" / "series" / "ES010.json").read_text())
    assert series.area_id == "ES010"


def test_retired_reservoirs_leave_current_views_and_coverage_counts() -> None:
    # ES-c last reported over a year before the snapshot: it has left the network.
    store = _store(
        [
            ("ES-a", date(2026, 10, 6), 30, 100),
            ("ES-b", date(2026, 10, 6), 50, 100),
            ("ES-c", date(2024, 1, 2), 10, 100),
        ]
    )
    out = build_outputs(store, {"ES": REGISTRY}, RBDS, [META], now=NOW)
    areas, current = out.areas, out.current
    assert "ES-c" not in current.root
    assert "ES-c" not in {a.id for a in areas.root}
    assert (current.root["ES"].n_reporting, current.root["ES"].n_total) == (2, 2)


def test_series_is_columnar_and_aligned(outputs: Outputs) -> None:
    series = outputs.series["ES"]
    assert series.weeks == ["2026-W38", "2026-W40", "2026-W41"]
    assert series.pct == [5.0, 10.0, 40.0]  # 2026-W38 is Gamma alone: 5/100
    assert len(series.normal) == len(series.p10) == len(series.p90) == len(series.n) == 3
    assert series.normal == [None, None, None]  # no history yet (E2)
    assert series.n == [1, 1, 2]


def test_series_window_is_ten_years() -> None:
    store = _store(
        [
            ("ES-a", date(2016, 10, 4), 10, 100),  # 2016-W40: just outside the window
            ("ES-a", date(2016, 10, 11), 20, 100),  # 2016-W41: first week inside
            ("ES-a", date(2026, 10, 6), 30, 100),
        ]
    )
    out = build_outputs(store, {"ES": REGISTRY}, RBDS, [META], now=NOW)
    assert out.series["ES-a"].weeks == ["2016-W41", "2026-W41"]
