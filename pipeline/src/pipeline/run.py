"""One pipeline run: fetch every source, merge into the store, publish."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
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
    fresh: list[pl.DataFrame] = []
    with httpx.Client(headers={"User-Agent": USER_AGENT}) as client:
        for adapter in adapters:
            meta = adapter.meta
            obs = adapter.parse(adapter.fetch(client))
            mapped, unknown = attach_reservoir_ids(obs, registries[meta.country])
            if unknown:
                log.warning(
                    "%s: %d source keys not in registry: %s", meta.id, len(unknown), unknown
                )
                report.unknown_keys[meta.id] = unknown
            fresh.append(
                mapped.select(
                    "reservoir_id",
                    "observed_on",
                    "volume_hm3",
                    "capacity_hm3",
                    source_id=pl.lit(meta.id),
                    fetched_at=pl.lit(now),
                ).cast(store.STORE_SCHEMA)  # type: ignore[arg-type]
            )

    merged = store.merge(store.load(store_path), pl.concat(fresh))
    store.save(merged, store_path)
    outputs = build_outputs(merged, registries, load_rbds(), [a.meta for a in adapters], now=now)
    write_outputs(outputs, out_dir=out_dir)
    return report
