"""One pipeline run: fetch every source, merge into the store, publish."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import polars as pl

from pipeline import health as health_store
from pipeline import http, store
from pipeline.adapters.base import SourceAdapter
from pipeline.publish import build_outputs, write_outputs
from pipeline.registry import attach_reservoir_ids, load_rbds, load_registry, load_withdrawn

log = logging.getLogger(__name__)


class PartialFailure(Exception):
    """The live fetch failed, but archived history was collected and should be kept."""

    def __init__(self, parsed: list[tuple[pl.DataFrame, datetime]], cause: Exception) -> None:
        super().__init__(f"{type(cause).__name__}: {cause}")
        self.parsed = parsed


@dataclass
class RunReport:
    unknown_keys: dict[str, list[str]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


def run(
    adapters: Sequence[SourceAdapter],
    store_path: Path,
    out_dir: Path,
    now: datetime,
) -> RunReport:
    report = RunReport()
    registries = {a.meta.country: load_registry(a.meta.country) for a in adapters}
    existing = store.load(store_path)
    known_sources = set(existing["source_id"].unique().to_list())
    health_file = health_store.health_path(store_path)
    health = health_store.load(health_file)
    fresh: list[pl.DataFrame] = []
    with http.client() as client:
        for adapter in adapters:
            meta = adapter.meta
            try:
                parsed = _collect(adapter, client, known_sources, now)
            except PartialFailure as err:
                parsed = err.parsed
                report.errors[meta.id] = str(err)
                health_store.record(health, meta.id, now, str(err))
                log.error("%s: live update failed, kept archived history: %s", meta.id, err)
            except Exception as err:  # E5: one broken source must not take the others down
                message = f"{type(err).__name__}: {err}"
                log.error("%s: update failed, keeping previous data: %s", meta.id, message)
                report.errors[meta.id] = message
                health_store.record(health, meta.id, now, message)
                continue
            else:
                health_store.record(health, meta.id, now, None)
            for obs, fetched_at in parsed:
                mapped, unknown = attach_reservoir_ids(obs, registries[meta.country])
                if unknown:
                    log.warning("%s: %d keys not in registry: %s", meta.id, len(unknown), unknown)
                    report.unknown_keys.setdefault(meta.id, [])
                    report.unknown_keys[meta.id] = sorted(
                        set(report.unknown_keys[meta.id]) | set(unknown)
                    )
                fresh.append(
                    mapped.select(
                        "reservoir_id",
                        "observed_on",
                        "volume_hm3",
                        "capacity_hm3",
                        source_id=pl.lit(meta.id),
                        fetched_at=pl.lit(fetched_at),
                    ).cast(store.STORE_SCHEMA)  # type: ignore[arg-type]
                )

    merged = store.merge(existing, pl.concat(fresh)) if fresh else existing
    store.save(merged, store_path)
    health_store.save(health, health_file)
    outputs = build_outputs(
        merged,
        registries,
        load_rbds(),
        [a.meta for a in adapters],
        now=now,
        health=health,
        withdrawn=load_withdrawn(),
    )
    write_outputs(outputs, out_dir=out_dir)
    return report


def _collect(
    adapter: SourceAdapter, client: httpx.Client, known_sources: set[str], now: datetime
) -> list[tuple[pl.DataFrame, datetime]]:
    """This run's observations from one source: its archive on first sight, then the live data."""
    meta = adapter.meta
    parsed: list[tuple[pl.DataFrame, datetime]] = []
    fetch_history = getattr(adapter, "fetch_history", None)
    if meta.id not in known_sources and fetch_history is not None:
        # First run for a source with an archive: backfill its history once.
        # Archived rows count as fetched just before the live one, so live wins.
        try:
            for raw in fetch_history(client):
                try:
                    parsed.append((adapter.parse(raw), now - timedelta(microseconds=1)))
                except Exception as err:  # one bad edition mustn't stop the rest
                    log.warning("%s: skipping unparseable archived edition: %s", meta.id, err)
        except httpx.HTTPError as err:
            # Keep whatever history arrived; the live fetch below still runs.
            log.warning("%s: history backfill interrupted: %s", meta.id, err)
    try:
        parsed.append((adapter.parse(adapter.fetch(client)), now))
    except Exception as err:
        if parsed:
            raise PartialFailure(parsed, err) from err
        raise
    return parsed
