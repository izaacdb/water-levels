import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.contract import (
    SCHEMA_PATH,
    Area,
    CurrentEntry,
    Manifest,
    contract_schema,
)


def test_manifest_serialises_with_camel_case_keys() -> None:
    manifest = Manifest(
        generated_at=datetime(2026, 10, 10, 6, 0, tzinfo=UTC),
        snapshot_week="2026-W41",
        countries=[{"code": "ES", "name": "Spain", "status": "active"}],
        sources=[
            {
                "id": "es-miteco",
                "country": "ES",
                "name": "MITECO",
                "url": "https://www.miteco.gob.es/",
                "last_published": date(2026, 10, 6),
            }
        ],
    )
    data = json.loads(manifest.model_dump_json(by_alias=True, exclude_none=True))
    assert data["snapshotWeek"] == "2026-W41"
    assert data["schemaVersion"] == 1
    assert data["sources"][0]["lastPublished"] == "2026-10-06"


def test_snapshot_week_must_be_iso_week() -> None:
    with pytest.raises(ValidationError):
        Manifest(generated_at=datetime.now(UTC), snapshot_week="2026-41", countries=[], sources=[])


def test_area_level_is_constrained() -> None:
    with pytest.raises(ValidationError):
        Area(id="ES", level="planet", name="Spain", country="ES", capacity_hm3=1, source_id="x")


def test_current_entry_can_carry_a_flagged_value_as_published() -> None:
    """E4: an over-capacity reading is shown as published, with its flag."""
    entry = CurrentEntry(
        pct=101,
        as_of=date(2026, 1, 1),
        stale=False,
        n_reporting=1,
        n_total=1,
        flags=["over_capacity"],
    )
    assert entry.flags == ["over_capacity"]


def test_normal_pct_is_bounded() -> None:
    with pytest.raises(ValidationError):
        CurrentEntry(
            pct=50, normal_pct=101, as_of=date(2026, 1, 1), stale=False, n_reporting=1, n_total=1
        )


def test_committed_schema_matches_models() -> None:
    """The committed schema is what the web app's types are generated from."""
    committed = json.loads(Path(SCHEMA_PATH).read_text())
    assert committed == contract_schema(), "run `uv run pipeline schema` to regenerate"
