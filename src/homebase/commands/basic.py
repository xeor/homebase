from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.text import Text
from rich.tree import Tree

from ..config.tag_rules import (
    direct_parents,
    is_group_only,
    iter_rules,
    resolve_for_display,
    roots,
)


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


def _expand_known_names(
    workspace_tags: set[str], base_dir: Path,
) -> set[str]:
    """Every name that should appear in the tree:

    * Every tag used by any project.
    * Every name spelled out in a rule's ``tags:`` matcher (so users
      see groups they configured even when no project uses them yet).
    * Every name referenced as a ``parents:`` value.
    * The transitive ancestors of all of the above.

    Regex-only rules don't enumerate their possible matches — those
    names appear only when a workspace tag matches them.
    """
    names: set[str] = set(workspace_tags)
    names.update(roots(base_dir))
    for rule in iter_rules(base_dir):
        names.update(rule.explicit_tags)
    queue = list(names)
    while queue:
        node = queue.pop()
        for parent in direct_parents(node, base_dir):
            if parent not in names:
                names.add(parent)
                queue.append(parent)
    return names


def _build_label(
    name: str,
    *,
    base_dir: Path,
    workspace_counts: dict[str, int],
) -> Text:
    """One label row: rendered tag, plain name (if different),
    project count, parents, and the matching rule's raw spec."""
    resolved = resolve_for_display(name, base_dir)
    line = Text()
    line.append(resolved.display, style=resolved.style_spec)
    if resolved.display != name:
        line.append("  ")
        line.append(f"({name})", style="dim")
    count = workspace_counts.get(name, 0)
    if count > 0:
        line.append("  ")
        line.append(f"× {count}", style="bold green")
    else:
        line.append("  ")
        line.append("× 0", style="dim")
    parents = direct_parents(name, base_dir)
    if parents:
        line.append("  ")
        line.append(f"⊂ {', '.join(parents)}", style="cyan")
    if resolved.matched_rule:
        line.append("  ")
        line.append(f"[{resolved.matched_rule}]", style="dim yellow")
    else:
        line.append("  ")
        line.append("(no rule)", style="dim")
    if is_group_only(name, base_dir):
        line.append("  ")
        line.append("(group-only)", style="dim magenta")
    return line


def cmd_tags_ls(
    base_dir: Path,
    *,
    load_rows: Callable[[Path], tuple[list[Any], list[Any]]],
) -> int:
    """List every known tag in its configured hierarchy.

    Sources for the node set:
      * every tag in use by any project (active + archived);
      * every name declared as a ``parents:`` value in any rule;
      * every transitive ancestor of those.

    Multi-parent tags appear once under each parent — the listing is
    a true tree, the underlying data is a DAG.
    """
    active, archived = load_rows(base_dir)
    counts: dict[str, int] = {}
    for row in list(active) + list(archived):
        for tag in row.tags:
            counts[tag] = counts.get(tag, 0) + 1

    workspace_tags = set(counts.keys())
    all_names = _expand_known_names(workspace_tags, base_dir)

    # Build child → parent edges as a children-of map.
    children_of: dict[str, list[str]] = {}
    for name in all_names:
        for parent in direct_parents(name, base_dir):
            children_of.setdefault(parent, []).append(name)
    for parent in children_of:
        children_of[parent].sort()

    # Top-level entries: names with no direct parents. This includes
    # declared group roots (e.g. ``meta``) and lonely workspace tags
    # with no rule.
    top_level = sorted(
        name for name in all_names
        if not direct_parents(name, base_dir)
    )

    console = Console()
    if not all_names:
        console.print("[dim]no tags configured or in use.[/]")
        return 0

    header = Text()
    header.append("tag tree", style="bold")
    header.append(
        f"  ({len(all_names)} name(s), {len(workspace_tags)} in use, "
        f"{sum(counts.values())} project link(s))",
        style="dim",
    )
    tree = Tree(header)
    visited: set[str] = set()

    def _attach(branch: Tree, name: str, path: tuple[str, ...]) -> None:
        # Cycle guard — a misconfigured DAG with a loop must terminate.
        if name in path:
            note = Text()
            note.append(name, style="dim")
            note.append("  (cycle — already visited)", style="dim red")
            branch.add(note)
            return
        visited.add(name)
        label = _build_label(name, base_dir=base_dir, workspace_counts=counts)
        node = branch.add(label)
        for child in children_of.get(name, []):
            _attach(node, child, path + (name,))

    for root_name in top_level:
        _attach(tree, root_name, ())

    # Anything not reached lives inside a cycle (or a strongly-
    # connected component with no entry from a root). List those at
    # the end so the user can still see them.
    stranded = sorted(all_names - visited)
    if stranded:
        cycle_branch = tree.add(
            Text("(unreached — cyclic groups)", style="dim red")
        )
        for name in stranded:
            label = _build_label(name, base_dir=base_dir, workspace_counts=counts)
            cycle_branch.add(label)

    console.print(tree)
    return 0
