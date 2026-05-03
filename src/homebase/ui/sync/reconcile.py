from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow


def mode_has_stale_rows(app: Any, mode: str) -> bool:
    rows = app.active_rows if mode == "active" else app.archived_rows
    return any(bool(row.stale) for row in rows)


def _reconcile_mode_cfg(app: Any, mode: str) -> dict[str, object]:
    cfg = app.reconcile_config.get(mode, {})
    return cfg if isinstance(cfg, dict) else {}


def effective_reconcile_wait_s(
    app: Any,
    mode: str,
) -> float:
    cfg = _reconcile_mode_cfg(app, mode)
    base_wait = max(1.0, float(cfg.get("interval_s", 5.0)))
    if mode_has_stale_rows(app, mode) and bool(cfg.get("stale_boost", True)):
        return max(0.05, float(cfg.get("stale_interval_s", base_wait)))
    return base_wait


def effective_reconcile_parallelism(
    app: Any,
    mode: str,
) -> int:
    cfg = _reconcile_mode_cfg(app, mode)
    base_parallelism = max(1, int(cfg.get("parallelism", 1)))
    if mode_has_stale_rows(app, mode) and bool(cfg.get("stale_boost", True)):
        return max(base_parallelism, int(cfg.get("stale_parallelism", base_parallelism)))
    return base_parallelism


def effective_reconcile_batch_size(
    app: Any,
    mode: str,
) -> int:
    cfg = _reconcile_mode_cfg(app, mode)
    base_batch = max(1, int(cfg.get("batch_size", 1)))
    if mode_has_stale_rows(app, mode) and bool(cfg.get("stale_boost", True)):
        return max(base_batch, int(cfg.get("stale_batch_size", base_batch)))
    return base_batch


def bump_row_usage(app: Any, path: Path | None, *, weight: float = 1.0) -> None:
    if path is None:
        return
    cur = float(app.row_usage_score.get(path, 0.0))
    app.row_usage_score[path] = min(1000.0, cur + max(0.1, float(weight)))
    app.row_usage_hits[path] = int(app.row_usage_hits.get(path, 0)) + 1
    app.row_usage_last_used_ts[path] = int(time.time())
    app.reconcile_usage_dirty = True
    app.reconcile_usage_due_at = time.time() + 2.0


def decay_row_usage(app: Any) -> None:
    if not app.row_usage_score:
        return
    for path in list(app.row_usage_score.keys()):
        value = float(app.row_usage_score.get(path, 0.0)) * 0.96
        if value < 0.2:
            app.row_usage_score.pop(path, None)
            app.row_usage_hits.pop(path, None)
            app.row_usage_last_used_ts.pop(path, None)
        else:
            app.row_usage_score[path] = value


def flush_reconcile_usage_if_due(
    app: Any,
    *,
    base_dir: Path,
    cache_save_reconcile_usage: Callable[[Path, dict[Path, float], dict[Path, int], dict[Path, int]], None],
) -> None:
    if not app.reconcile_usage_dirty:
        return
    if time.time() < app.reconcile_usage_due_at:
        return
    cache_save_reconcile_usage(
        base_dir,
        app.row_usage_score,
        app.row_usage_hits,
        app.row_usage_last_used_ts,
    )
    app.reconcile_usage_dirty = False


def pick_reconcile_candidates(
    app: Any,
    mode: str,
    batch_size: int,
    *,
    mode_active: str,
    now_ts: int,
    random_choices: Callable[..., list[ProjectRow]],
) -> list[ProjectRow]:
    rows = app.active_rows if mode == mode_active else app.archived_rows
    if not rows:
        return []
    stale_rows = [row for row in rows if row.stale]
    cfg = _reconcile_mode_cfg(app, mode)
    use_usage_score = bool(cfg.get("use_usage_score", True))
    usage_weight = max(0.0, float(cfg.get("usage_weight", 1.0)))
    stale_boost = bool(cfg.get("stale_boost", True))
    pool = stale_rows if stale_rows else list(rows)
    out: list[ProjectRow] = []
    limit = max(1, int(batch_size))
    while pool and len(out) < limit:
        weights: list[float] = []
        for row in pool:
            since_reconcile = (
                max(0, now_ts - row.last_reconciled_ts)
                if row.last_reconciled_ts > 0
                else max(0, now_ts - row.last_ts)
            )
            age_w = min(40.0, since_reconcile / 5.0)
            usage_w = (
                min(25.0, float(app.row_usage_score.get(row.path, 0.0))) * usage_weight
                if use_usage_score
                else 0.0
            )
            hit_w = (
                min(8.0, float(app.row_usage_hits.get(row.path, 0)) * 0.1) * usage_weight
                if use_usage_score
                else 0.0
            )
            used_ts = int(app.row_usage_last_used_ts.get(row.path, 0))
            recency_w = 0.0
            if used_ts > 0:
                since_used = max(0, now_ts - used_ts)
                recency_w = max(0.0, 6.0 - min(6.0, since_used / 60.0))
            stale_w = 6.0 if row.stale and stale_boost else 0.0
            dirty_w = 10.0 if row.dirty in {"~", "?", "*"} else 0.0
            weights.append(1.0 + age_w + usage_w + hit_w + recency_w + stale_w + dirty_w)
        picked = random_choices(pool, weights=weights, k=1)[0]
        out.append(picked)
        pool = [row for row in pool if row.path != picked.path]
    return out
