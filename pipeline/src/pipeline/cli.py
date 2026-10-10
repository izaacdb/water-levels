"""Command-line entry point: ``pipeline <command>``."""

from __future__ import annotations

import argparse
import json

from pipeline.contract import SCHEMA_PATH, contract_schema


def _schema(_: argparse.Namespace) -> None:
    SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_PATH.write_text(json.dumps(contract_schema(), indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {SCHEMA_PATH}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(required=True)
    sub.add_parser("schema", help="export the JSON contract schema").set_defaults(func=_schema)
    args = parser.parse_args(argv)
    args.func(args)
