from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


def cmd_tags_sync(
    base_dir: Path,
    *,
    sync_tag_symlinks_detailed: Callable[[Path, bool, bool], tuple[str | None, list[str]]],
    verbose: bool,
    debug: bool,
) -> int:
    err, lines = sync_tag_symlinks_detailed(base_dir, verbose, debug)
    if verbose:
        for line in lines:
            print(line)
    if err:
        print(f"tag sync failed: {err}", file=sys.stderr)
        return 1
    if not verbose:
        print("tag sync ok")
    return 0


def cmd_ls(
    base_dir: Path,
    *,
    cache_load_rows: Callable[[Path], tuple[list[Any], list[Any], int]],
    compile_filter_expr: Callable[[str], tuple[Callable[[Any], bool], str | None]],
    fmt_ymd: Callable[[int], str],
    fmt_size_human: Callable[[int], str],
    enrich_git: Callable[[list[Any]], None] | None = None,
    filter_expr: str = "",
    long_format: bool = False,
    with_git: bool = False,
    show_archived: bool = False,
) -> int:
    """Fast, cache-backed `ls` over the workspace.

    Defaults: print only project names, one per line. With ``-l`` /
    ``long_format``, render a few extra columns (last modified, size,
    tags). All cheap fields come straight from the SQLite cache
    (``cache_load_rows``) so the no-flag path doesn't probe git, the
    filesystem, or run any per-row work.

    Opt-in slower data sources go behind explicit flags:
      ``with_git`` — refresh + show branch / dirty status.

    The ``filter_expr`` accepts the same syntax as the TUI's QUERY
    input (compiled via ``compile_filter_expr``)."""
    active, archived, _ts = cache_load_rows(base_dir)
    rows = archived if show_archived else active

    if filter_expr.strip():
        pred, err = compile_filter_expr(filter_expr)
        if err:
            print(f"b ls: invalid filter: {err}", file=sys.stderr)
            return 2
        rows = [r for r in rows if pred(r)]

    rows = sorted(rows, key=lambda r: str(getattr(r, "name", "")).lower())

    if with_git and enrich_git is not None:
        enrich_git(rows)

    if not long_format and not with_git:
        for row in rows:
            print(row.name)
        return 0

    # Long format. Width-allocated columns; truncated values keep the
    # output grep-friendly when piped. No ANSI — pipe-clean by design.
    cols: list[tuple[str, int, Callable[[Any], str]]] = [
        ("NAME", 28, lambda r: str(r.name)),
        (
            "MODIFIED",
            12,
            lambda r: fmt_ymd(getattr(r, "last_ts", 0) or 0)
            if (getattr(r, "last_ts", 0) or 0) > 0
            else str(getattr(r, "last", "") or "-"),
        ),
    ]
    if with_git:
        cols.append((
            "BRANCH",
            18,
            lambda r: (
                f"{getattr(r, 'branch', '') or '-'}"
                + ("*" if str(getattr(r, "dirty", "")).strip() else "")
            ),
        ))
    cols.append((
        "SIZE",
        10,
        lambda r: fmt_size_human(int(getattr(r, "size_bytes", 0) or 0)),
    ))
    cols.append((
        "TAGS",
        24,
        lambda r: ",".join(getattr(r, "tags", []) or []) or "-",
    ))

    header = "  ".join(f"{label:<{width}}" for label, width, _ in cols)
    print(header)
    for row in rows:
        parts: list[str] = []
        for _label, width, render in cols:
            text = str(render(row))
            if len(text) > width:
                text = text[: max(1, width - 1)] + "…"
            parts.append(f"{text:<{width}}")
        print("  ".join(parts))
    return 0


def cmd_recent(
    base_dir: Path,
    *,
    collect_projects: Callable[[Path], list[Any]],
    sort_rows: Callable[[list[Any], str], list[Any]],
    fmt_ymd: Callable[[int], str],
) -> int:
    rows = sort_rows(collect_projects(base_dir), "git")
    for row in rows[:20]:
        stamp = fmt_ymd(row.git_ts) if row.git_ts > 0 else row.last
        print(f"{stamp}  {row.name}")
    return 0


def cmd_cd(
    base_dir: Path,
    name: str,
    *,
    archive_dir_name: str,
    open_shell_in_dir: Callable[[Path], int],
) -> int:
    """Spawn a shell in ``<base>/<name>``. Works from anywhere, so the
    user can jump to any project they know the name of without first
    cd-ing into base. Tab completion narrows ``<name>`` to active
    (non-archived) projects.

    Empty ``<name>`` is treated as "drop me into base itself"."""
    target_name = (name or "").strip()
    if not target_name:
        return open_shell_in_dir(base_dir)
    candidate = (base_dir / target_name).resolve()
    base_resolved = base_dir.resolve()
    try:
        rel = candidate.relative_to(base_resolved)
    except ValueError:
        print(f"refusing to cd outside base: {candidate}", file=sys.stderr)
        return 2
    parts = rel.parts
    if not parts:
        # User asked for base itself via something like ``b cd .``.
        return open_shell_in_dir(candidate)
    first = parts[0]
    # ``_archive``, ``_tags``, and any other underscore / dot dir
    # under base is bookkeeping, not a project. Block the jump so
    # ``b cd _archive`` doesn't silently land in the archive root.
    if first.startswith("_") or first.startswith("."):
        print(
            f"refusing to cd into a reserved/hidden dir: {first}",
            file=sys.stderr,
        )
        return 2
    if first == archive_dir_name:
        print(
            f"refusing to cd into the archive (use `b archive ls`): {first}",
            file=sys.stderr,
        )
        return 2
    if not candidate.is_dir():
        print(f"no such project: {target_name}", file=sys.stderr)
        return 2
    return open_shell_in_dir(candidate)
