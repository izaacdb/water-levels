from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from pipeline.registry import attach_reservoir_ids, load_registry
from pipeline.store import STORE_SCHEMA, load, merge, save


def _obs(**overrides: object) -> pl.DataFrame:
    row = {
        "source_key": "albarellos",
        "name": "Albarellos",
        "group": "Miño - Sil",
        "observed_on": date(2026, 10, 6),
        "volume_hm3": 22.0,
        "capacity_hm3": 91.0,
    }
    row.update(overrides)
    return pl.DataFrame([row])


def test_spain_registry_has_unique_ids_and_keys() -> None:
    reg = load_registry("ES")
    assert reg.height >= 400
    assert reg["id"].is_unique().all()
    assert reg["source_key"].is_unique().all()
    assert reg["id"].str.starts_with("ES-").all()


def test_attach_ids_maps_known_and_reports_unknown() -> None:
    reg = pl.DataFrame({"id": ["ES-albarellos"], "source_key": ["albarellos"]})
    obs = pl.concat([_obs(), _obs(source_key="nuevo", name="Nuevo")])
    mapped, unknown = attach_reservoir_ids(obs, reg)
    assert mapped["reservoir_id"].to_list() == ["ES-albarellos"]
    assert unknown == ["nuevo"]


def _stored(volume: float, fetched: datetime, day: date = date(2026, 10, 6)) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "reservoir_id": "ES-albarellos",
                "observed_on": day,
                "volume_hm3": volume,
                "capacity_hm3": 91.0,
                "source_id": "es-miteco",
                "fetched_at": fetched,
            }
        ],
        schema=STORE_SCHEMA,
    )


def test_merge_dedupes_keeping_latest_fetch() -> None:
    old = _stored(20.0, datetime(2026, 10, 7, tzinfo=UTC))
    new = _stored(22.0, datetime(2026, 10, 8, tzinfo=UTC))
    merged = merge(old, new)
    assert merged.height == 1
    assert merged["volume_hm3"].item() == 22.0


def test_merge_keeps_distinct_dates() -> None:
    a = _stored(20.0, datetime(2026, 10, 7, tzinfo=UTC), date(2026, 9, 29))
    b = _stored(22.0, datetime(2026, 10, 7, tzinfo=UTC), date(2026, 10, 6))
    assert merge(a, b).height == 2


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "observations.parquet"
    assert load(path).height == 0  # missing store is empty, not an error
    df = _stored(22.0, datetime(2026, 10, 8, tzinfo=UTC))
    save(df, path)
    assert load(path).equals(df)
