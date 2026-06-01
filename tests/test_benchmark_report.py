from __future__ import annotations

import pytest

from homebase.workspace import benchmark_report as benchmark_report


def test_metric_map_and_total_avg() -> None:
    run = {
        "metrics": [
            {"name": "collect_projects", "avg_s": 1.0},
            {"name": "collect_archived", "avg_s": 2.0},
        ],
        "score_metric_profile": ["collect_projects", "collect_archived"],
    }
    mm = benchmark_report.metric_map(run)
    assert mm["collect_projects"] == 1.0
    assert benchmark_report.total_avg(run) == 3.0


def test_perf_score_monotonic() -> None:
    fast = benchmark_report.perf_score(
        10.0,
        score_ref_seconds=30.0,
        score_ref_day_value=1.0,
    )
    slow = benchmark_report.perf_score(
        100.0,
        score_ref_seconds=30.0,
        score_ref_day_value=1.0,
    )
    assert fast is not None and slow is not None
    assert fast > slow


def test_composite_score_weighted_average() -> None:
    assert benchmark_report.composite_score(
        100.0, 50.0, warm_weight=0.7, cold_weight=0.3
    ) == 85.0


def test_composite_score_falls_back_to_available() -> None:
    assert benchmark_report.composite_score(
        100.0, None, warm_weight=0.7, cold_weight=0.3
    ) == 100.0
    assert benchmark_report.composite_score(
        None, 50.0, warm_weight=0.7, cold_weight=0.3
    ) == 50.0
    assert benchmark_report.composite_score(
        None, None, warm_weight=0.7, cold_weight=0.3
    ) is None


def test_score_runs_uses_composite() -> None:
    runs: list[dict[str, object]] = [
        {
            "elapsed_s": 10.0,
            "warm_elapsed_s": 10.0,
            "cold_elapsed_s": 20.0,
            "metrics": [],
            "score_metric_profile": [],
        }
    ]
    [scored] = benchmark_report.score_runs(
        runs,
        ignore_featuresets=None,
        score_ref_seconds=30.0,
        score_ref_day_value=1.0,
        warm_weight=0.7,
        cold_weight=0.3,
    )
    warm = benchmark_report.perf_score(
        10.0, score_ref_seconds=30.0, score_ref_day_value=1.0
    )
    cold = benchmark_report.perf_score(
        20.0, score_ref_seconds=30.0, score_ref_day_value=1.0
    )
    assert warm is not None and cold is not None
    assert scored["score"] == pytest.approx(0.7 * warm + 0.3 * cold)
