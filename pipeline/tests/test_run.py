import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl

from pipeline.adapters.base import OBSERVATION_SCHEMA, PartialFetch, SourceMeta
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


class BrokenAdapter(FakeAdapter):
    meta = SourceMeta(id="pt-apa", country="PT", name="APA", url="https://example.org/pt")

    def fetch(self, client: httpx.Client) -> bytes:
        raise httpx.ConnectError("source down")


def test_one_failing_source_does_not_break_the_others(tmp_path: Path) -> None:
    """E5: the failure is recorded, the healthy source still publishes."""
    store_path = tmp_path / "observations.parquet"
    report = run(
        [FakeAdapter(), BrokenAdapter()], store_path=store_path, out_dir=tmp_path / "site", now=NOW
    )
    assert "source down" in report.errors["pt-apa"]
    manifest = json.loads((tmp_path / "site" / "data" / "manifest.json").read_text())
    sources = {s["id"]: s for s in manifest["sources"]}
    assert "source down" in sources["pt-apa"]["lastError"]
    assert "lastError" not in sources["es-miteco"]
    assert json.loads((tmp_path / "site" / "data" / "current.json").read_text())["ES"]


def test_health_tracks_consecutive_failures_across_runs(tmp_path: Path) -> None:
    store_path = tmp_path / "observations.parquet"
    for _ in range(3):
        run(
            [FakeAdapter(), BrokenAdapter()], store_path=store_path, out_dir=tmp_path / "s", now=NOW
        )
    health = json.loads((tmp_path / "source-health.json").read_text())
    assert health["pt-apa"]["consecutive_failures"] == 3
    assert health["es-miteco"]["consecutive_failures"] == 0
    assert health["es-miteco"]["last_success"].startswith("2026-10-10")
    # Recovery resets the count.
    run([FakeAdapter()], store_path=store_path, out_dir=tmp_path / "s", now=NOW)
    health = json.loads((tmp_path / "source-health.json").read_text())
    assert health["pt-apa"]["consecutive_failures"] == 3  # untouched: not run
    assert health["es-miteco"]["consecutive_failures"] == 0


class ArchiveButLiveDown(ArchivedAdapter):
    def fetch(self, client: httpx.Client) -> bytes:
        raise httpx.ConnectError("live site down")


def test_backfilled_history_is_kept_when_the_live_fetch_fails(tmp_path: Path) -> None:
    store_path = tmp_path / "observations.parquet"
    report = run([ArchiveButLiveDown()], store_path=store_path, out_dir=tmp_path / "s", now=NOW)
    assert "live site down" in report.errors["es-miteco"]
    assert pl.read_parquet(store_path)["observed_on"].to_list() == [date(2026, 9, 29)]


class PartlyReachable(FakeAdapter):
    def fetch(self, client: httpx.Client) -> bytes:
        raise PartialFetch(b"raw", RuntimeError("one portal down"))


def test_a_partial_fetch_publishes_what_arrived_and_counts_as_a_failure(tmp_path: Path) -> None:
    store_path = tmp_path / "observations.parquet"
    report = run([PartlyReachable()], store_path=store_path, out_dir=tmp_path / "s", now=NOW)
    assert "one portal down" in report.errors["es-miteco"]
    assert pl.read_parquet(store_path)["reservoir_id"].to_list() == ["ES-albarellos"]
    health = json.loads((tmp_path / "source-health.json").read_text())
    assert health["es-miteco"]["consecutive_failures"] == 1


class FutureDated(FakeAdapter):
    def parse(self, raw: bytes) -> pl.DataFrame:
        rows = super().parse(raw)  # albarellos on 6 Oct, plus an unknown key
        return pl.concat([rows, rows.head(1).with_columns(observed_on=pl.lit(date(2026, 12, 3)))])


def test_readings_dated_in_the_future_are_dropped(tmp_path: Path) -> None:
    """Some feeds swap day and month ('2026-12-03' for 12 March); never store a future date."""
    store_path = tmp_path / "observations.parquet"
    run([FutureDated()], store_path=store_path, out_dir=tmp_path / "s", now=NOW)
    assert pl.read_parquet(store_path)["observed_on"].to_list() == [date(2026, 10, 6)]
