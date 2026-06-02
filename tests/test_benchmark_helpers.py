"""Unit tests for the in-process helpers in ``workspace/benchmark``.

The full benchmark suite is too heavy to run as a unit test (it seeds
hundreds of projects and packs archives). These tests focus on the
small pure-ish helpers that the suite is built from."""
from __future__ import annotations

from pathlib import Path

import yaml

from homebase.workspace import benchmark as bm

# ---- _benchmark_timeit ----------------------------------------------


def test_benchmark_timeit_records_min_avg_max_for_quick_fn() -> None:
    metric = bm._benchmark_timeit("quick", lambda: 1, repeat=4, warmup=0)
    assert metric["name"] == "quick"
    assert metric["repeat"] == 4
    assert metric["min_s"] >= 0
    assert metric["avg_s"] >= metric["min_s"]
    assert metric["max_s"] >= metric["avg_s"]
    assert "error" not in metric


def test_benchmark_timeit_runs_warmup_iterations() -> None:
    """``warmup=N`` calls the fn N extra times before the timed loop —
    those calls are not counted in ``repeat``."""
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1

    bm._benchmark_timeit("warm", fn, repeat=3, warmup=2)
    assert calls["n"] == 2 + 3


def test_benchmark_timeit_floors_repeat_at_one() -> None:
    """``repeat=0`` is clamped to 1 — we always need at least one
    sample so the min/avg/max lookups don't blow up."""
    metric = bm._benchmark_timeit("floor", lambda: None, repeat=0, warmup=0)
    assert metric["repeat"] == 1


def test_benchmark_timeit_captures_result_count_for_list_results() -> None:
    """List/tuple results carry their length as ``result_count`` for
    the benchmark report — scalar results don't."""
    list_metric = bm._benchmark_timeit("l", lambda: [1, 2, 3], repeat=1, warmup=0)
    tuple_metric = bm._benchmark_timeit("t", lambda: (1, 2), repeat=1, warmup=0)
    scalar_metric = bm._benchmark_timeit("s", lambda: 42, repeat=1, warmup=0)
    assert list_metric.get("result_count") == 3
    assert tuple_metric.get("result_count") == 2
    assert "result_count" not in scalar_metric


def test_benchmark_timeit_records_error_when_fn_raises() -> None:
    def boom() -> None:
        raise ValueError("boom!")

    metric = bm._benchmark_timeit("err", boom, repeat=2, warmup=0)
    assert metric.get("error") == "boom!"
    # repeat is still observed even when every call errors.
    assert metric["repeat"] == 2


def test_benchmark_timeit_swallows_errors_during_warmup() -> None:
    """The warmup loop must never propagate exceptions — the timed
    loop has its own error handling and benchmarking should be best
    effort."""
    counter = {"n": 0}

    def fn() -> int:
        counter["n"] += 1
        if counter["n"] <= 2:
            raise OSError("warm fails")
        return counter["n"]

    metric = bm._benchmark_timeit("warm-err", fn, repeat=1, warmup=2)
    assert metric["repeat"] == 1
    assert "error" not in metric


# ---- _benchmark_metric_error -----------------------------------------


def test_benchmark_metric_error_shape() -> None:
    err = bm._benchmark_metric_error("noop", "explain why")
    assert err == {
        "name": "noop",
        "repeat": 1,
        "min_s": 0.0,
        "avg_s": 0.0,
        "max_s": 0.0,
        "error": "explain why",
    }


# ---- _benchmark_write_report ----------------------------------------


def test_write_report_seeds_new_file(tmp_path: Path) -> None:
    report = tmp_path / "report.yaml"
    run = {"timestamp": "2026-06-02", "metrics": []}
    bm._benchmark_write_report(report, run)

    loaded = yaml.safe_load(report.read_text())
    assert loaded["version"] == 1
    assert loaded["last_run"] == "2026-06-02"
    assert loaded["runs"] == [run]


def test_write_report_appends_to_existing_runs(tmp_path: Path) -> None:
    report = tmp_path / "report.yaml"
    bm._benchmark_write_report(report, {"timestamp": "first"})
    bm._benchmark_write_report(report, {"timestamp": "second"})

    loaded = yaml.safe_load(report.read_text())
    timestamps = [r["timestamp"] for r in loaded["runs"]]
    assert timestamps == ["first", "second"]
    # ``last_run`` always tracks the most recent timestamp.
    assert loaded["last_run"] == "second"


def test_write_report_caps_at_100_runs(tmp_path: Path) -> None:
    """A long history is trimmed to the most recent 100 runs so the
    report file doesn't grow without bound."""
    report = tmp_path / "report.yaml"
    # Seed an existing file with 105 historical runs to skip 105
    # serial write calls.
    seeded = {
        "version": 1,
        "last_run": "h104",
        "runs": [{"timestamp": f"h{i}"} for i in range(105)],
    }
    report.write_text(yaml.safe_dump(seeded, sort_keys=False))

    bm._benchmark_write_report(report, {"timestamp": "fresh"})
    loaded = yaml.safe_load(report.read_text())
    assert len(loaded["runs"]) == 100
    timestamps = [r["timestamp"] for r in loaded["runs"]]
    # Oldest entries fell off the front; freshest entry is at the end.
    assert timestamps[-1] == "fresh"
    assert timestamps[0] == "h6"


def test_write_report_recovers_from_corrupt_existing_file(tmp_path: Path) -> None:
    """A broken YAML file shouldn't block a new run — the helper
    silently resets and starts fresh."""
    report = tmp_path / "report.yaml"
    report.write_text("not: valid: yaml: : :\n  - bad")
    bm._benchmark_write_report(report, {"timestamp": "fresh"})
    loaded = yaml.safe_load(report.read_text())
    assert loaded["runs"] == [{"timestamp": "fresh"}]


def test_write_report_drops_runs_field_when_wrong_type(tmp_path: Path) -> None:
    """If a previous writer left ``runs`` as a non-list, ignore it —
    don't crash trying to ``.append`` to a string."""
    report = tmp_path / "report.yaml"
    report.write_text(yaml.safe_dump({"version": 1, "runs": "broken"}))
    bm._benchmark_write_report(report, {"timestamp": "fresh"})
    loaded = yaml.safe_load(report.read_text())
    assert loaded["runs"] == [{"timestamp": "fresh"}]


# ---- _benchmark_report_path ------------------------------------------


def test_benchmark_report_path_uses_homebase_dir(tmp_path: Path) -> None:
    """Reports always sit under ``<base>/.homebase/<file>``."""
    p = bm._benchmark_report_path(tmp_path, "x.yaml")
    assert p.parent.name == ".homebase"
    assert p.name == "x.yaml"


# ---- _benchmark_make_project -----------------------------------------


def test_benchmark_make_project_creates_marker_file(tmp_path: Path) -> None:
    bm._benchmark_make_project(tmp_path, idx=0)
    candidates = [p for p in tmp_path.iterdir() if p.name.startswith("bench-")]
    assert len(candidates) == 1
    proj = candidates[0]
    assert (proj / ".base.yaml").is_file()


def test_benchmark_make_project_tmp_suffix_every_eleventh(tmp_path: Path) -> None:
    """idx % 11 == 0 gets ``.tmp`` (precedence over ``.fork``)."""
    bm._benchmark_make_project(tmp_path, idx=11)
    assert (tmp_path / "bench-0011.tmp").is_dir()


def test_benchmark_make_project_fork_suffix_at_17(tmp_path: Path) -> None:
    bm._benchmark_make_project(tmp_path, idx=17)
    assert (tmp_path / "bench-0017.fork").is_dir()


def test_benchmark_make_project_wip_every_seventh(tmp_path: Path) -> None:
    """idx % 7 == 0 → wip: true in metadata."""
    bm._benchmark_make_project(tmp_path, idx=7)
    meta = yaml.safe_load((tmp_path / "bench-0007" / ".base.yaml").read_text())
    assert meta.get("wip") is True


def test_benchmark_make_project_writes_extra_files_modular(tmp_path: Path) -> None:
    """Every 3rd, 4th, 6th idx drops a specific extra file in the
    project root (pyproject.toml / .envrc / requirements.txt)."""
    bm._benchmark_make_project(tmp_path, idx=12)  # 12 % 3 == 0, 12 % 4 == 0, 12 % 6 == 0
    proj = tmp_path / "bench-0012"
    assert (proj / "pyproject.toml").is_file()
    assert (proj / ".envrc").is_file()
    assert (proj / "requirements.txt").is_file()


# ---- _benchmark_dataset_counts ---------------------------------------


def test_benchmark_dataset_counts_constant_shape() -> None:
    """The dataset counts are intentionally fixed so benchmark runs
    are comparable across machines. If this changes, downstream
    score calibration breaks."""
    active, archived_dirs, archived_packed = bm._benchmark_dataset_counts()
    assert (active, archived_dirs, archived_packed) == (900, 900, 300)


# ---- _benchmark_git_context ------------------------------------------


def _fake_run_factory(by_args):
    def fake_run(cmd, **_kwargs):
        key = tuple(cmd[:3])

        class _Proc:
            def __init__(self, returncode: int, stdout: str) -> None:
                self.returncode = returncode
                self.stdout = stdout

        rc, out = by_args.get(key, (1, ""))
        return _Proc(rc, out)

    return fake_run


def test_benchmark_git_context_returns_empty_when_not_in_repo(tmp_path: Path, monkeypatch) -> None:
    fake = _fake_run_factory({
        ("git", "rev-parse", "--is-inside-work-tree"): (128, "fatal: not a repo\n"),
    })
    monkeypatch.setattr(bm.subprocess, "run", fake)
    out = bm._benchmark_git_context(tmp_path)
    assert out == {"repo": False, "head": "", "branch": "", "dirty": False}


def test_benchmark_git_context_populates_for_clean_repo(tmp_path: Path, monkeypatch) -> None:
    fake = _fake_run_factory({
        ("git", "rev-parse", "--is-inside-work-tree"): (0, "true\n"),
        ("git", "rev-parse", "HEAD"): (0, "abc123\n"),
        ("git", "rev-parse", "--abbrev-ref"): (0, "main\n"),
        ("git", "status", "--porcelain"): (0, ""),
    })
    monkeypatch.setattr(bm.subprocess, "run", fake)
    out = bm._benchmark_git_context(tmp_path)
    assert out == {
        "repo": True,
        "head": "abc123",
        "branch": "main",
        "dirty": False,
    }


def test_benchmark_git_context_marks_dirty_when_status_nonempty(
    tmp_path: Path, monkeypatch,
) -> None:
    fake = _fake_run_factory({
        ("git", "rev-parse", "--is-inside-work-tree"): (0, "true\n"),
        ("git", "rev-parse", "HEAD"): (0, "abc\n"),
        ("git", "rev-parse", "--abbrev-ref"): (0, "feature\n"),
        ("git", "status", "--porcelain"): (0, " M file\n"),
    })
    monkeypatch.setattr(bm.subprocess, "run", fake)
    out = bm._benchmark_git_context(tmp_path)
    assert out["dirty"] is True


def test_benchmark_git_context_swallows_oserror(tmp_path: Path, monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise OSError("git missing")

    monkeypatch.setattr(bm.subprocess, "run", boom)
    out = bm._benchmark_git_context(tmp_path)
    # default empty dict on any failure.
    assert out["repo"] is False
    assert out["head"] == ""


# ---- ArchiveOp gating -----------------------------------------------


def test_seed_benchmark_dataset_skips_packing_without_handler(tmp_path: Path) -> None:
    """Without an injected ``archive_pack_internal`` the seeder still
    creates archive dirs but reports ``archived_packed == 0``."""
    summary = bm._seed_benchmark_dataset(
        tmp_path,
        active_count=2,
        archived_dir_count=2,
        archived_pack_count=2,
        archive_pack_internal=None,
    )
    assert summary["archived_packed"] == 0
    assert summary["archived_dirs"] == 2


def test_seed_benchmark_dataset_returns_git_paths_and_active_count(tmp_path: Path) -> None:
    summary = bm._seed_benchmark_dataset(
        tmp_path,
        active_count=3,
        archived_dir_count=0,
        archived_pack_count=0,
    )
    # active_count + 3 git repos.
    assert summary["active_projects"] == 6
    assert summary["git_small"] == 1
    assert summary["git_medium"] == 1
    assert summary["git_large"] == 1
    git_paths = summary["git_paths"]
    assert isinstance(git_paths, dict)
    assert {"small", "medium", "large"} <= set(git_paths)


# ---- _benchmark_seed_dataset (wrapper) ------------------------------


def test_benchmark_seed_dataset_invokes_seed_with_fixed_counts(
    tmp_path: Path, monkeypatch,
) -> None:
    """The thin ``_benchmark_seed_dataset`` wrapper just plugs the
    fixed counts into ``_seed_benchmark_dataset``."""
    captured: dict[str, int] = {}

    def fake_seed(base_dir, *, active_count, archived_dir_count, archived_pack_count, archive_pack_internal=None):
        captured.update(
            active=active_count,
            archived=archived_dir_count,
            packed=archived_pack_count,
        )
        return {"active_projects": active_count}

    monkeypatch.setattr(bm, "_seed_benchmark_dataset", fake_seed)
    bm._benchmark_seed_dataset(tmp_path)
    assert captured["active"] == 900
    assert captured["archived"] == 900
    assert captured["packed"] == 300


# ---- archive_iso_from_ts (re-export) ---------------------------------


def test_archive_iso_from_ts_returns_iso_string() -> None:
    # 1_700_100_000 is in late 2023 UTC.
    out = bm.archive_iso_from_ts(1_700_100_000)
    assert out.startswith("2023-")
    assert len(out) >= 10
