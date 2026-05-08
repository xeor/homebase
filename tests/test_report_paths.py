from __future__ import annotations

from pathlib import Path

import yaml

from homebase.core import nested as nested_utils
from homebase.workspace import benchmark as benchmark_workspace
from homebase.workspace import regression as regression_workspace


def test_benchmark_results_reads_reports_from_base_homebase(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    run_cwd = tmp_path / "cwd"
    (base_dir / ".homebase").mkdir(parents=True)
    (run_cwd / ".homebase").mkdir(parents=True)

    report_path = run_cwd / ".homebase" / "benchmark.yaml"
    payload = {
        "runs": [
            {
                "suite_version": 1,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "score": 1.0,
                "metrics": [],
            }
        ]
    }
    report_path.write_text(yaml.safe_dump(payload, sort_keys=False))

    rc = benchmark_workspace.cmd_benchmark_results(base_dir)
    assert rc == 1


def test_regression_report_written_to_base_homebase(
    tmp_path: Path, monkeypatch
) -> None:
    base_dir = tmp_path / "base"
    run_cwd = tmp_path / "cwd"
    base_dir.mkdir(parents=True)
    run_cwd.mkdir(parents=True)

    monkeypatch.setattr(regression_workspace, "_regression_cases", lambda: [])

    rc = regression_workspace.cmd_test_regression(base_dir, run_cwd)
    assert rc == 0
    assert (base_dir / ".homebase" / "regression-test.yaml").is_file()
    assert not (run_cwd / ".homebase" / "regression-test.yaml").exists()


def test_nested_report_written_to_base_homebase(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    run_cwd = tmp_path / "cwd"
    base_dir.mkdir(parents=True)
    run_cwd.mkdir(parents=True)

    nested_entry = {
        "relative": "a/b",
        "reason": "nested marker",
        "suggested_name": "a-b",
        "suggested_tags": [],
        "nested": True,
        "active_subfolder": True,
    }
    counts = {
        "dirs_scanned": 1,
        "markers_total": 1,
        "active_roots": 1,
        "archive_roots": 0,
        "active_subfolder_markers": 1,
        "archive_subfolder_markers": 0,
        "active_child_of_marker": 1,
        "archive_child_of_marker": 0,
    }

    rc = nested_utils.cmd_utils_opt_in_nested_discovery(
        base_dir,
        base_marker_file=".base.yaml",
        archive_dir_name="_archive",
        nested_discovery_enabled=lambda _b: False,
        set_nested_discovery_enabled=lambda _b, _v: None,
        prompt_yes_no=lambda _q, _d: True,
        scan_nested_markers_all_fn=lambda _b: (counts, [nested_entry]),
    )
    assert rc == 2
    assert (base_dir / ".homebase" / "nested-discovery.yaml").is_file()
    assert not (run_cwd / ".homebase" / "nested-discovery.yaml").exists()
