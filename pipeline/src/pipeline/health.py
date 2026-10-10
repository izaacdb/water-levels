"""Per-source health, kept beside the observation archive across runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class SourceHealth:
    last_success: str | None = None  # ISO timestamp of the last successful fetch
    last_error: str | None = None  # error from the most recent run, if it failed
    consecutive_failures: int = 0


def health_path(store_path: Path) -> Path:
    return store_path.parent / "source-health.json"


def load(path: Path) -> dict[str, SourceHealth]:
    if not path.exists():
        return {}
    return {k: SourceHealth(**v) for k, v in json.loads(path.read_text()).items()}


def save(health: dict[str, SourceHealth], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: asdict(v) for k, v in sorted(health.items())}, indent=2) + "\n")


def record(
    health: dict[str, SourceHealth], source_id: str, now: datetime, error: str | None
) -> None:
    h = health.setdefault(source_id, SourceHealth())
    if error is None:
        h.last_success, h.last_error, h.consecutive_failures = now.isoformat(), None, 0
    else:
        h.last_error, h.consecutive_failures = error, h.consecutive_failures + 1


def alerts(health: dict[str, SourceHealth], threshold: int = 3) -> tuple[dict[str, str], list[str]]:
    """Sources failing for `threshold`+ runs in a row (to raise), and healthy ones (to close)."""
    failing = {
        sid: h.last_error or "unknown error"
        for sid, h in sorted(health.items())
        if h.consecutive_failures >= threshold
    }
    healthy = [sid for sid, h in sorted(health.items()) if h.consecutive_failures == 0]
    return failing, healthy
