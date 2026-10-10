"""Command-line entry point: ``pipeline <command>``."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pipeline import health, store
from pipeline.adapters.base import SourceAdapter
from pipeline.adapters.bg_moew import MoewAdapter
from pipeline.adapters.cy_wdd import WddAdapter
from pipeline.adapters.cz_povodi import PovodiAdapter
from pipeline.adapters.el_eydap import EydapAdapter
from pipeline.adapters.es_miteco import MitecoAdapter
from pipeline.adapters.pt_apa import ApaAdapter
from pipeline.adapters.uk_anglian import AnglianAdapter
from pipeline.adapters.uk_scottish_water import ScottishWaterAdapter
from pipeline.adapters.uk_severn_trent import HAFREN_DYFRDWY, SEVERN_TRENT, StoragePagesAdapter
from pipeline.adapters.uk_stream import STREAM_COMPANIES, StreamAdapter
from pipeline.canary import canary
from pipeline.contract import SCHEMA_PATH, contract_schema
from pipeline.run import run

ADAPTERS: list[SourceAdapter] = [
    MitecoAdapter(),
    ApaAdapter(),
    MoewAdapter(),
    WddAdapter(),
    PovodiAdapter(),
    *(StreamAdapter(c) for c in STREAM_COMPANIES),
    StoragePagesAdapter(SEVERN_TRENT),
    StoragePagesAdapter(HAFREN_DYFRDWY),
    AnglianAdapter(),
    ScottishWaterAdapter(),
    EydapAdapter(),
]


def _schema(_: argparse.Namespace) -> None:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(contract_schema(), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {SCHEMA_PATH}")


def _run(args: argparse.Namespace) -> None:
    report = run(ADAPTERS, store_path=args.store, out_dir=args.out, now=datetime.now(UTC))
    for source, keys in report.unknown_keys.items():
        print(f"::warning::{source}: {len(keys)} reservoirs missing from registry: {keys}")


def _canary(args: argparse.Namespace) -> None:
    results = canary(ADAPTERS, store.load(args.store), args.out)
    (args.out / "canary.json").write_text(json.dumps(results, indent=2, default=str) + "\n")
    failing = {k: v for k, v in results.items() if not v["ok"]}
    for source, result in results.items():
        print(f"{'FAIL' if source in failing else 'ok  '} {source}: {result}")
    if failing:
        raise SystemExit(1)


def _alerts(args: argparse.Namespace) -> None:
    failing, healthy = health.alerts(health.load(args.health), threshold=args.threshold)
    print(json.dumps({"failing": failing, "healthy": healthy}))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("schema", help="export the JSON contract schema").set_defaults(func=_schema)
    run_cmd = sub.add_parser("run", help="fetch sources, update the store, publish JSON")
    run_cmd.add_argument("--store", type=Path, default=Path("data-store/observations.parquet"))
    run_cmd.add_argument("--out", type=Path, default=Path("site-data"))
    run_cmd.set_defaults(func=_run)
    canary_cmd = sub.add_parser("canary", help="live-check every source without storing")
    canary_cmd.add_argument("--store", type=Path, default=Path("data-store/observations.parquet"))
    canary_cmd.add_argument("--out", type=Path, default=Path("canary-out"))
    canary_cmd.set_defaults(func=_canary)
    alerts_cmd = sub.add_parser("alerts", help="sources failing repeatedly, as JSON")
    alerts_cmd.add_argument("--health", type=Path, default=Path("data-store/source-health.json"))
    alerts_cmd.add_argument("--threshold", type=int, default=3)
    alerts_cmd.set_defaults(func=_alerts)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parser.parse_args(argv)
    args.func(args)
