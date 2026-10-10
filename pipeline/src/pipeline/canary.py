"""Weekly live check that every source still fetches and parses as expected."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import polars as pl

from pipeline import http
from pipeline.adapters.base import SourceAdapter
from pipeline.registry import attach_reservoir_ids, load_registry

DRIFT = 0.10


def canary(
    adapters: Sequence[SourceAdapter], store: pl.DataFrame, out_dir: Path
) -> dict[str, dict[str, Any]]:
    """Fetch + parse each source live. A source fails if it errors, or if the number of
    reservoirs it reports drops more than DRIFT below its latest week in the archive.
    Raw fetches are saved to ``out_dir`` as candidate test fixtures."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, Any]] = {}
    with http.client() as client:
        for adapter in adapters:
            meta = adapter.meta
            try:
                raw = adapter.fetch(client)
                (out_dir / f"{meta.id}.raw").write_bytes(raw)
                mapped, unknown = attach_reservoir_ids(
                    adapter.parse(raw), load_registry(meta.country)
                )
            except Exception as err:
                results[meta.id] = {"ok": False, "problem": f"{type(err).__name__}: {err}"}
                continue
            mine = store.filter(pl.col("source_id") == meta.id)
            expected = 0
            if mine.height:
                latest = mine["observed_on"].max()
                expected = mine.filter(pl.col("observed_on") == latest)["reservoir_id"].n_unique()
            found = mapped["reservoir_id"].n_unique()
            result: dict[str, Any] = {
                "ok": True,
                "reservoirs": found,
                "expected": expected,
                "unknown_keys": unknown,
            }
            if found == 0 or (expected and found < expected * (1 - DRIFT)):
                result |= {"ok": False, "problem": f"row count drift: {found} vs {expected}"}
            results[meta.id] = result
    return results
