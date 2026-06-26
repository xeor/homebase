from __future__ import annotations

from pathlib import Path

from homebase.commands import debug_tools
from homebase.core.setup_model import SetupDebugTool


def test_build_dev_debug_tools_shape(tmp_path: Path) -> None:
    tools = debug_tools.build_dev_debug_tools(tmp_path)
    assert all(isinstance(t, SetupDebugTool) for t in tools)
    ids = [t.id for t in tools]
    assert ids == ["env_report", "run_benchmark", "run_pytest", "qa_summary"]
    assert all(tid.replace("_", "").isalnum() for tid in ids)


def test_env_report_runs(tmp_path: Path) -> None:
    report = debug_tools._env_report(tmp_path)
    assert "Environment report" in report
    assert "homebase version:" in report
    assert "pyobjc" in report
    assert str(tmp_path) in report


def test_run_pytest_without_checkout_warns(monkeypatch) -> None:
    monkeypatch.setattr(debug_tools, "_repo_root", lambda: None)
    report = debug_tools._run_pytest()
    assert "not a source checkout" in report


def test_qa_summary_without_checkout_warns(monkeypatch) -> None:
    monkeypatch.setattr(debug_tools, "_repo_root", lambda: None)
    report = debug_tools._qa_summary()
    assert "not a source checkout" in report


def test_qa_status_snapshot_reads_section(tmp_path: Path) -> None:
    qa = tmp_path / "docs" / "QA"
    qa.mkdir(parents=True)
    (qa / "README.md").write_text(
        "# QA\n\n## Status snapshot\n\n- ruff: clean\n- mypy: 0 errors\n\n## Next\n",
        encoding="utf-8",
    )
    out = "\n".join(debug_tools._qa_status_snapshot(tmp_path))
    assert "ruff: clean" in out
    assert "mypy: 0 errors" in out
    # stops at the next heading
    assert "Next" not in out


def test_run_benchmark_captures_output(tmp_path: Path, monkeypatch) -> None:
    def fake_run(base_dir: Path, run_cwd: Path) -> int:
        print(f"benchmark base: {base_dir}")
        print("done")
        return 0

    monkeypatch.setattr(
        "homebase.workspace.benchmark.cmd_benchmark_run", fake_run
    )
    report = debug_tools._run_benchmark(tmp_path)
    assert "Performance benchmark" in report
    assert "done" in report
    assert "ok" in report
