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
