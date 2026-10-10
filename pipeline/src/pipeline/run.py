"""One pipeline run: fetch every source, merge into the store, publish."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import polars as pl

from pipeline import store
from pipeline.adapters.base import SourceAdapter
from pipeline.publish import build_outputs, write_outputs
from pipeline.registry import attach_reservoir_ids, load_rbds, load_registry

log = logging.getLogger(__name__)
USER_AGENT = "water-levels/0.1 (+https://github.com/izaacdb/water-levels)"


@dataclass
class RunReport:
    unknown_keys: dict[str, list[str]] = field(default_factory=dict)


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
    fresh: list[pl.DataFrame] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for adapter in adapters:
            meta = adapter.meta
            parsed: list[tuple[pl.DataFrame, datetime]] = []
            fetch_history = getattr(adapter, "fetch_history", None)
            if meta.id not in known_sources and fetch_history is not None:
                # First run for a source with an archive: backfill its history once.
                # Archived rows count as fetched just before the live one, so live wins.
                for raw in fetch_history(client):
                    try:
                        parsed.append((adapter.parse(raw), now - timedelta(microseconds=1)))
                    except Exception as err:  # one bad archived edition mustn't stop the rest
                        log.warning("%s: skipping unparseable archived edition: %s", meta.id, err)
            parsed.append((adapter.parse(adapter.fetch(client)), now))
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

    merged = store.merge(existing, pl.concat(fresh))
    store.save(merged, store_path)
    outputs = build_outputs(merged, registries, load_rbds(), [a.meta for a in adapters], now=now)
    write_outputs(outputs, out_dir=out_dir)
    return report
