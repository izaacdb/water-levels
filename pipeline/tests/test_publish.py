import json
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest

from pipeline.adapters.base import SourceMeta
from pipeline.contract import Areas, Current, Manifest
from pipeline.publish import build_outputs, write_outputs
from pipeline.store import STORE_SCHEMA

META = SourceMeta(id="es-miteco", country="ES", name="MITECO", url="https://www.miteco.gob.es/")
NOW = datetime(2026, 10, 10, 6, tzinfo=UTC)
REGISTRY = pl.DataFrame({"id": ["ES-a", "ES-b"], "source_key": ["a", "b"]})


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
def outputs() -> tuple[Manifest, Areas, Current]:
    store = _store(
        [
            ("ES-a", date(2026, 9, 29), 10, 100),
            ("ES-a", date(2026, 10, 6), 30, 100),
            ("ES-b", date(2026, 10, 6), 50, 100),
        ]
    )
    return build_outputs(store, {"ES": REGISTRY}, [META], now=NOW)


def test_manifest(outputs: tuple[Manifest, Areas, Current]) -> None:
    manifest, _, _ = outputs
    assert manifest.snapshot_week == "2026-W41"
    assert [(c.code, c.status) for c in manifest.countries] == [("ES", "active")]
    assert manifest.sources[0].last_published == date(2026, 10, 6)


def test_country_area_and_current(outputs: tuple[Manifest, Areas, Current]) -> None:
    _, areas, current = outputs
    spain = next(a for a in areas.root if a.id == "ES")
    assert (spain.level, spain.name, spain.capacity_hm3) == ("country", "Spain", 200)
    entry = current.root["ES"]
    assert entry.pct == pytest.approx(40.0)
    assert entry.as_of == date(2026, 10, 6)
    assert (entry.n_reporting, entry.n_total, entry.stale) == (2, 2, False)


def test_country_goes_stale_when_source_falls_behind() -> None:
    store = _store([("ES-a", date(2026, 9, 1), 30, 100)])
    manifest, _, current = build_outputs(store, {"ES": REGISTRY}, [META], now=NOW)
    assert current.root["ES"].stale is True
    assert manifest.countries[0].status == "stale"


def test_write_outputs_produces_valid_files(
    outputs: tuple[Manifest, Areas, Current], tmp_path: Path
) -> None:
    write_outputs(*outputs, out_dir=tmp_path)
    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text())
    assert manifest["snapshotWeek"] == "2026-W41"
    Manifest.model_validate(manifest)
    Areas.model_validate_json((tmp_path / "data" / "areas.json").read_text())
    Current.model_validate_json((tmp_path / "data" / "current.json").read_text())
