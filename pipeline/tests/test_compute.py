from datetime import UTC, date, datetime

import polars as pl
import pytest
from hypothesis import given
from hypothesis import strategies as st

from pipeline.compute.aggregate import aggregate
from pipeline.compute.stale import is_stale, snapshot_week
from pipeline.compute.weekly import iso_week_label, weekly_snapshot
from pipeline.store import STORE_SCHEMA

FETCHED = datetime(2026, 10, 8, tzinfo=UTC)


def store(rows: list[tuple[str, date, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "reservoir_id": r,
                "observed_on": d,
                "volume_hm3": v,
                "capacity_hm3": c,
                "source_id": "es-miteco",
                "fetched_at": FETCHED,
            }
            for r, d, v, c in rows
        ],
        schema=STORE_SCHEMA,
    )


def test_iso_week_label_handles_year_boundaries() -> None:
    assert iso_week_label(date(2026, 10, 6)) == "2026-W41"
    assert iso_week_label(date(2021, 1, 1)) == "2020-W53"


def test_weekly_snapshot_takes_latest_value_in_week() -> None:
    # Monday and Thursday of the same ISO week: Thursday wins (B3).
    df = store([("A", date(2026, 10, 5), 10, 100), ("A", date(2026, 10, 8), 12, 100)])
    weekly = weekly_snapshot(df)
    assert weekly.height == 1
    assert weekly.row(0, named=True)["volume_hm3"] == 12
    assert weekly.row(0, named=True)["week"] == "2026-W41"


def membership() -> pl.DataFrame:
    return pl.DataFrame({"reservoir_id": ["A", "B", "C"], "area_id": ["ES", "ES", "ES"]})


def test_aggregate_is_sum_of_volumes_over_sum_of_capacities() -> None:
    # A: 10/300 = 3.3%, B: 90/100 = 90%. Mean of pcts is ~46.7%; sum-over-sum is 100/400.
    weekly = weekly_snapshot(
        store([("A", date(2026, 10, 6), 10, 300), ("B", date(2026, 10, 6), 90, 100)])
    )
    out = aggregate(weekly, membership()).row(0, named=True)
    assert out["pct"] == pytest.approx(25.0)
    assert out["n_reporting"] == 2
    assert out["n_total"] == 3  # C is a member but did not report (E1)


def test_aggregate_excludes_implausible_values() -> None:
    weekly = weekly_snapshot(
        store([("A", date(2026, 10, 6), 50, 100), ("B", date(2026, 10, 6), 150, 100)])
    )
    out = aggregate(weekly, membership()).row(0, named=True)
    assert out["pct"] == pytest.approx(50.0)
    assert out["n_reporting"] == 1


def test_aggregate_as_of_is_latest_contributing_date() -> None:
    weekly = weekly_snapshot(
        store([("A", date(2026, 10, 5), 50, 100), ("B", date(2026, 10, 6), 50, 100)])
    )
    assert aggregate(weekly, membership()).row(0, named=True)["as_of"] == date(2026, 10, 6)


@given(
    st.lists(
        st.tuples(st.floats(0, 1000), st.floats(1, 1000)).filter(lambda vc: vc[0] <= vc[1]),
        min_size=1,
        max_size=8,
    ),
    st.randoms(),
)
def test_aggregate_bounds_and_order_invariance(
    pairs: list[tuple[float, float]], rnd: object
) -> None:
    rows = [(f"R{i}", date(2026, 10, 6), v, c) for i, (v, c) in enumerate(pairs)]
    members = pl.DataFrame({"reservoir_id": [r[0] for r in rows], "area_id": ["ES"] * len(rows)})
    shuffled = rows[:]
    rnd.shuffle(shuffled)  # type: ignore[attr-defined]
    a = aggregate(weekly_snapshot(store(rows)), members)["pct"].item()
    b = aggregate(weekly_snapshot(store(shuffled)), members)["pct"].item()
    assert 0 <= a <= 100
    assert a == pytest.approx(b)


def test_snapshot_week_is_latest_published_week_not_beyond_today() -> None:
    latest = [date(2026, 10, 6), date(2026, 9, 29)]
    assert snapshot_week(latest, today=date(2026, 10, 10)) == "2026-W41"
    # A future-dated value never pushes the snapshot past the current week.
    assert snapshot_week([date(2026, 12, 1)], today=date(2026, 10, 10)) == "2026-W41"


@pytest.mark.parametrize(
    ("as_of", "expected"),
    [
        (date(2026, 10, 6), False),  # published in the snapshot week
        (date(2026, 9, 29), True),  # missed the snapshot week (B24)
    ],
)
def test_is_stale(as_of: date, expected: bool) -> None:
    assert is_stale(as_of, "2026-W41", today=date(2026, 10, 10)) is expected


def test_is_stale_when_whole_snapshot_is_old() -> None:
    # Even the snapshot week itself is stale if nothing has been published for 14+ days.
    assert is_stale(date(2026, 9, 1), "2026-W36", today=date(2026, 10, 10)) is True


def test_implausible_value_is_shown_as_published_on_its_own_reservoir() -> None:
    """E4: the reservoir's own area keeps the published value, flagged; aggregates skip it."""
    weekly = weekly_snapshot(
        store([("A", date(2026, 10, 6), 50, 100), ("B", date(2026, 10, 6), 150, 100)])
    )
    members = pl.DataFrame(
        {
            "reservoir_id": ["A", "B", "A", "B"],
            "area_id": ["ES", "ES", "A", "B"],
        }
    )
    out = {r["area_id"]: r for r in aggregate(weekly, members).iter_rows(named=True)}
    assert out["B"]["pct"] == pytest.approx(150.0)
    assert out["B"]["flag"] == "over_capacity"
    assert out["A"]["flag"] is None
    assert out["ES"]["pct"] == pytest.approx(50.0)
    assert out["ES"]["flag"] is None
