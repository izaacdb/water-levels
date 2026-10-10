import polars as pl
import pytest

from pipeline.compute.normal import with_normals


def weeks(rows: list[tuple[int, int, float]], area: str = "ES") -> pl.DataFrame:
    """Aggregated weekly rows: (iso_year, iso_week, pct)."""
    return pl.DataFrame(
        {
            "area_id": [area] * len(rows),
            "week": [f"{y}-W{w:02d}" for y, w, _ in rows],
            "pct": [p for _, _, p in rows],
        }
    )


def row(df: pl.DataFrame, week: str) -> dict[str, object]:
    return df.filter(pl.col("week") == week).row(0, named=True)


def test_normal_is_mean_of_same_week_in_previous_years() -> None:
    history = [(2020 + i, 41, 40.0 + i) for i in range(5)]  # 2020..2024: 40..44
    out = with_normals(weeks([*history, (2025, 41, 50.0)]))
    r = row(out, "2025-W41")
    assert r["normal_pct"] == pytest.approx(42.0)
    assert r["normal_years"] == 5
    assert r["anomaly_pts"] == pytest.approx(8.0)


def test_fewer_than_five_years_is_insufficient_history() -> None:
    history = [(2021 + i, 41, 40.0) for i in range(4)]
    r = row(with_normals(weeks([*history, (2025, 41, 50.0)])), "2025-W41")
    assert r["normal_pct"] is None
    assert r["anomaly_pts"] is None
    assert r["normal_years"] == 4


def test_only_the_previous_ten_years_count() -> None:
    history = [(2010, 41, 0.0)] + [(2015 + i, 41, 50.0) for i in range(10)]
    r = row(with_normals(weeks([*history, (2025, 41, 60.0)])), "2025-W41")
    assert r["normal_years"] == 10
    assert r["normal_pct"] == pytest.approx(50.0)  # 2010 is outside 2015..2024


def test_missing_years_reduce_the_count() -> None:
    history = [(y, 41, 50.0) for y in (2015, 2016, 2018, 2020, 2022, 2024)]
    r = row(with_normals(weeks([*history, (2025, 41, 60.0)])), "2025-W41")
    assert r["normal_years"] == 6


def test_week_53_uses_the_week_52_normal() -> None:
    history = [(2015 + i, 52, 30.0) for i in range(5)]
    r = row(with_normals(weeks([*history, (2020, 53, 36.0)])), "2020-W53")
    assert r["normal_pct"] == pytest.approx(30.0)
    assert r["anomaly_pts"] == pytest.approx(6.0)


def test_band_is_10th_to_90th_percentile() -> None:
    history = [(2015 + i, 41, float(10 * i)) for i in range(10)]  # 0..90
    r = row(with_normals(weeks([*history, (2025, 41, 50.0)])), "2025-W41")
    assert r["normal_p10"] == pytest.approx(9.0)
    assert r["normal_p90"] == pytest.approx(81.0)


def test_areas_do_not_mix() -> None:
    a = weeks([(2015 + i, 41, 10.0) for i in range(5)] + [(2020, 41, 10.0)], area="A")
    b = weeks([(2015 + i, 41, 90.0) for i in range(5)] + [(2020, 41, 90.0)], area="B")
    out = with_normals(pl.concat([a, b]))
    assert out.filter(pl.col("area_id") == "A", pl.col("week") == "2020-W41")[
        "normal_pct"
    ].item() == pytest.approx(10.0)
