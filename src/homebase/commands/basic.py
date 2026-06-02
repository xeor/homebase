from __future__ import annotations

import json
import sys
from dataclasses import dataclass
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


_JSON_FIELDS: tuple[str, ...] = (
    "name", "branch", "dirty", "last", "src", "created", "description",
    "created_ts", "last_ts", "git_ts", "opened_ts",
    "is_fork", "is_tmp", "archived", "archived_ts",
    "wip", "suffix",
    "size_bytes",
    "worktree_of", "repo_dir",
    "tags", "properties",
)


def _row_to_json_dict(row: Any) -> dict[str, Any]:
    """Serialize a ``ProjectRow`` for ``b json``. ``Path`` / optional
    ``Path`` fields are stringified (or null) so the output is plain
    JSON; internal cache bookkeeping (haystack_lower, tags_lower,
    cache_age_s, …) is dropped — consumers don't need it and it's
    not stable across runs."""
    out: dict[str, Any] = {}
    path = getattr(row, "path", None)
    out["path"] = str(path) if path is not None else None
    restore = getattr(row, "restore_target", None)
    out["restore_target"] = str(restore) if restore is not None else None
    for field_name in _JSON_FIELDS:
        if not hasattr(row, field_name):
            continue
        value = getattr(row, field_name)
        if isinstance(value, (list, tuple)):
            out[field_name] = [str(v) for v in value]
        else:
            out[field_name] = value
    return out


@dataclass(frozen=True)
class _LsColumn:
    label: str
    width: int
    render: Callable[[Any], str]


def _ls_modified_value(row: Any, fmt_ymd: Callable[[int], str]) -> str:
    ts = getattr(row, "last_ts", 0) or 0
    if ts > 0:
        return fmt_ymd(ts)
    return str(getattr(row, "last", "") or "-")


def _ls_branch_value(row: Any) -> str:
    branch = getattr(row, "branch", "") or "-"
    suffix = "*" if str(getattr(row, "dirty", "")).strip() else ""
    return f"{branch}{suffix}"


def _ls_columns(
    *,
    fmt_ymd: Callable[[int], str],
    fmt_size_human: Callable[[int], str],
    flags: dict[str, bool],
) -> list[_LsColumn]:
    """Build the active column list. The spec table fixes column
    *order* (independent of CLI flag order). The *last* column is
    rendered without truncation so a free-form tail field (TAGS,
    PROPS, DESCRIPTION, PATH) stays complete."""
    def ymd_or_dash(ts: int) -> str:
        return fmt_ymd(ts) if ts > 0 else "-"

    specs: list[tuple[str | None, _LsColumn]] = [
        (None, _LsColumn("NAME", 28, lambda r: str(r.name))),
        ("with_created", _LsColumn(
            "CREATED", 12,
            lambda r: ymd_or_dash(int(getattr(r, "created_ts", 0) or 0)),
        )),
        (None, _LsColumn("MODIFIED", 12, lambda r: _ls_modified_value(r, fmt_ymd))),
        ("with_active", _LsColumn(
            "ACTIVE", 12,
            lambda r: ymd_or_dash(int(getattr(r, "opened_ts", 0) or 0)),
        )),
        ("with_git", _LsColumn("BRANCH", 18, _ls_branch_value)),
        ("with_wip", _LsColumn(
            "WIP", 5,
            lambda r: "wip" if bool(getattr(r, "wip", False)) else "-",
        )),
        (None, _LsColumn(
            "SIZE", 10,
            lambda r: fmt_size_human(int(getattr(r, "size_bytes", 0) or 0)),
        )),
        ("with_worktree_of", _LsColumn(
            "WORKTREE-OF", 16,
            lambda r: str(getattr(r, "worktree_of", "") or "-"),
        )),
        ("with_src", _LsColumn(
            "SRC", 24, lambda r: str(getattr(r, "src", "") or "-"),
        )),
        ("with_path", _LsColumn(
            "PATH", 40, lambda r: str(getattr(r, "path", "") or "-"),
        )),
        ("with_description", _LsColumn(
            "DESCRIPTION", 40,
            lambda r: str(getattr(r, "description", "") or "-"),
        )),
        (None, _LsColumn(
            "TAGS", 24,
            lambda r: ",".join(getattr(r, "tags", []) or []) or "-",
        )),
        ("with_props", _LsColumn(
            "PROPS", 24,
            lambda r: ",".join(getattr(r, "properties", []) or []) or "-",
        )),
    ]
    return [col for flag, col in specs if flag is None or flags.get(flag, False)]


def _print_ls_table(cols: list[_LsColumn], rows: list[Any]) -> None:
    """Width-allocated, no-ANSI rendering. Header + one row per
    project. The last column is never truncated so piped output keeps
    the tail field whole."""
    last_idx = len(cols) - 1
    header_parts = [
        col.label if i == last_idx else f"{col.label:<{col.width}}"
        for i, col in enumerate(cols)
    ]
    print("  ".join(header_parts))
    for row in rows:
        parts: list[str] = []
        for i, col in enumerate(cols):
            text = str(col.render(row))
            if i == last_idx:
                parts.append(text)
                continue
            if len(text) > col.width:
                text = text[: max(1, col.width - 1)] + "…"
            parts.append(f"{text:<{col.width}}")
        print("  ".join(parts))


def _apply_filter_or_error(
    rows: list[Any],
    *,
    filter_expr: str,
    compile_filter_expr: Callable[[str], tuple[Callable[[Any], bool], str | None]],
    error_prefix: str,
) -> tuple[list[Any] | None, int]:
    if not filter_expr.strip():
        return rows, 0
    pred, err = compile_filter_expr(filter_expr)
    if err:
        print(f"{error_prefix}: invalid filter: {err}", file=sys.stderr)
        return None, 2
    return [r for r in rows if pred(r)], 0


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
    with_created: bool = False,
    with_active: bool = False,
    with_wip: bool = False,
    with_worktree_of: bool = False,
    with_src: bool = False,
    with_path: bool = False,
    with_description: bool = False,
    with_props: bool = False,
) -> int:
    """Fast, cache-backed `ls` over the workspace.

    Defaults: print only project names, one per line. With ``-l`` /
    ``long_format``, render a few extra columns (last modified, size,
    tags). All cheap fields come straight from the SQLite cache
    (``cache_load_rows``) so the no-flag path doesn't probe git, the
    filesystem, or run any per-row work.

    Opt-in slower data sources go behind explicit flags:
      ``with_git`` — refresh + show branch / dirty status.

    Additional ``with_*`` flags append extra columns
    (CREATED / ACTIVE / WIP / WORKTREE-OF / SRC / PATH / DESCRIPTION /
    PROPS). Any of these also implicitly switches on long format so
    the user can opt into a single extra column without having to add
    ``-l``.

    The ``filter_expr`` accepts the same syntax as the TUI's QUERY
    input (compiled via ``compile_filter_expr``)."""
    active, archived, _ts = cache_load_rows(base_dir)
    source = archived if show_archived else active

    rows, rc = _apply_filter_or_error(
        list(source),
        filter_expr=filter_expr,
        compile_filter_expr=compile_filter_expr,
        error_prefix="b ls",
    )
    if rows is None:
        return rc

    rows = sorted(rows, key=lambda r: str(getattr(r, "name", "")).lower())

    if with_git and enrich_git is not None:
        enrich_git(rows)

    flags = {
        "with_created": with_created,
        "with_active": with_active,
        "with_git": with_git,
        "with_wip": with_wip,
        "with_worktree_of": with_worktree_of,
        "with_src": with_src,
        "with_path": with_path,
        "with_description": with_description,
        "with_props": with_props,
    }
    extras_on = any(v for k, v in flags.items() if k != "with_git")
    if not long_format and not with_git and not extras_on:
        for row in rows:
            print(row.name)
        return 0

    cols = _ls_columns(fmt_ymd=fmt_ymd, fmt_size_human=fmt_size_human, flags=flags)
    _print_ls_table(cols, rows)
    return 0


def cmd_json(
    base_dir: Path,
    *,
    cache_load_rows: Callable[[Path], tuple[list[Any], list[Any], int]],
    compile_filter_expr: Callable[[str], tuple[Callable[[Any], bool], str | None]],
    filter_expr: str = "",
    include_archived: bool = False,
    archived_only: bool = False,
) -> int:
    """Cache-backed JSON dump of project rows. Counterpart to
    ``cmd_ls`` for machine consumers — no column flags, every field
    is always present.

    Selection rules:
      * default → active rows only.
      * ``--archived`` → active + archived rows, with
        ``is_archived: true`` added to the archived entries so
        consumers can tell them apart.
      * ``--archived-only`` → archived rows only (no
        ``is_archived`` field; everything in the list is archived).

    Filter expression uses the same syntax as ``b ls`` / the TUI's
    QUERY input."""
    active, archived, _ts = cache_load_rows(base_dir)
    if archived_only:
        rows: list[Any] = list(archived)
        mark_archived = False
    elif include_archived:
        rows = list(active) + list(archived)
        mark_archived = True
    else:
        rows = list(active)
        mark_archived = False
    archived_paths: set[Any] = (
        {getattr(r, "path", None) for r in archived} if mark_archived else set()
    )

    filtered, rc = _apply_filter_or_error(
        rows,
        filter_expr=filter_expr,
        compile_filter_expr=compile_filter_expr,
        error_prefix="b json",
    )
    if filtered is None:
        return rc
    rows = sorted(filtered, key=lambda r: str(getattr(r, "name", "")).lower())

    payload: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_json_dict(row)
        if mark_archived and getattr(row, "path", None) in archived_paths:
            item["is_archived"] = True
        payload.append(item)
    print(json.dumps(payload, indent=2))
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
