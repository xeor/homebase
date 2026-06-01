from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import yaml

from ..cache.api import (
    cache_delete_paths,
    cache_load_rows,
    cache_store_rows,
    cache_upsert_rows,
)
from ..commands.archive import archive_pack_internal, archive_unpack_internal
from ..config.prefs import resolve_filter_expression
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    BENCHMARK_REPORT_FILE_NAME,
    BENCHMARK_SCORE_COLD_WEIGHT,
    BENCHMARK_SCORE_MODEL,
    BENCHMARK_SCORE_REF_DAY_VALUE,
    BENCHMARK_SCORE_REF_SECONDS,
    BENCHMARK_SCORE_WARM_WEIGHT,
    BENCHMARK_SUITE_VERSION,
    CACHE_MAX_AGE_S,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    PACKED_ARCHIVE_SUFFIX,
    TEST_REPORT_FILE_NAME,
)
from ..metadata.api import save_base_tags, sync_tag_symlinks
from . import benchmark_report
from .projects import git_info, project_row
from .rows import (
    collect_archived,
    collect_projects,
    collect_workspace_rows,
    compile_filter_expr,
    match_query,
)
from .seed import (
    commit_files,
    git_init,
    make_active_project,
    make_archive_entry,
    make_temp_basefolder,
    pack_archive_entry,
)


def archive_iso_from_ts(ts: int) -> str:
    return core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ)


def _benchmark_dataset_counts() -> tuple[int, int, int]:
    # Fixed dataset size for comparable runs.
    # active_projects, archived_dirs, archived_packed
    return 900, 900, 300


def _benchmark_make_git_repo(
    base_dir: Path,
    name: str,
    file_count: int,
    commits: int,
) -> Path:
    """Bench-only git repo: flat layout (no ``.base.yaml``, no
    ``repo/`` wrapper). Used as a raw input to ``git_info`` /
    ``project_row`` timings, not as a homebase project."""
    path = base_dir / name
    git_init(path, user_email="bench@example.local", user_name="bench")

    for i in range(file_count):
        sub = path / "src" / f"m{i % 16:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"f{i:05d}.txt").write_text(f"{name}:{i}\n")
    commit_files(path, "seed 0")

    step = max(1, file_count // max(1, commits - 1))
    for c in range(1, max(1, commits)):
        idx = (c * step) % file_count
        target = path / "src" / f"m{idx % 16:02d}" / f"f{idx:05d}.txt"
        target.write_text(f"{name}:{idx}:commit:{c}\n")
        commit_files(
            path,
            f"seed {c}",
            paths=[str(target.relative_to(path))],
        )
    return path


_BENCHMARK_TAGS_POOL: tuple[str, ...] = (
    "cli", "api", "data", "infra", "ops", "web", "ml", "db", "sync", "perf",
)


def _benchmark_make_project(base_dir: Path, idx: int) -> None:
    name = f"bench-{idx:04d}"
    if idx % 11 == 0:
        name += ".tmp"
    elif idx % 17 == 0:
        name += ".fork"

    tag_count = idx % 5
    tags = [
        _BENCHMARK_TAGS_POOL[(idx + k) % len(_BENCHMARK_TAGS_POOL)]
        for k in range(tag_count)
    ]
    log = {
        "events": [
            {
                "_event": "seeded",
                "_ts": archive_iso_from_ts(1700000000 + idx),
                "index": idx,
            }
        ]
    }
    path = make_active_project(
        base_dir,
        name,
        description=f"benchmark project {idx}",
        tags=tags,
        wip=(idx % 7 == 0),
        log=log,
    )

    if idx % 3 == 0:
        (path / "pyproject.toml").write_text("[project]\nname='bench'\n")
    if idx % 4 == 0:
        (path / ".envrc").write_text("export BENCH=1\n")
    if idx % 6 == 0:
        (path / "requirements.txt").write_text("pyyaml\ntextual\n")


def _benchmark_seed_dataset(base_dir: Path) -> dict[str, int]:
    active_count, archived_dir_count, archived_pack_count = _benchmark_dataset_counts()
    return _seed_benchmark_dataset(
        base_dir,
        active_count=active_count,
        archived_dir_count=archived_dir_count,
        archived_pack_count=archived_pack_count,
    )


def _seed_benchmark_dataset(
    base_dir: Path,
    *,
    active_count: int,
    archived_dir_count: int,
    archived_pack_count: int,
) -> dict[str, int]:
    """Parameterized variant used by the production seeder above and by
    the small-dataset regression test. The shape of the returned dict
    is part of the bench report contract — don't reshape without
    updating ``benchmark_report``."""
    for i in range(active_count):
        _benchmark_make_project(base_dir, i)

    git_small = _benchmark_make_git_repo(
        base_dir, "bench-git-small", file_count=24, commits=4
    )
    git_medium = _benchmark_make_git_repo(
        base_dir, "bench-git-medium", file_count=240, commits=8
    )
    git_large = _benchmark_make_git_repo(
        base_dir, "bench-git-large", file_count=1400, commits=12
    )

    for i in range(archived_dir_count):
        archived_ts = 1700100000 + i
        iso = archive_iso_from_ts(archived_ts)[:10]
        y, m, d = iso.split("-")
        entry_date = date(int(y), int(m), int(d))
        slug = f"arch-{i:04d}"
        entry = make_archive_entry(
            base_dir,
            date=entry_date,
            slug=slug,
            description=f"archived benchmark {i}",
            tags=["arch", f"g{i % 9}"],
        )
        if i % 5 == 0:
            (entry / "README.txt").write_text("benchmark archive payload\n")

    archive_root = base_dir / ARCHIVE_DIR_NAME
    packed = 0
    for i in range(min(archived_pack_count, archived_dir_count)):
        matches = sorted(
            [x for x in archive_root.glob(f"*/*_arch-{i:04d}") if x.is_dir()],
            key=lambda x: x.name,
        )
        if not matches:
            continue
        if pack_archive_entry(base_dir, matches[-1]) is not None:
            packed += 1

    return {
        "active_projects": active_count + 3,
        "archived_dirs": archived_dir_count,
        "archived_packed": packed,
        "git_small": 1,
        "git_medium": 1,
        "git_large": 1,
        "git_paths": {
            "small": str(git_small),
            "medium": str(git_medium),
            "large": str(git_large),
        },
    }


def _benchmark_timeit(
    name: str,
    fn: Callable[[], object],
    repeat: int = 5,
    warmup: int = 1,
) -> dict[str, object]:
    for _ in range(max(0, warmup)):
        try:
            fn()
        except (
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
            subprocess.SubprocessError,
            sqlite3.Error,
        ):
            pass

    times: list[float] = []
    last_result: object = None
    error: str | None = None
    for _ in range(max(1, repeat)):
        t0 = time.perf_counter()
        try:
            last_result = fn()
        except (
            OSError,
            ValueError,
            TypeError,
            RuntimeError,
            subprocess.SubprocessError,
            sqlite3.Error,
        ) as exc:
            error = str(exc)
            last_result = None
        dt = time.perf_counter() - t0
        times.append(dt)

    result_count = None
    if isinstance(last_result, tuple):
        try:
            result_count = len(last_result)
        except TypeError:
            result_count = None
    elif isinstance(last_result, list):
        result_count = len(last_result)

    out: dict[str, object] = {
        "name": name,
        "repeat": max(1, repeat),
        "min_s": min(times),
        "avg_s": sum(times) / len(times),
        "max_s": max(times),
    }
    if result_count is not None:
        out["result_count"] = result_count
    if error:
        out["error"] = error
    return out


def _benchmark_write_report(report_path: Path, run_data: dict[str, object]) -> None:
    existing: dict[str, object] = {}
    if report_path.is_file():
        try:
            loaded = yaml.safe_load(report_path.read_text())
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, yaml.YAMLError, json.JSONDecodeError, TypeError, ValueError):
            existing = {}

    runs = existing.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    runs.append(run_data)
    runs = runs[-100:]

    out: dict[str, object] = {
        "version": 1,
        "last_run": run_data.get("timestamp", ""),
        "runs": runs,
    }
    report_path.write_text(
        yaml.safe_dump(out, sort_keys=False, default_flow_style=False)
    )


def _benchmark_metric_error(name: str, err: str) -> dict[str, object]:
    return {
        "name": name,
        "repeat": 1,
        "min_s": 0.0,
        "avg_s": 0.0,
        "max_s": 0.0,
        "error": err,
    }


def _benchmark_metric_groups() -> dict[str, list[str]]:
    return benchmark_report.metric_groups()


def _benchmark_metric_featuresets() -> dict[str, str]:
    return benchmark_report.metric_featuresets()


def _default_score_metric_profile(metrics: list[dict[str, object]]) -> list[str]:
    return benchmark_report.default_score_metric_profile(metrics)


def _benchmark_run_suite(
    bench_root: Path,
    seed_dataset: bool = True,
    dataset_hint: dict[str, object] | None = None,
) -> tuple[dict[str, object], list[dict[str, object]], list[str], float, float]:
    notes: list[str] = []
    if seed_dataset:
        t_seed = time.perf_counter()
        dataset = _benchmark_seed_dataset(bench_root)
        seed_elapsed_s = time.perf_counter() - t_seed
    else:
        dataset = dict(dataset_hint or {})
        seed_elapsed_s = 0.0

    t_suite = time.perf_counter()
    metrics: list[dict[str, object]] = []

    metrics.append(
        _benchmark_timeit(
            "collect_projects", lambda: collect_projects(bench_root), repeat=4
        )
    )
    metrics.append(
        _benchmark_timeit(
            "collect_archived", lambda: collect_archived(bench_root), repeat=4
        )
    )

    active_rows, archived_rows = collect_workspace_rows(bench_root)
    packed_rows = [r for r in archived_rows if r.packed]
    archived_dir_rows = [r for r in archived_rows if not r.packed]

    metrics.append(
        _benchmark_timeit(
            "cache_store_rows_full",
            lambda: cache_store_rows(bench_root, active_rows, archived_rows),
            repeat=4,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "cache_load_rows_warm",
            lambda: cache_load_rows(bench_root, CACHE_MAX_AGE_S),
            repeat=8,
        )
    )

    upsert_rows = active_rows[:240]
    delete_paths = [r.path for r in active_rows[240:480]]
    metrics.append(
        _benchmark_timeit(
            "cache_upsert_rows_240",
            lambda: cache_upsert_rows(bench_root, upsert_rows, touch_refresh_ts=False),
            repeat=4,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "cache_delete_paths_240",
            lambda: cache_delete_paths(
                bench_root, delete_paths, touch_refresh_ts=False
            ),
            repeat=4,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "cache_restore_after_delete",
            lambda: cache_store_rows(bench_root, active_rows, archived_rows),
            repeat=2,
        )
    )

    q_plain = "bench-01"
    q_plain2 = "#cli"
    q_expr = "(#cli OR #api) :tags>1 :properties>=0 :created>=2000"
    q_expr2 = "(:created>=2023 AND :tags>0) OR !pkg"
    metrics.append(
        _benchmark_timeit(
            "query_plain_name_scan",
            lambda: [r for r in active_rows if match_query(r, q_plain)],
            repeat=8,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "query_plain_tag_scan",
            lambda: [r for r in active_rows if match_query(r, q_plain2)],
            repeat=8,
        )
    )

    pred1, pred1_err = compile_filter_expr(q_expr)
    if pred1_err:
        metrics.append(_benchmark_metric_error("query_expr_scan_1", pred1_err))
    else:
        metrics.append(
            _benchmark_timeit(
                "query_expr_scan_1",
                lambda: [r for r in active_rows if pred1(r)],
                repeat=8,
            )
        )

    pred2, pred2_err = compile_filter_expr(q_expr2)
    if pred2_err:
        metrics.append(_benchmark_metric_error("query_expr_scan_2", pred2_err))
    else:
        metrics.append(
            _benchmark_timeit(
                "query_expr_scan_2",
                lambda: [r for r in active_rows if pred2(r)],
                repeat=8,
            )
        )

    named_conf = bench_root / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    named_conf.parent.mkdir(parents=True, exist_ok=True)
    named_conf.write_text(
        yaml.safe_dump(
            {
                "filters": {
                    "named": {
                        "hot": "#cli OR #api",
                        "ops": "#ops :tags>0",
                    }
                }
            },
            sort_keys=False,
            default_flow_style=False,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "resolve_filter_expression_named",
            lambda: resolve_filter_expression(bench_root, "@hot AND :tags>1"),
            repeat=25,
            warmup=2,
        )
    )

    git_small = bench_root / "bench-git-small"
    git_medium = bench_root / "bench-git-medium"
    git_large = bench_root / "bench-git-large"
    metrics.append(
        _benchmark_timeit("git_info_small", lambda: git_info(git_small), repeat=10)
    )
    metrics.append(
        _benchmark_timeit("git_info_medium", lambda: git_info(git_medium), repeat=10)
    )
    metrics.append(
        _benchmark_timeit("git_info_large", lambda: git_info(git_large), repeat=10)
    )
    metrics.append(
        _benchmark_timeit(
            "project_row_git_small", lambda: project_row(git_small), repeat=8
        )
    )
    metrics.append(
        _benchmark_timeit(
            "project_row_git_medium", lambda: project_row(git_medium), repeat=8
        )
    )
    metrics.append(
        _benchmark_timeit(
            "project_row_git_large", lambda: project_row(git_large), repeat=8
        )
    )

    packed_sample = [r.path for r in packed_rows[:32]]
    archived_dir_sample = [r.path for r in archived_dir_rows[-32:]]
    if packed_sample:
        metrics.append(
            _benchmark_timeit(
                "archive_unpack_32",
                lambda: [archive_unpack_internal(bench_root, p) for p in packed_sample],
                repeat=1,
                warmup=0,
            )
        )
        unpacked_dirs = [
            p.with_name(p.name[: -len(PACKED_ARCHIVE_SUFFIX)]) for p in packed_sample
        ]
        metrics.append(
            _benchmark_timeit(
                "archive_repack_32",
                lambda: [archive_pack_internal(bench_root, p) for p in unpacked_dirs],
                repeat=1,
                warmup=0,
            )
        )
    else:
        metrics.append(_benchmark_metric_error("archive_unpack_32", "no packed rows"))
        metrics.append(_benchmark_metric_error("archive_repack_32", "no packed rows"))

    if archived_dir_sample:
        metrics.append(
            _benchmark_timeit(
                "archive_pack_32",
                lambda: [
                    archive_pack_internal(bench_root, p) for p in archived_dir_sample
                ],
                repeat=1,
                warmup=0,
            )
        )
        repacked = [
            p.with_name(f"{p.name}{PACKED_ARCHIVE_SUFFIX}") for p in archived_dir_sample
        ]
        metrics.append(
            _benchmark_timeit(
                "archive_unpack_back_32",
                lambda: [archive_unpack_internal(bench_root, p) for p in repacked],
                repeat=1,
                warmup=0,
            )
        )
    else:
        metrics.append(_benchmark_metric_error("archive_pack_32", "no archive dirs"))
        metrics.append(
            _benchmark_metric_error("archive_unpack_back_32", "no archive dirs")
        )

    tag_targets = [r.path for r in active_rows[:420]]
    metrics.append(
        _benchmark_timeit(
            "tags_write_420",
            lambda: [
                save_base_tags(bench_root, p, ["bench", "perf", f"g{(i % 9)}"])
                for i, p in enumerate(tag_targets)
            ],
            repeat=2,
            warmup=0,
        )
    )
    metrics.append(
        _benchmark_timeit(
            "tags_sync_symlink",
            lambda: sync_tag_symlinks(bench_root),
            repeat=2,
            warmup=0,
        )
    )

    if len(active_rows) < int(dataset.get("active_projects", 0)):
        notes.append("active row count lower than expected")
    if len(archived_rows) < int(dataset.get("archived_dirs", 0)):
        notes.append("archived row count lower than expected")
    if len([r for r in archived_rows if r.packed]) < int(
        dataset.get("archived_packed", 0)
    ):
        notes.append("packed archived rows lower than expected")

    suite_elapsed_s = time.perf_counter() - t_suite
    return dataset, metrics, notes, seed_elapsed_s, suite_elapsed_s


def _benchmark_metric_names() -> list[str]:
    # Core score set kept stable across versions so history stays comparable.
    return [
        "collect_projects",
        "collect_archived",
        "cache_store_rows_full",
        "cache_load_rows_warm",
        "query_plain_name_scan",
        "query_expr_scan_1",
    ]


def _benchmark_metric_map(run: dict[str, object]) -> dict[str, float]:
    return benchmark_report.metric_map(run)


def _benchmark_git_context(cwd: Path) -> dict[str, object]:
    out: dict[str, object] = {
        "repo": False,
        "head": "",
        "branch": "",
        "dirty": False,
    }
    try:
        p = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if p.returncode != 0 or (p.stdout or "").strip() != "true":
            return out
        out["repo"] = True
        p_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if p_head.returncode == 0:
            out["head"] = (p_head.stdout or "").strip()
        p_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if p_branch.returncode == 0:
            out["branch"] = (p_branch.stdout or "").strip()
        p_dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if p_dirty.returncode == 0:
            out["dirty"] = bool((p_dirty.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return out
    return out


def _benchmark_group_totals(run: dict[str, object]) -> dict[str, float]:
    return benchmark_report.group_totals(run)


def _benchmark_total_avg(run: dict[str, object]) -> float | None:
    return benchmark_report.total_avg(run)


def _benchmark_perf_score(elapsed_s: float | None) -> float | None:
    return benchmark_report.perf_score(
        elapsed_s,
        score_ref_seconds=BENCHMARK_SCORE_REF_SECONDS,
        score_ref_day_value=BENCHMARK_SCORE_REF_DAY_VALUE,
    )


def _benchmark_load_runs(report_path: Path) -> list[dict[str, object]]:
    return benchmark_report.load_runs(report_path)


def _benchmark_report_path(base_dir: Path, file_name: str) -> Path:
    return base_dir / HOMEBASE_DIR_NAME / file_name


def _benchmark_score_runs(
    runs: list[dict[str, object]], ignore_featuresets: set[str] | None = None
) -> list[dict[str, object]]:
    return benchmark_report.score_runs(
        runs,
        ignore_featuresets=ignore_featuresets,
        score_ref_seconds=BENCHMARK_SCORE_REF_SECONDS,
        score_ref_day_value=BENCHMARK_SCORE_REF_DAY_VALUE,
        warm_weight=BENCHMARK_SCORE_WARM_WEIGHT,
        cold_weight=BENCHMARK_SCORE_COLD_WEIGHT,
    )


def _fmt_bench_value(v: float | None) -> str:
    return benchmark_report.fmt_bench_value(v)


def _fmt_score(v: float | None) -> str:
    return benchmark_report.fmt_score(v)


def _fmt_bench_delta(v: float | None) -> str:
    return benchmark_report.fmt_bench_delta(v)


def _short_ts(ts: str) -> str:
    return benchmark_report.short_ts(ts)


def _available_featuresets(runs: list[dict[str, object]]) -> set[str]:
    return benchmark_report.available_featuresets(runs)


def _benchmark_results_compat_warnings(
    runs: list[dict[str, object]],
) -> list[str]:
    return benchmark_report.results_compat_warnings(runs)


def _run_filtered_metric_total(
    run: dict[str, object], ignore_featuresets: set[str]
) -> float | None:
    return benchmark_report.run_filtered_metric_total(run, ignore_featuresets)


def _run_filtered_metric_counts(
    run: dict[str, object], ignore_featuresets: set[str]
) -> tuple[int, int]:
    return benchmark_report.run_filtered_metric_counts(run, ignore_featuresets)


def cmd_benchmark_run(
    base_dir: Path,
    run_cwd: Path,
    comment: str = "",
    keep_basefolder: bool = False,
) -> int:

    bench_root = make_temp_basefolder(base_dir, "bench")

    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"benchmark timestamp: {ts}")
    print(f"benchmark base (temp): {bench_root}")
    print(f"configured base folder: {base_dir}")
    if comment:
        print(f"comment: {comment}")

    dataset: dict[str, object] = {}
    metrics: list[dict[str, object]] = []
    notes: list[str] = []
    cold_metrics: list[dict[str, object]] = []
    cold_notes: list[str] = []
    seed_elapsed_s = 0.0
    suite_elapsed_s = 0.0
    warm_suite_elapsed_s = 0.0
    warm_pass_elapsed_s = 0.0
    cleanup_elapsed_s = 0.0
    t_start = time.perf_counter()
    try:
        dataset, cold_metrics, cold_notes, seed_elapsed_s, suite_elapsed_s = (
            _benchmark_run_suite(bench_root, seed_dataset=True)
        )
        t_warm = time.perf_counter()
        _dataset2, metrics, notes, _seed2, warm_suite_elapsed_s = _benchmark_run_suite(
            bench_root, seed_dataset=False, dataset_hint=dataset
        )
        warm_pass_elapsed_s = time.perf_counter() - t_warm
    finally:
        t_cleanup = time.perf_counter()
        if not keep_basefolder:
            shutil.rmtree(bench_root, ignore_errors=True)
        cleanup_elapsed_s = time.perf_counter() - t_cleanup
    elapsed_s = time.perf_counter() - t_start

    print("")
    print("benchmark metrics:")
    for m in metrics:
        err = str(m.get("error", "")).strip()
        if err:
            print(f"- {m['name']:<18} error={err}")
            continue
        print(
            "- "
            f"{m['name']:<18} "
            f"min={float(m['min_s']):.4f}s "
            f"avg={float(m['avg_s']):.4f}s "
            f"max={float(m['max_s']):.4f}s"
        )

    total_avg_s = _benchmark_total_avg({"metrics": metrics})
    cold_total_avg_s = _benchmark_total_avg({"metrics": cold_metrics})
    perf_score = _benchmark_perf_score(warm_pass_elapsed_s)
    engine_score = _benchmark_perf_score(warm_suite_elapsed_s)
    cold_score = _benchmark_perf_score(suite_elapsed_s)
    cold_engine_score = _benchmark_perf_score(suite_elapsed_s)
    composite = benchmark_report.composite_score(
        perf_score,
        cold_score,
        warm_weight=BENCHMARK_SCORE_WARM_WEIGHT,
        cold_weight=BENCHMARK_SCORE_COLD_WEIGHT,
    )
    print("")
    print(
        "benchmark score: "
        f"{_fmt_score(perf_score)}"
        + f" (warm_pass_elapsed={warm_pass_elapsed_s:.2f}s"
        + (
            f", core total={_fmt_bench_value(total_avg_s)}"
            if total_avg_s is not None
            else ""
        )
        + ")"
    )
    print(
        "benchmark cold score: "
        f"{_fmt_score(cold_score)}"
        + f" (cold_suite_elapsed={suite_elapsed_s:.2f}s"
        + (
            f", cold core total={_fmt_bench_value(cold_total_avg_s)}"
            if cold_total_avg_s is not None
            else ""
        )
        + ")"
    )
    print(
        "benchmark phases: "
        f"seed={seed_elapsed_s:.2f}s cold_suite={suite_elapsed_s:.2f}s warm_suite={warm_suite_elapsed_s:.2f}s warm_pass={warm_pass_elapsed_s:.2f}s cleanup={cleanup_elapsed_s:.2f}s total_cmd={elapsed_s:.2f}s"
    )
    print(f"benchmark engine score: {_fmt_score(engine_score)} (warm suite basis)")

    run_data: dict[str, object] = {
        "suite_version": BENCHMARK_SUITE_VERSION,
        "timestamp": ts,
        "comment": comment,
        "configured_base_folder": str(base_dir),
        "benchmark_base_folder": str(bench_root),
        "keep_basefolder": keep_basefolder,
        "elapsed_s": warm_pass_elapsed_s,
        "warm_elapsed_s": warm_pass_elapsed_s,
        "cold_elapsed_s": suite_elapsed_s,
        "seed_elapsed_s": seed_elapsed_s,
        "suite_elapsed_s": warm_suite_elapsed_s,
        "cold_suite_elapsed_s": suite_elapsed_s,
        "warm_suite_elapsed_s": warm_suite_elapsed_s,
        "warm_pass_elapsed_s": warm_pass_elapsed_s,
        "cleanup_elapsed_s": cleanup_elapsed_s,
        "total_elapsed_s": elapsed_s,
        "total_command_elapsed_s": elapsed_s,
        "score_model": BENCHMARK_SCORE_MODEL,
        "score_ref_seconds": BENCHMARK_SCORE_REF_SECONDS,
        "score_ref_day_value": BENCHMARK_SCORE_REF_DAY_VALUE,
        "host": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count() or 0,
        },
        "git_context": _benchmark_git_context(run_cwd),
        "dataset": dataset,
        "metrics": metrics,
        "metrics_warm": metrics,
        "metrics_cold": cold_metrics,
        "metric_groups": _benchmark_metric_groups(),
        "metric_featuresets": _benchmark_metric_featuresets(),
        "score_metric_profile": _default_score_metric_profile(metrics),
        "notes": (cold_notes + notes),
        "score": composite,
        "score_warm": perf_score,
        "score_cold": cold_score,
        "score_warm_weight": BENCHMARK_SCORE_WARM_WEIGHT,
        "score_cold_weight": BENCHMARK_SCORE_COLD_WEIGHT,
        "engine_score": engine_score,
        "engine_score_warm": engine_score,
        "engine_score_cold": cold_engine_score,
        "score_basis_total_avg_s": total_avg_s,
        "score_basis_total_avg_s_warm": total_avg_s,
        "score_basis_total_avg_s_cold": cold_total_avg_s,
        "score_basis_elapsed_s": warm_pass_elapsed_s,
        "score_basis_elapsed_s_warm": warm_pass_elapsed_s,
        "score_basis_elapsed_s_cold": suite_elapsed_s,
    }

    report_path = _benchmark_report_path(base_dir, BENCHMARK_REPORT_FILE_NAME)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _benchmark_write_report(report_path, run_data)
    print("")
    print(f"benchmark report updated: {report_path}")
    if notes:
        print("benchmark notes:")
        for note in notes:
            print(f"- {note}")
    if not keep_basefolder:
        print("temp benchmark base folder removed")
    return 0


def cmd_benchmark_results(base_dir: Path, ignore_featuresets: set[str] | None = None) -> int:
    ignore_featuresets = set(ignore_featuresets or set())
    report_path = _benchmark_report_path(base_dir, BENCHMARK_REPORT_FILE_NAME)
    all_runs = _benchmark_load_runs(report_path)
    if not all_runs:
        print(f"no benchmark runs found: {report_path}")
        return 1

    runs = [
        r
        for r in all_runs
        if int(r.get("suite_version", BENCHMARK_SUITE_VERSION))
        == BENCHMARK_SUITE_VERSION
    ]
    skipped = len(all_runs) - len(runs)
    if not runs:
        print(
            f"no benchmark runs for suite_version={BENCHMARK_SUITE_VERSION} in: {report_path}"
        )
        return 1

    available_featuresets = _available_featuresets(runs)
    invalid_featuresets = sorted(
        fs for fs in ignore_featuresets if fs not in available_featuresets
    )
    if invalid_featuresets:
        print(
            "invalid featureset(s): " + ", ".join(invalid_featuresets),
            file=sys.stderr,
        )
        if available_featuresets:
            print(
                "valid featuresets: " + ", ".join(sorted(available_featuresets)),
                file=sys.stderr,
            )
        else:
            print("valid featuresets: (none)", file=sys.stderr)
        return 1

    scored = _benchmark_score_runs(runs, ignore_featuresets=ignore_featuresets)
    if ignore_featuresets:
        kept_any = False
        for run in runs:
            total_n, kept_n = _run_filtered_metric_counts(run, ignore_featuresets)
            if total_n > 0 and kept_n > 0:
                kept_any = True
                break
        if not kept_any:
            print(
                "ignore-featureset removed all score metrics; nothing left to compare",
                file=sys.stderr,
            )
            return 1

    print(f"benchmark report: {report_path}")
    print(f"suite_version: {BENCHMARK_SUITE_VERSION}")
    print(f"runs: {len(scored)}")
    compat_warnings = _benchmark_results_compat_warnings(scored)
    if compat_warnings:
        print("compat warnings:")
        for line in compat_warnings:
            print(f"- {line}")
    if available_featuresets:
        print("available featuresets: " + ", ".join(sorted(available_featuresets)))
    if ignore_featuresets:
        print(
            f"compare basis: filtered metrics (ignore featureset={','.join(sorted(ignore_featuresets))})"
        )
        total_n, kept_n = _run_filtered_metric_counts(runs[-1], ignore_featuresets)
        print(f"filtered profile metrics: kept={kept_n}/{total_n}")
    else:
        print("compare basis: elapsed wall-clock")
    if skipped > 0:
        print(f"skipped old-suite runs: {skipped}")
    print("")

    header = (
        f"{'#':>3}  {'timestamp':19}  {'score':>8}  {'best%':>7}  "
        f"{'warm_sc':>8}  {'cold_sc':>8}  {'warm_s':>10}  {'cold_s':>10}  {'delta':>9}  comment"
    )
    print(header)
    print("-" * len(header))
    for i, run in enumerate(scored, start=1):
        ts = _short_ts(str(run.get("timestamp", "")))
        score_raw = run.get("score")
        score = float(score_raw) if isinstance(score_raw, (int, float)) else None
        best_pct_raw = run.get("score_best_pct")
        best_pct = (
            float(best_pct_raw) if isinstance(best_pct_raw, (int, float)) else None
        )
        warm_elapsed = run.get("warm_elapsed_s", run.get("elapsed_s"))
        cold_elapsed = run.get("cold_elapsed_s", run.get("cold_suite_elapsed_s"))
        warm_score_raw = run.get("score_warm", run.get("score"))
        warm_score = (
            float(warm_score_raw) if isinstance(warm_score_raw, (int, float)) else None
        )
        cold_score_raw = run.get("score_cold")
        cold_score = (
            float(cold_score_raw) if isinstance(cold_score_raw, (int, float)) else None
        )
        delta = run.get("delta_prev_pct")
        comment = str(run.get("comment", "")).strip()
        if len(comment) > 48:
            comment = comment[:45] + "..."
        best_pct_text = f"{best_pct:.1f}%" if best_pct is not None else "-"
        print(
            f"{i:>3}  {ts:19}  {_fmt_score(score):>8}  "
            f"{best_pct_text:>7}  "
            f"{_fmt_score(warm_score):>8}  "
            f"{_fmt_score(cold_score):>8}  "
            f"{_fmt_bench_value(float(warm_elapsed) if isinstance(warm_elapsed, (int, float)) else None):>10}  "
            f"{_fmt_bench_value(float(cold_elapsed) if isinstance(cold_elapsed, (int, float)) else None):>10}  "
            f"{_fmt_bench_delta(delta):>9}  {comment}"
        )

    print("")
    latest = scored[-1]
    latest_map = _benchmark_metric_map(latest)
    prev_map = _benchmark_metric_map(scored[-2]) if len(scored) > 1 else {}
    latest_elapsed = latest.get("warm_elapsed_s", latest.get("elapsed_s"))
    latest_cold_elapsed = latest.get(
        "cold_elapsed_s", latest.get("cold_suite_elapsed_s")
    )
    latest_core_total = latest.get("total_avg_s")
    latest_filtered_total = latest.get("filtered_total_s")
    print(
        "latest basis: "
        f"elapsed={_fmt_bench_value(float(latest_elapsed) if isinstance(latest_elapsed, (int, float)) else None)}"
        f", cold_elapsed={_fmt_bench_value(float(latest_cold_elapsed) if isinstance(latest_cold_elapsed, (int, float)) else None)}"
        f", core_total={_fmt_bench_value(float(latest_core_total) if isinstance(latest_core_total, (int, float)) else None)}"
        + (
            f", filtered_total={_fmt_bench_value(float(latest_filtered_total) if isinstance(latest_filtered_total, (int, float)) else None)}"
            if ignore_featuresets
            else ""
        )
    )
    print("latest run metrics (avg_s):")
    for name in sorted(latest_map.keys()):
        cur = latest_map.get(name)
        prev = prev_map.get(name)
        delta = None
        if prev is not None and prev > 0 and cur is not None:
            delta = ((prev - cur) / prev) * 100.0
        print(
            f"- {name:<18} {_fmt_bench_value(cur):>10}  delta={_fmt_bench_delta(delta):>9}"
        )

    latest_groups = _benchmark_group_totals(latest)
    prev_groups = _benchmark_group_totals(scored[-2]) if len(scored) > 1 else {}
    if latest_groups:
        print("")
        print("latest metric groups (sum avg_s):")
        for group in sorted(latest_groups.keys()):
            cur = latest_groups.get(group)
            prev = prev_groups.get(group)
            delta = None
            if prev is not None and prev > 0 and cur is not None:
                delta = ((prev - cur) / prev) * 100.0
            print(
                f"- {group:<18} {_fmt_bench_value(cur):>10}  delta={_fmt_bench_delta(delta):>9}"
            )

    git_ctx = latest.get("git_context")
    if isinstance(git_ctx, dict) and bool(git_ctx.get("repo", False)):
        branch = str(git_ctx.get("branch", "")).strip() or "-"
        head = str(git_ctx.get("head", "")).strip() or "-"
        dirty = bool(git_ctx.get("dirty", False))
        print("")
        print(
            "latest run context: "
            f"branch={branch} head={head[:12]} dirty={'yes' if dirty else 'no'}"
        )

    print("")
    print("trend (warm + cold, relative to best):")
    best_score = max(
        [
            float(r.get("score"))
            for r in scored
            if isinstance(r.get("score"), (int, float))
        ]
        or [0.0]
    )
    best_cold_score = max(
        [
            float(r.get("score_cold"))
            for r in scored
            if isinstance(r.get("score_cold"), (int, float))
        ]
        or [0.0]
    )
    for i, run in enumerate(scored, start=1):
        raw_score = run.get("score")
        score = float(raw_score) if isinstance(raw_score, (int, float)) else 0.0
        rel = (score / best_score) if best_score > 0 else 0.0
        raw_cold_score = run.get("score_cold")
        cold_score = (
            float(raw_cold_score) if isinstance(raw_cold_score, (int, float)) else 0.0
        )
        cold_rel = (cold_score / best_cold_score) if best_cold_score > 0 else 0.0
        bar_w = 28
        fill = max(1, int(round(rel * bar_w))) if score > 0 else 0
        fill_cold = max(1, int(round(cold_rel * bar_w))) if cold_score > 0 else 0
        bar = "#" * fill + "." * (bar_w - fill)
        bar_cold = "=" * fill_cold + "." * (bar_w - fill_cold)
        print(
            f"{i:>3} W:{bar} ({_fmt_score(score):>8})  C:{bar_cold} ({_fmt_score(cold_score):>8})  {_short_ts(str(run.get('timestamp', '')))}"
        )

    return 0


def cmd_benchmark(
    base_dir: Path,
    run_cwd: Path,
    subcommand: str,
    comment: str = "",
    keep_basefolder: bool = False,
    ignore_featuresets: set[str] | None = None,
) -> int:
    if subcommand == "run":
        return cmd_benchmark_run(
            base_dir,
            run_cwd,
            comment=comment,
            keep_basefolder=keep_basefolder,
        )
    if subcommand == "results":
        return cmd_benchmark_results(base_dir, ignore_featuresets=ignore_featuresets)
    print("unknown benchmark subcommand", file=sys.stderr)
    return 1


def cmd_test(
    base_dir: Path,
    run_cwd: Path,
    comment: str = "",
    keep_basefolder: bool = False,
) -> int:

    test_root = make_temp_basefolder(base_dir, "test")
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"test timestamp: {ts}")
    print(f"test base (temp): {test_root}")
    print(f"configured base folder: {base_dir}")
    if comment:
        print(f"comment: {comment}")

    dataset: dict[str, object] = {}
    metrics: list[dict[str, object]] = []
    notes: list[str] = []
    seed_elapsed_s = 0.0
    suite_elapsed_s = 0.0
    cleanup_elapsed_s = 0.0
    t_start = time.perf_counter()
    try:
        dataset, metrics, notes, seed_elapsed_s, suite_elapsed_s = _benchmark_run_suite(
            test_root
        )
    finally:
        t_cleanup = time.perf_counter()
        if not keep_basefolder:
            shutil.rmtree(test_root, ignore_errors=True)
        cleanup_elapsed_s = time.perf_counter() - t_cleanup
    elapsed_s = time.perf_counter() - t_start

    print("")
    print("test metrics:")
    perf_score = _benchmark_perf_score(elapsed_s)
    engine_score = _benchmark_perf_score(suite_elapsed_s)
    failures = 0
    for m in metrics:
        err = str(m.get("error", "")).strip()
        if err:
            failures += 1
            print(f"- {m['name']:<26} FAIL  error={err}")
            continue
        print(
            "- "
            f"{m['name']:<26} PASS  "
            f"min={float(m['min_s']):.4f}s "
            f"avg={float(m['avg_s']):.4f}s "
            f"max={float(m['max_s']):.4f}s"
        )
    print(
        f"test phases: seed={seed_elapsed_s:.2f}s suite={suite_elapsed_s:.2f}s cleanup={cleanup_elapsed_s:.2f}s total={elapsed_s:.2f}s"
    )
    print(f"test score: {_fmt_score(perf_score)}  engine={_fmt_score(engine_score)}")

    report_path = _benchmark_report_path(base_dir, TEST_REPORT_FILE_NAME)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_data: dict[str, object] = {
        "suite_version": BENCHMARK_SUITE_VERSION,
        "timestamp": ts,
        "comment": comment,
        "configured_base_folder": str(base_dir),
        "test_base_folder": str(test_root),
        "keep_basefolder": keep_basefolder,
        "elapsed_s": elapsed_s,
        "seed_elapsed_s": seed_elapsed_s,
        "suite_elapsed_s": suite_elapsed_s,
        "cleanup_elapsed_s": cleanup_elapsed_s,
        "total_elapsed_s": elapsed_s,
        "score_model": BENCHMARK_SCORE_MODEL,
        "score_ref_seconds": BENCHMARK_SCORE_REF_SECONDS,
        "score_ref_day_value": BENCHMARK_SCORE_REF_DAY_VALUE,
        "host": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cpu_count": os.cpu_count() or 0,
        },
        "git_context": _benchmark_git_context(run_cwd),
        "dataset": dataset,
        "metrics": metrics,
        "metric_groups": _benchmark_metric_groups(),
        "metric_featuresets": _benchmark_metric_featuresets(),
        "score_metric_profile": _default_score_metric_profile(metrics),
        "notes": notes,
        "failures": failures,
        "score": perf_score,
        "engine_score": engine_score,
    }
    _benchmark_write_report(report_path, run_data)
    print("")
    print(f"test report updated: {report_path}")
    if notes:
        print("test notes:")
        for note in notes:
            print(f"- {note}")
    if not keep_basefolder:
        print("temp test base folder removed")
    if failures > 0 or notes:
        return 1
    return 0
