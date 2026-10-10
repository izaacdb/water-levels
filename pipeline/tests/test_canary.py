from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, SourceMeta
from pipeline.canary import canary
from pipeline.store import STORE_SCHEMA

NOW = datetime(2026, 10, 10, 6, tzinfo=UTC)
META = SourceMeta(id="es-miteco", country="ES", name="MITECO", url="https://example.org/")


def obs(keys: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "source_key": k,
                "name": k,
                "group": "g",
                "observed_on": date(2026, 10, 6),
                "volume_hm3": 1.0,
                "capacity_hm3": 2.0,
            }
            for k in keys
        ],
        schema=OBSERVATION_SCHEMA,
    )


class Adapter:
    meta = META

    def __init__(self, keys: list[str] | None = None, fail: bool = False) -> None:
        self.keys, self.fail = keys or [], fail

    def fetch(self, client: httpx.Client) -> bytes:
        if self.fail:
            raise httpx.ConnectError("down")
        return b"raw-bytes"

    def parse(self, raw: bytes) -> pl.DataFrame:
        return obs(self.keys)


def store_with(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "reservoir_id": f"ES-{k}",
                "observed_on": date(2026, 9, 29),
                "volume_hm3": 1.0,
                "capacity_hm3": 2.0,
                "source_id": "es-miteco",
                "fetched_at": NOW,
            }
            for k in ["albarellos", "acena", "aguilar"][:n]
        ],
        schema=STORE_SCHEMA,
    )


def test_healthy_source_passes_and_saves_the_raw_fetch(tmp_path: Path) -> None:
    result = canary([Adapter(["albarellos", "acena", "aguilar"])], store_with(3), tmp_path)
    assert result["es-miteco"]["ok"] is True
    assert (tmp_path / "es-miteco.raw").read_bytes() == b"raw-bytes"


def test_row_count_drift_over_ten_percent_fails(tmp_path: Path) -> None:
    result = canary([Adapter(["albarellos", "acena"])], store_with(3), tmp_path)
    assert result["es-miteco"]["ok"] is False
    assert "drift" in result["es-miteco"]["problem"]


def test_fetch_or_parse_errors_fail(tmp_path: Path) -> None:
    result = canary([Adapter(fail=True)], store_with(3), tmp_path)
    assert result["es-miteco"]["ok"] is False
    assert "down" in result["es-miteco"]["problem"]
