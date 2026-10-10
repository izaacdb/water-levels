"""Published static JSON contract.

These models are the single source of truth for the files the web app reads.
JSON Schema is exported from them (``pipeline schema``) and the web app
generates its TypeScript types from that schema.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel
from pydantic.alias_generators import to_camel

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "contract.schema.json"

IsoWeek = Annotated[str, Field(pattern=r"^\d{4}-W\d{2}$")]
Pct = Annotated[float, Field(ge=0, le=100)]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class CountryStatus(_Model):
    code: str
    name: str
    status: Literal["active", "stale", "withdrawn"]
    note: str | None = None


class SourceInfo(_Model):
    id: str
    country: str
    name: str
    url: str
    last_fetched: datetime | None = None
    last_published: date | None = None
    last_error: str | None = None


class Manifest(_Model):
    schema_version: int = SCHEMA_VERSION
    generated_at: datetime
    snapshot_week: IsoWeek
    countries: list[CountryStatus]
    sources: list[SourceInfo]


class Area(_Model):
    id: str
    level: Literal["country", "region", "reservoir"]
    name: str
    country: str
    parent_id: str | None = None
    capacity_hm3: float
    source_id: str
    centroid: Annotated[list[float], Field(min_length=2, max_length=2)] | None = None


class Areas(RootModel[list[Area]]):
    pass


class CurrentEntry(_Model):
    pct: Pct
    anomaly_pts: float | None = None
    normal_pct: Pct | None = None
    normal_years: int = 0
    as_of: date
    stale: bool
    n_reporting: int
    n_total: int
    flags: list[str] = Field(default_factory=list)


class Current(RootModel[dict[str, CurrentEntry]]):
    pass


def contract_schema() -> dict[str, Any]:
    """Combined JSON Schema for every published file, keyed by file."""
    defs: dict[str, Any] = {}
    files: dict[str, Any] = {}
    for name, model in (("Manifest", Manifest), ("Areas", Areas), ("Current", Current)):
        schema = model.model_json_schema(
            by_alias=True, ref_template="#/$defs/{model}", mode="serialization"
        )
        defs.update(schema.pop("$defs", {}))
        defs[name] = schema
        files[name] = {"$ref": f"#/$defs/{name}"}
    _strip_property_titles(defs)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Contract",
        "type": "object",
        "properties": files,
        "$defs": dict(sorted(defs.items())),
    }


def _strip_property_titles(node: Any) -> None:
    """Drop per-property titles so generated TS types use plain field types, not aliases."""
    if isinstance(node, dict):
        for prop in node.get("properties", {}).values():
            prop.pop("title", None)
        for value in node.values():
            _strip_property_titles(value)
    elif isinstance(node, list):
        for item in node:
            _strip_property_titles(item)
