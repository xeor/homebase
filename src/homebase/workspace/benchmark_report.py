from __future__ import annotations

import math
from pathlib import Path

import yaml


def metric_groups() -> dict[str, list[str]]:
    return {
        "core": [
            "collect_projects",
            "collect_archived",
            "cache_store_rows_full",
            "cache_load_rows_warm",
            "query_plain_name_scan",
            "query_expr_scan_1",
        ],
        "cache_mutation": [
            "cache_upsert_rows_240",
            "cache_delete_paths_240",
            "cache_restore_after_delete",
        ],
        "query_extra": [
            "query_plain_tag_scan",
            "query_expr_scan_2",
            "resolve_filter_expression_named",
        ],
        "git": [
            "git_info_small",
            "git_info_medium",
            "git_info_large",
            "project_row_git_small",
            "project_row_git_medium",
            "project_row_git_large",
        ],
        "archive": [
            "archive_unpack_32",
            "archive_repack_32",
            "archive_pack_32",
            "archive_unpack_back_32",
        ],
        "tags": [
            "tags_write_420",
            "tags_sync_symlink",
        ],
    }


def metric_featuresets() -> dict[str, str]:
    out: dict[str, str] = {}
    for group, metrics in metric_groups().items():
        for metric in metrics:
            out[metric] = group
    return out


def default_score_metric_profile(metrics: list[dict[str, object]]) -> list[str]:
    out: list[str] = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name", "")).strip()
        if not name:
            continue
        if str(metric.get("error", "")).strip():
            continue
        out.append(name)
    return out


def metric_map(run: dict[str, object]) -> dict[str, float]:
    out: dict[str, float] = {}
    metrics = run.get("metrics", [])
    if not isinstance(metrics, list):
        return out
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = str(metric.get("name", "")).strip()
        if not name:
            continue
        try:
            avg_s = float(metric.get("avg_s", 0.0))
        except (TypeError, ValueError):
            continue
        if avg_s < 0:
            continue
        out[name] = avg_s
    return out


def group_totals(run: dict[str, object]) -> dict[str, float]:
    mm = metric_map(run)
    out: dict[str, float] = {}
    for group, names in metric_groups().items():
        vals = [mm[name] for name in names if name in mm]
        if vals:
            out[group] = sum(vals)
    return out


def total_avg(run: dict[str, object]) -> float | None:
    mm = metric_map(run)
    profile = run.get("score_metric_profile")
    if isinstance(profile, list) and profile:
        vals2: list[float] = []
        for name_raw in profile:
            name = str(name_raw)
            if name not in mm:
                return None
            vals2.append(mm[name])
        return sum(vals2)
    if mm:
        return sum(mm.values())
    score_groups: list[tuple[str, ...]] = [
        ("collect_projects",),
        ("collect_archived",),
        ("cache_store_rows_full", "cache_store_rows"),
        ("cache_load_rows_warm", "cache_load_rows"),
        ("query_plain_name_scan", "query_plain_scan"),
        ("query_expr_scan_1", "query_expr_scan"),
    ]
    vals: list[float] = []
    for group in score_groups:
        found = None
        for name in group:
            if name in mm:
                found = mm[name]
                break
        if found is None:
            return None
        vals.append(found)
    return sum(vals)


def perf_score(
    elapsed_s: float | None,
    *,
    score_ref_seconds: float,
    score_ref_day_value: float,
) -> float | None:
    if elapsed_s is None:
        return None
    if elapsed_s == float("inf"):
        return 0.0
    if elapsed_s <= 0:
        return None
    day_s = 24.0 * 60.0 * 60.0
    exponent = math.log(100.0 / score_ref_day_value) / math.log(day_s / score_ref_seconds)
    return (day_s / elapsed_s) ** exponent


def load_runs(report_path: Path) -> list[dict[str, object]]:
    if not report_path.is_file():
        return []
    try:
        raw = yaml.safe_load(report_path.read_text())
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(raw, dict):
        return []
    runs = raw.get("runs", [])
    if not isinstance(runs, list):
        return []
    return [run for run in runs if isinstance(run, dict)]


def run_filtered_metric_total(run: dict[str, object], ignore_featuresets: set[str]) -> float | None:
    if not ignore_featuresets:
        return None
    mm = metric_map(run)
    if not mm:
        return None
    names = sorted(mm.keys())
    featureset_map = dict(metric_featuresets())
    raw = run.get("metric_featuresets", {})
    if isinstance(raw, dict):
        for k, v in raw.items():
            featureset_map[str(k)] = str(v)
    vals: list[float] = []
    for name in names:
        fut = str(featureset_map.get(name, ""))
        if fut and fut in ignore_featuresets:
            continue
        vals.append(mm[name])
    return sum(vals) if vals else None


def run_filtered_metric_counts(run: dict[str, object], ignore_featuresets: set[str]) -> tuple[int, int]:
    mm = metric_map(run)
    if not mm:
        return (0, 0)
    names = sorted(mm.keys())
    featureset_map = dict(metric_featuresets())
    raw = run.get("metric_featuresets", {})
    if isinstance(raw, dict):
        for k, v in raw.items():
            featureset_map[str(k)] = str(v)
    total = 0
    kept = 0
    for name in names:
        total += 1
        fut = str(featureset_map.get(name, ""))
        if fut and fut in ignore_featuresets:
            continue
        kept += 1
    return total, kept


def score_runs(
    runs: list[dict[str, object]],
    *,
    ignore_featuresets: set[str] | None,
    score_ref_seconds: float,
    score_ref_day_value: float,
) -> list[dict[str, object]]:
    ignored = ignore_featuresets or set()
    totals = [total_avg(run) for run in runs]
    filtered_totals = [run_filtered_metric_total(run, ignored) if ignored else None for run in runs]
    elapsed_vals: list[float | None] = []
    for i, run in enumerate(runs):
        if ignored:
            raw = filtered_totals[i]
            elapsed_vals.append(float(raw) if isinstance(raw, (int, float)) and float(raw) > 0 else None)
        else:
            raw = run.get("elapsed_s")
            if isinstance(raw, (int, float)) and float(raw) > 0:
                elapsed_vals.append(float(raw))
            else:
                elapsed_vals.append(totals[i])
    scores = [
        perf_score(value, score_ref_seconds=score_ref_seconds, score_ref_day_value=score_ref_day_value)
        for value in elapsed_vals
    ]
    valid_scores = [s for s in scores if s is not None and s >= 0]
    best_score = max(valid_scores) if valid_scores else 0.0

    out: list[dict[str, object]] = []
    prev_score: float | None = None
    for i, run in enumerate(runs):
        score = scores[i]
        delta_score_pct: float | None = None
        if prev_score is not None and prev_score > 0 and score is not None:
            delta_score_pct = ((score - prev_score) / prev_score) * 100.0
        if score is not None and score >= 0:
            prev_score = score
        best_pct: float | None = None
        if score is not None and best_score > 0:
            best_pct = (score / best_score) * 100.0
        enriched = dict(run)
        enriched["total_avg_s"] = totals[i]
        enriched["filtered_total_s"] = filtered_totals[i]
        enriched["elapsed_s"] = elapsed_vals[i]
        enriched["score"] = score
        enriched["score_best_pct"] = best_pct
        enriched["delta_prev_pct"] = delta_score_pct
        out.append(enriched)
    return out


def fmt_bench_value(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}s"


def fmt_score(v: float | None) -> str:
    if v is None:
        return "-"
    if v >= 1000:
        return f"{v:.0f}"
    if v >= 100:
        return f"{v:.1f}"
    return f"{v:.2f}"


def fmt_bench_delta(v: float | None) -> str:
    if v is None:
        return "-"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def short_ts(ts: str) -> str:
    text = str(ts).strip()
    return "-" if not text else text[:19]


def available_featuresets(runs: list[dict[str, object]]) -> set[str]:
    out: set[str] = set(metric_groups().keys())
    for run in runs:
        raw = run.get("metric_featuresets", {})
        if not isinstance(raw, dict):
            continue
        for value in raw.values():
            s = str(value).strip()
            if s:
                out.add(s)
    return out


def results_compat_warnings(runs: list[dict[str, object]]) -> list[str]:
    if not runs:
        return []
    n = len(runs)
    missing_score_warm = sum(1 for run in runs if "score_warm" not in run)
    missing_score_cold = sum(1 for run in runs if "score_cold" not in run)
    missing_warm_elapsed = sum(1 for run in runs if "warm_elapsed_s" not in run)
    missing_cold_elapsed = sum(1 for run in runs if "cold_elapsed_s" not in run and "cold_suite_elapsed_s" not in run)
    missing_profile = sum(
        1
        for run in runs
        if not isinstance(run.get("score_metric_profile"), list) or not bool(run.get("score_metric_profile"))
    )
    lines: list[str] = []
    if missing_score_warm > 0:
        lines.append(f"compat: score_warm missing in {missing_score_warm}/{n} run(s) (using score fallback)")
    if missing_score_cold > 0:
        lines.append(f"compat: score_cold missing in {missing_score_cold}/{n} run(s)")
    if missing_warm_elapsed > 0:
        lines.append(f"compat: warm_elapsed_s missing in {missing_warm_elapsed}/{n} run(s) (using elapsed_s fallback)")
    if missing_cold_elapsed > 0:
        lines.append(f"compat: cold elapsed field missing in {missing_cold_elapsed}/{n} run(s)")
    if missing_profile > 0:
        lines.append(f"profile: score_metric_profile missing/empty in {missing_profile}/{n} run(s)")
    return lines
