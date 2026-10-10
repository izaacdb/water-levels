import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta
from pipeline.run import run

NOW = datetime(2026, 10, 10, 6, tzinfo=UTC)


class FakeAdapter:
    meta = SourceMeta(id="es-miteco", country="ES", name="MITECO", url="https://example.org/")

    def fetch(self, client: httpx.Client) -> bytes:
        return b"raw"

    def parse(self, raw: bytes) -> pl.DataFrame:
        assert raw == b"raw"
        return pl.DataFrame(
            [
                {
                    "source_key": "albarellos",
                    "name": "Albarellos",
                    "group": "Miño - Sil",
                    "observed_on": date(2026, 10, 6),
                    "volume_hm3": 22.0,
                    "capacity_hm3": 91.0,
                },
                {
                    "source_key": "not-in-registry",
                    "name": "Nuevo",
                    "group": "Tajo",
                    "observed_on": date(2026, 10, 6),
                    "volume_hm3": 1.0,
                    "capacity_hm3": 2.0,
                },
            ],
            schema=OBSERVATION_SCHEMA,
        )


def test_run_merges_into_store_and_publishes(tmp_path: Path) -> None:
    store_path = tmp_path / "store" / "observations.parquet"
    report = run([FakeAdapter()], store_path=store_path, out_dir=tmp_path / "site", now=NOW)

    stored = pl.read_parquet(store_path)
    assert stored["reservoir_id"].to_list() == ["ES-albarellos"]
    assert report.unknown_keys == {"es-miteco": ["not-in-registry"]}

    current = json.loads((tmp_path / "site" / "data" / "current.json").read_text())
    assert current["ES"]["pct"] == 24.2  # 22 / 91


class ArchivedAdapter(FakeAdapter):
    """A source with an archive: history is fetched once, when the store has none."""

    history_calls = 0

    def fetch_history(self, client: httpx.Client) -> list[bytes]:
        ArchivedAdapter.history_calls += 1
        return [b"old"]

    def parse(self, raw: bytes) -> pl.DataFrame:
        day = date(2026, 9, 29) if raw == b"old" else date(2026, 10, 6)
        return pl.DataFrame(
            [
                {
                    "source_key": "albarellos",
                    "name": "Albarellos",
                    "group": "Miño - Sil",
                    "observed_on": day,
                    "volume_hm3": 20.0,
                    "capacity_hm3": 91.0,
                }
            ],
            schema=OBSERVATION_SCHEMA,
        )


def test_history_is_backfilled_only_when_the_source_is_new(tmp_path: Path) -> None:
    store_path = tmp_path / "observations.parquet"
    run([ArchivedAdapter()], store_path=store_path, out_dir=tmp_path / "site", now=NOW)
    assert sorted(pl.read_parquet(store_path)["observed_on"].to_list()) == [
        date(2026, 9, 29),
        date(2026, 10, 6),
    ]
    run([ArchivedAdapter()], store_path=store_path, out_dir=tmp_path / "site", now=NOW)
    assert ArchivedAdapter.history_calls == 1
