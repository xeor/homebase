from __future__ import annotations

from pathlib import Path


def reconcile_queue_push(
    queue: list[tuple[int, str, str, list[Path]]],
    mode: str,
    reason: str,
    paths: list[Path],
    priority: int,
    *,
    limit: int = 40,
) -> list[tuple[int, str, str, list[Path]]]:
    if not paths:
        return list(queue)
    out = list(queue)
    out.append((priority, mode, reason, list(paths)))
    out.sort(key=lambda item: (-item[0], item[2]))
    if len(out) > limit:
        out = out[:limit]
    return out


def reconcile_queue_pop_next(
    queue: list[tuple[int, str, str, list[Path]]],
    *,
    worker_running: bool,
) -> tuple[list[tuple[int, str, str, list[Path]]], tuple[int, str, str, list[Path]] | None]:
    out = list(queue)
    if worker_running or not out:
        return out, None
    item = out.pop(0)
    return out, item
