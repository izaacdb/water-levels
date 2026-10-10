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


def test_attach_ids_is_scoped_to_the_source_when_a_country_has_several() -> None:
    """D6: two companies may use the same key; each maps only to its own reservoirs."""
    reg = pl.DataFrame(
        {
            "id": ["UK-kielder", "UK-other-kielder"],
            "source_id": ["uk-northumbrian", "uk-yorkshire"],
            "source_key": ["kielder", "kielder"],
        }
    )
    mapped, unknown = attach_reservoir_ids(_obs(source_key="kielder"), reg, "uk-yorkshire")
    assert mapped["reservoir_id"].to_list() == ["UK-other-kielder"]
    assert unknown == []


def test_attach_completes_volume_and_capacity_from_the_registry() -> None:
    """D7: %-only and volume-only sources are completed with the registry's capacity."""
    reg = pl.DataFrame(
        {
            "id": ["UK-a", "DE-b", "XX-c"],
            "source_key": ["a", "b", "c"],
            "capacity_hm3": ["10", "4", ""],
        }
    )
    obs = pl.concat(
        [
            _obs(source_key="a", volume_hm3=None, capacity_hm3=None, pct_full=50.0),
            _obs(source_key="b", volume_hm3=3.0, capacity_hm3=None),
            _obs(source_key="c", volume_hm3=None, capacity_hm3=None, pct_full=10.0),
        ],
        how="diagonal_relaxed",
    )
    mapped, _ = attach_reservoir_ids(obs, reg)
    rows = {r["reservoir_id"]: (r["volume_hm3"], r["capacity_hm3"]) for r in mapped.to_dicts()}
    assert rows == {"UK-a": (5.0, 10.0), "DE-b": (3.0, 4.0)}  # XX-c can't be completed


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
