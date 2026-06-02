from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


def test_metric_groups_and_featuresets_consistent() -> None:
    groups = benchmark_report.metric_groups()
    assert "core" in groups
    fs = benchmark_report.metric_featuresets()
    for group, metrics in groups.items():
        for m in metrics:
            assert fs[m] == group


def test_default_score_metric_profile_skips_errors_and_blank() -> None:
    metrics: list[dict[str, object]] = [
        {"name": "collect_projects", "avg_s": 1.0},
        {"name": "  ", "avg_s": 1.0},
        {"name": "with_error", "avg_s": 1.0, "error": "boom"},
        {"name": "good", "avg_s": 2.0},
        "not-a-dict",
    ]
    profile = benchmark_report.default_score_metric_profile(metrics)
    assert profile == ["collect_projects", "good"]


def test_metric_map_rejects_invalid_entries() -> None:
    run = {
        "metrics": [
            {"name": "a", "avg_s": 1.0},
            {"name": "b", "avg_s": "not-a-number"},
            {"name": "c", "avg_s": -0.5},
            {"name": "", "avg_s": 1.0},
            "string-entry",
        ],
    }
    mm = benchmark_report.metric_map(run)
    assert mm == {"a": 1.0}


def test_metric_map_rejects_non_list_metrics() -> None:
    assert benchmark_report.metric_map({"metrics": {"a": 1.0}}) == {}


def test_group_totals_sums_only_groups_with_data() -> None:
    run = {
        "metrics": [
            {"name": "collect_projects", "avg_s": 1.0},
            {"name": "collect_archived", "avg_s": 2.0},
            {"name": "git_info_small", "avg_s": 4.0},
        ],
    }
    totals = benchmark_report.group_totals(run)
    assert totals["core"] == pytest.approx(3.0)
    assert totals["git"] == pytest.approx(4.0)
    assert "cache_mutation" not in totals


def test_total_avg_returns_none_when_profile_missing_metric() -> None:
    run = {
        "metrics": [{"name": "collect_projects", "avg_s": 1.0}],
        "score_metric_profile": ["collect_projects", "collect_archived"],
    }
    assert benchmark_report.total_avg(run) is None


def test_total_avg_falls_back_to_legacy_score_groups() -> None:
    run = {
        "metrics": [
            {"name": "collect_projects", "avg_s": 1.0},
            {"name": "collect_archived", "avg_s": 2.0},
            {"name": "cache_store_rows", "avg_s": 1.0},
            {"name": "cache_load_rows", "avg_s": 1.0},
            {"name": "query_plain_scan", "avg_s": 1.0},
            {"name": "query_expr_scan", "avg_s": 1.0},
        ],
        "score_metric_profile": "not-a-list",
    }
    # 6 distinct metrics — total_avg sums them via the present-metrics branch
    assert benchmark_report.total_avg(run) == pytest.approx(7.0)


def test_total_avg_returns_none_for_run_with_no_metrics() -> None:
    assert benchmark_report.total_avg({"metrics": []}) is None


def test_perf_score_edge_cases() -> None:
    assert benchmark_report.perf_score(
        None, score_ref_seconds=30.0, score_ref_day_value=1.0
    ) is None
    assert benchmark_report.perf_score(
        float("inf"), score_ref_seconds=30.0, score_ref_day_value=1.0
    ) == 0.0
    assert benchmark_report.perf_score(
        0.0, score_ref_seconds=30.0, score_ref_day_value=1.0
    ) is None


def test_fmt_helpers_format_values() -> None:
    assert benchmark_report.fmt_bench_value(None) == "-"
    assert benchmark_report.fmt_bench_value(1.2345) == "1.2345s"
    assert benchmark_report.fmt_score(None) == "-"
    assert benchmark_report.fmt_score(1500.0) == "1500"
    assert benchmark_report.fmt_score(150.0) == "150.0"
    assert benchmark_report.fmt_score(1.5) == "1.50"
    assert benchmark_report.fmt_bench_delta(None) == "-"
    assert benchmark_report.fmt_bench_delta(2.5) == "+2.50%"
    assert benchmark_report.fmt_bench_delta(-3.5) == "-3.50%"
    assert benchmark_report.short_ts("") == "-"
    assert benchmark_report.short_ts("2026-06-01T12:34:56+00:00") == "2026-06-01T12:34:56"


def test_load_runs_handles_missing_and_malformed(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    assert benchmark_report.load_runs(missing) == []

    broken = tmp_path / "broken.yaml"
    broken.write_text(":\n  not yaml: [")
    assert benchmark_report.load_runs(broken) == []

    not_mapping = tmp_path / "list.yaml"
    not_mapping.write_text(yaml.safe_dump([1, 2, 3]))
    assert benchmark_report.load_runs(not_mapping) == []

    runs_not_list = tmp_path / "wrong_shape.yaml"
    runs_not_list.write_text(yaml.safe_dump({"runs": {"a": 1}}))
    assert benchmark_report.load_runs(runs_not_list) == []

    good = tmp_path / "good.yaml"
    good.write_text(
        yaml.safe_dump(
            {"runs": [{"label": "r1"}, "skip-me", {"label": "r2"}]}
        )
    )
    runs = benchmark_report.load_runs(good)
    assert [r["label"] for r in runs] == ["r1", "r2"]


def test_run_filtered_metric_totals_and_counts() -> None:
    run = {
        "metrics": [
            {"name": "collect_projects", "avg_s": 1.0},  # core
            {"name": "git_info_small", "avg_s": 2.0},  # git
            {"name": "tags_write_420", "avg_s": 3.0},  # tags
            {"name": "custom_metric", "avg_s": 4.0},  # mapped via per-run map
        ],
        "metric_featuresets": {"custom_metric": "custom"},
    }
    total = benchmark_report.run_filtered_metric_total(run, {"git", "tags"})
    assert total == pytest.approx(1.0 + 4.0)
    total_no_filter = benchmark_report.run_filtered_metric_total(run, set())
    assert total_no_filter is None

    counts = benchmark_report.run_filtered_metric_counts(run, {"git"})
    assert counts == (4, 3)
    assert benchmark_report.run_filtered_metric_counts({"metrics": []}, {"git"}) == (0, 0)


def test_run_filtered_metric_total_returns_none_when_no_metrics() -> None:
    assert benchmark_report.run_filtered_metric_total({"metrics": []}, {"git"}) is None


def test_score_runs_with_ignore_featuresets() -> None:
    runs: list[dict[str, object]] = [
        {
            "metrics": [
                {"name": "collect_projects", "avg_s": 1.0},
                {"name": "git_info_small", "avg_s": 5.0},
            ],
            "cold_elapsed_s": 5.0,
        }
    ]
    [scored] = benchmark_report.score_runs(
        runs,
        ignore_featuresets={"git"},
        score_ref_seconds=30.0,
        score_ref_day_value=1.0,
        warm_weight=0.7,
        cold_weight=0.3,
    )
    # filtered total is collect_projects only (1.0) → that becomes the warm elapsed
    assert scored["score"] is not None and scored["score"] > 0
    assert scored["filtered_total_s"] == pytest.approx(1.0)


def test_score_runs_delta_prev_and_best_pct() -> None:
    runs: list[dict[str, object]] = [
        {"warm_elapsed_s": 100.0, "cold_elapsed_s": 200.0, "metrics": []},
        {"warm_elapsed_s": 50.0, "cold_elapsed_s": 100.0, "metrics": []},
        {"warm_elapsed_s": 200.0, "cold_elapsed_s": 400.0, "metrics": []},
    ]
    # warm/cold need to be set as elapsed_s for non-ignored path
    for r in runs:
        r["elapsed_s"] = r["warm_elapsed_s"]
    scored = benchmark_report.score_runs(
        runs,
        ignore_featuresets=None,
        score_ref_seconds=30.0,
        score_ref_day_value=1.0,
        warm_weight=0.7,
        cold_weight=0.3,
    )
    assert scored[0]["delta_prev_pct"] is None
    # Second run is faster -> score increased
    assert scored[1]["delta_prev_pct"] is not None and scored[1]["delta_prev_pct"] > 0
    # All best_pct values should be ≤ 100
    for s in scored:
        assert s["score_best_pct"] is not None
        assert s["score_best_pct"] <= 100.0 + 1e-9


def test_available_featuresets_collects_custom_values() -> None:
    runs: list[dict[str, object]] = [
        {"metric_featuresets": {"a": "extra"}},
        {"metric_featuresets": {"b": "core"}},
        {"metric_featuresets": "not-a-dict"},
    ]
    fs = benchmark_report.available_featuresets(runs)
    assert "extra" in fs
    assert "core" in fs


def test_results_compat_warnings_summarises_missing_fields() -> None:
    runs: list[dict[str, object]] = [
        {"score_metric_profile": ["a"]},
        {"score_warm": 1.0, "score_cold": 1.0, "warm_elapsed_s": 1.0,
         "cold_elapsed_s": 1.0, "score_metric_profile": ["a"]},
        {"cold_suite_elapsed_s": 1.0, "score_metric_profile": []},
    ]
    lines = benchmark_report.results_compat_warnings(runs)
    joined = "\n".join(lines)
    assert "score_warm" in joined
    assert "profile" in joined


def test_results_compat_warnings_no_runs_returns_empty() -> None:
    assert benchmark_report.results_compat_warnings([]) == []

