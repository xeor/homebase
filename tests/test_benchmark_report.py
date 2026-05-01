from __future__ import annotations

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
