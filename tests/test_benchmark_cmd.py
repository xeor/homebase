from __future__ import annotations

from pathlib import Path

import yaml

from homebase.core.constants import (
    BENCHMARK_REPORT_FILE_NAME,
    BENCHMARK_SUITE_VERSION,
    HOMEBASE_DIR_NAME,
)
from homebase.workspace.benchmark import (
    _best_score,
    _delta_pct,
    _filter_current_suite_runs,
    _fmt_optional_float,
    _trend_bar,
    _validate_featuresets,
    cmd_benchmark,
    cmd_benchmark_results,
)


def _write_report(base_dir: Path, runs: list[dict]) -> Path:
    hb = base_dir / HOMEBASE_DIR_NAME
    hb.mkdir(parents=True, exist_ok=True)
    path = hb / BENCHMARK_REPORT_FILE_NAME
    payload = {
        "version": 1,
        "last_run": runs[-1].get("timestamp", "") if runs else "",
        "runs": runs,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return path


def _make_run(
    *,
    ts: str,
    warm_elapsed: float,
    cold_elapsed: float,
    suite_version: int = BENCHMARK_SUITE_VERSION,
    comment: str = "",
    extra_metrics: list[dict] | None = None,
    featuresets: dict[str, str] | None = None,
    git_repo: bool = False,
) -> dict:
    metrics = [
        {"name": "collect_projects", "avg_s": 0.10, "min_s": 0.09, "max_s": 0.11},
        {"name": "collect_archived", "avg_s": 0.05, "min_s": 0.04, "max_s": 0.06},
    ]
    if extra_metrics:
        metrics.extend(extra_metrics)
    fs_map: dict[str, str] = {
        "collect_projects": "core",
        "collect_archived": "core",
    }
    if featuresets:
        fs_map.update(featuresets)
    run = {
        "suite_version": suite_version,
        "timestamp": ts,
        "comment": comment,
        "elapsed_s": warm_elapsed,
        "warm_elapsed_s": warm_elapsed,
        "cold_elapsed_s": cold_elapsed,
        "metrics": metrics,
        "metric_featuresets": fs_map,
        "score_metric_profile": ["collect_projects", "collect_archived"],
    }
    if git_repo:
        run["git_context"] = {
            "repo": True,
            "branch": "main",
            "head": "abcdef1234567890",
            "dirty": False,
        }
    return run


def test_cmd_benchmark_results_no_report_returns_1(tmp_path: Path, capsys) -> None:
    rc = cmd_benchmark_results(tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "no benchmark runs found" in out


def test_cmd_benchmark_results_no_current_suite_runs_returns_1(
    tmp_path: Path, capsys
) -> None:
    _write_report(
        tmp_path,
        [_make_run(ts="2026-06-01T10:00:00", warm_elapsed=1.0, cold_elapsed=2.0, suite_version=BENCHMARK_SUITE_VERSION - 1)],
    )
    rc = cmd_benchmark_results(tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert f"suite_version={BENCHMARK_SUITE_VERSION}" in out


def test_cmd_benchmark_results_renders_table_and_trend(
    tmp_path: Path, capsys
) -> None:
    runs = [
        _make_run(ts="2026-06-01T10:00:00", warm_elapsed=2.0, cold_elapsed=4.0, comment="r1"),
        _make_run(ts="2026-06-02T10:00:00", warm_elapsed=1.5, cold_elapsed=3.0, comment="r2", git_repo=True),
        _make_run(ts="2026-06-03T10:00:00", warm_elapsed=1.0, cold_elapsed=2.0, comment="r3"),
    ]
    report = _write_report(tmp_path, runs)
    rc = cmd_benchmark_results(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert f"benchmark report: {report}" in out
    assert "runs: 3" in out
    assert "warm_sc" in out and "cold_sc" in out
    assert "latest basis:" in out
    assert "latest run metrics" in out
    assert "trend (warm + cold" in out
    assert "compare basis: elapsed wall-clock" in out


def test_cmd_benchmark_results_skipped_count_reported(
    tmp_path: Path, capsys
) -> None:
    runs = [
        _make_run(
            ts="2026-05-30T10:00:00",
            warm_elapsed=2.0,
            cold_elapsed=4.0,
            suite_version=BENCHMARK_SUITE_VERSION - 1,
        ),
        _make_run(ts="2026-06-01T10:00:00", warm_elapsed=1.5, cold_elapsed=3.0),
    ]
    _write_report(tmp_path, runs)
    rc = cmd_benchmark_results(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "skipped old-suite runs: 1" in out


def test_cmd_benchmark_results_invalid_featureset_returns_1(
    tmp_path: Path, capsys
) -> None:
    _write_report(
        tmp_path,
        [_make_run(ts="2026-06-01T10:00:00", warm_elapsed=1.0, cold_elapsed=2.0)],
    )
    rc = cmd_benchmark_results(tmp_path, ignore_featuresets={"nope"})
    assert rc == 1
    err = capsys.readouterr().err
    assert "invalid featureset(s): nope" in err


def test_cmd_benchmark_results_filtered_basis_lists_kept_count(
    tmp_path: Path, capsys
) -> None:
    runs = [
        _make_run(
            ts="2026-06-01T10:00:00",
            warm_elapsed=1.0,
            cold_elapsed=2.0,
            extra_metrics=[
                {"name": "git_info_small", "avg_s": 0.20, "min_s": 0.19, "max_s": 0.21}
            ],
            featuresets={"git_info_small": "git"},
        ),
        _make_run(
            ts="2026-06-02T10:00:00",
            warm_elapsed=0.9,
            cold_elapsed=1.8,
            extra_metrics=[
                {"name": "git_info_small", "avg_s": 0.18, "min_s": 0.17, "max_s": 0.19}
            ],
            featuresets={"git_info_small": "git"},
        ),
    ]
    _write_report(tmp_path, runs)
    rc = cmd_benchmark_results(tmp_path, ignore_featuresets={"git"})
    assert rc == 0
    out = capsys.readouterr().out
    assert "compare basis: filtered metrics" in out
    assert "filtered profile metrics: kept=" in out


def test_cmd_benchmark_results_all_metrics_filtered_returns_1(
    tmp_path: Path, capsys
) -> None:
    run = {
        "suite_version": BENCHMARK_SUITE_VERSION,
        "timestamp": "2026-06-01T10:00:00",
        "comment": "",
        "elapsed_s": 0.2,
        "warm_elapsed_s": 0.2,
        "cold_elapsed_s": 0.4,
        "metrics": [
            {"name": "git_info_small", "avg_s": 0.20, "min_s": 0.19, "max_s": 0.21}
        ],
        "metric_featuresets": {"git_info_small": "git"},
        "score_metric_profile": ["git_info_small"],
    }
    _write_report(tmp_path, [run])
    rc = cmd_benchmark_results(tmp_path, ignore_featuresets={"git"})
    assert rc == 1
    err = capsys.readouterr().err
    assert "ignore-featureset removed all score metrics" in err


def test_cmd_benchmark_dispatches_to_results(tmp_path: Path) -> None:
    _write_report(
        tmp_path,
        [_make_run(ts="2026-06-01T10:00:00", warm_elapsed=1.0, cold_elapsed=2.0)],
    )
    assert cmd_benchmark(tmp_path, tmp_path, "results") == 0


def test_cmd_benchmark_unknown_subcommand_returns_1(
    tmp_path: Path, capsys
) -> None:
    rc = cmd_benchmark(tmp_path, tmp_path, "nope")
    assert rc == 1
    assert "unknown benchmark subcommand" in capsys.readouterr().err


def test_filter_current_suite_runs_counts_skipped() -> None:
    runs = [
        {"suite_version": BENCHMARK_SUITE_VERSION - 1},
        {"suite_version": BENCHMARK_SUITE_VERSION},
        {"suite_version": BENCHMARK_SUITE_VERSION},
    ]
    kept, skipped = _filter_current_suite_runs(runs)
    assert len(kept) == 2
    assert skipped == 1


def test_filter_current_suite_runs_treats_missing_as_current() -> None:
    kept, skipped = _filter_current_suite_runs([{}, {"suite_version": BENCHMARK_SUITE_VERSION}])
    assert len(kept) == 2
    assert skipped == 0


def test_validate_featuresets_returns_zero_when_all_valid() -> None:
    runs = [
        _make_run(
            ts="t",
            warm_elapsed=1.0,
            cold_elapsed=2.0,
            extra_metrics=[
                {"name": "git_info_small", "avg_s": 0.1, "min_s": 0.1, "max_s": 0.1}
            ],
            featuresets={"git_info_small": "git"},
        )
    ]
    available, err = _validate_featuresets(runs, {"git"})
    assert err == 0
    assert "git" in available


def test_fmt_optional_float_passthrough_and_none() -> None:
    assert _fmt_optional_float(1.5) == 1.5
    assert _fmt_optional_float(2) == 2.0
    assert _fmt_optional_float(None) is None
    assert _fmt_optional_float("x") is None


def test_delta_pct_returns_none_when_prev_invalid() -> None:
    assert _delta_pct(1.0, 0.0) is None
    assert _delta_pct(1.0, None) is None
    assert _delta_pct(None, 1.0) is None
    assert _delta_pct(8.0, 10.0) == 20.0


def test_best_score_picks_max_and_handles_missing() -> None:
    assert _best_score([{"score": 1.0}, {"score": 3.0}, {"score": 2.0}], "score") == 3.0
    assert _best_score([{"score": "nan"}, {}], "score") == 0.0


def test_trend_bar_scales_with_relative_value() -> None:
    full = _trend_bar(10.0, 10.0, "#", bar_w=10)
    empty = _trend_bar(0.0, 10.0, "#", bar_w=10)
    half = _trend_bar(5.0, 10.0, "#", bar_w=10)
    assert full == "#" * 10
    assert empty == "." * 10
    assert half.count("#") == 5
    # value>0 but best<=0 still yields the minimum one-char fill
    assert _trend_bar(1.0, 0.0, "#", bar_w=4).count("#") == 1
    # value==0 with any best yields an entirely-dotted bar
    assert _trend_bar(0.0, 0.0, "#", bar_w=4) == "." * 4
