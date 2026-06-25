from __future__ import annotations

import fnmatch
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ...core.constants import (
    COLOR_ACCENT_HEX,
    COLOR_ARCHIVE_HEX,
    COLOR_DYNAMIC_ENV_HEX,
    COLOR_DYNAMIC_FILE_HEX,
    COLOR_DYNAMIC_STATE_HEX,
    COLOR_ERROR_HEX,
    COLOR_INFO_HEX,
    COLOR_SUCCESS_HEX,
    COLOR_WARN_HEX,
)
from ...core.models import ProjectRow
from ...core.version import get_commit, get_version
from ...metadata.api import load_base_worktree as _load_worktree_block
from ..actions import template as action_template


def global_info_lines(app: Any) -> list[str]:
    rows = app._current_rows()
    selected = app._selected_row()
    query_text = str(getattr(app, "query", "")).strip()
    selected_text = selected.name if selected is not None else "-"
    open_panes_total = sum(int(n) for n in app.open_pane_count_by_project.values())
    return [
        f"version: {get_version()} ({get_commit()})",
        f"base dir: {app._esc(app.base_dir)}",
        f"view: {app.view_mode}",
        f"sort: {app.sort_mode}",
        f"query: {app._esc(query_text) if query_text else '-'}",
        f"rows visible: {len(rows)}",
        f"focused: {app._esc(selected_text)}",
        f"multi-selected: {len(app.multi_selected)}",
        f"open panes: {open_panes_total}",
    ]


def property_count_map(
    app: Any,
    *,
    all_property_defs: Callable[[], list[Any]],
) -> dict[str, int]:
    rows = app._current_rows()
    out = {p.key: 0 for p in all_property_defs()}
    for row in rows:
        for key in row.properties:
            if key in out:
                out[key] += 1
    return out


def tag_count_map(app: Any, *, limit: int = 12) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in app._current_rows():
        for tag in row.tags:
            counts[tag] = counts.get(tag, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:limit]


def cheat_columns(
    app: Any,
    *,
    all_property_defs: Callable[[], list[Any]],
) -> tuple[str, str]:
    left: list[str] = []
    left.append("- ctrl+n           create new project")
    left.append("- enter            open selected row")
    left.append("- ctrl+s           sort picker")
    left.append("- ctrl+f           saved filters (multi OR, save current)")
    left.append("- ctrl+c           reset view (clear query, jump top)")
    left.append("- ctrl+l           cycle side tabs")
    left.append("- ctrl+k           cycle side tabs (reverse)")
    left.append("- ctrl+d           switch active/archive view")
    left.append("- ctrl+w           toggle wip on focused project")
    left.append("- alt+1..9         open wip project by index")
    left.append("- ctrl+a           actions picker (tags/suffix inside)")
    left.append("- ctrl+o           toggle select mode")
    left.append("- ctrl+q           quit")
    left.append("")
    left.append("- Targets are selected rows, or focused row if nothing is selected")
    left.append("- In select mode: space=toggle, a=all, c=clear, u=untagged")
    left.append("")
    left.append("- row prefix legend:")
    left.append("  char1: '*' selected, ' ' not selected")
    left.append("  char2: '!' stale, '~' refresh running, '?' unknown, ' ' healthy")
    left.append("  char3: '1'..'9' open pane count, ' ' none")
    left.append("  char4: always space")
    left.append("- examples: '    ' normal, '*   ' selected, ' !  ' stale")
    left.append("- examples: '*!2 ' selected+stale+2 panes, ' ~1 ' refresh+1 pane")
    left.append("")

    left.append("- keep   : no change for that tag on each target")
    left.append("- add    : add tag to all targets")
    left.append("- remove : remove tag from all targets")
    left.append("- add tags: creates new tag entries and marks them as add")
    left.append("- designed to avoid accidental tag loss in multi-select")
    left.append("")
    left.append("- restore conflicts offer skip or restore-to-other-location")
    left.append("- bulk actions continue on failures and log per-item result")
    left.append("- properties are auto-detected from project context")
    left.append("- dynamic properties are defined in .homebase/config.yaml")
    left.append("- metadata issues are explained in Selected -> Overview")
    left.append("")
    left.append("- filter syntax (combine with AND/OR and parentheses):")
    left.append("  #tag                 exact tag")
    left.append("  #lang*               tag glob (* ? [..] supported)")
    left.append("  ##group              tag tree (parent + descendants)")
    left.append("  ##cod*               tag-tree glob")
    left.append("  !prop                property key/label/token")
    left.append("  !*git*               property glob")
    left.append("  .tmp                 suffix")
    left.append("  .tm*                 suffix glob")
    left.append("  @name                saved filter by name")
    left.append("- negation: prefix any term with '-' to exclude")
    left.append("  -#data               exclude rows tagged data")
    left.append("  -!readme             exclude rows with the readme property")
    left.append("  -.tmp                exclude rows with .tmp suffix")
    left.append("  -##cod*              exclude any tag in the 'cod*' tree")
    left.append("  -@stale              exclude rows matching the saved 'stale' filter")
    left.append("- column-specific syntax (:key matches a table column id):")
    left.append("  :tags=0              rows with no tags")
    left.append("  :tags>4              rows with more than 4 tags")
    left.append("  :properties=0        rows with no properties")
    left.append("  :properties>0        rows with at least one property")
    left.append("  :created=@-3y        created within last 3 years")
    left.append("  :created=@-2y100d    relative spans can be combined")
    left.append("  :created=@-2y20m     m=months, d=days (always summed)")
    left.append("  :modified=@-7d       modified within last 7 days")
    left.append("  :active=@-30d        last opened within last 30 days")
    left.append("  :created=2025        created in year 2025")
    left.append("  :created=2025-01     created in Jan 2025")
    left.append("  :created=2025-01-05  created on exact date")
    left.append("  :created<=2025       created in/before year 2025")
    left.append("- operators for :key: = != < <= > >=")
    left.append("")
    left.append("- color legend (meaning-bearing colors):")
    left.append(
        f"  [{COLOR_INFO_HEX}]info blue[/] ({COLOR_INFO_HEX}): informational status and neutral highlights"
    )
    left.append(
        f"  [{COLOR_WARN_HEX}]warning yellow[/] ({COLOR_WARN_HEX}): caution, degraded state, retry-needed signals"
    )
    left.append(
        f"  [{COLOR_ERROR_HEX}]error red[/] ({COLOR_ERROR_HEX}): failures, blocking errors, invalid state"
    )
    left.append(
        f"  [{COLOR_SUCCESS_HEX}]success green[/] ({COLOR_SUCCESS_HEX}): successful operations and healthy outcomes"
    )
    left.append(
        f"  [{COLOR_ACCENT_HEX}]accent cyan[/] ({COLOR_ACCENT_HEX}): interactive emphasis (links, selectable custom actions)"
    )
    left.append(
        f"  [{COLOR_ARCHIVE_HEX}]archive purple[/] ({COLOR_ARCHIVE_HEX}): archive-mode context, archive-specific state"
    )
    left.append(
        f"  [{COLOR_DYNAMIC_ENV_HEX}]dynamic env orange[/] ({COLOR_DYNAMIC_ENV_HEX}): env/tmux-driven dynamic properties"
    )
    left.append(
        f"  [{COLOR_DYNAMIC_FILE_HEX}]dynamic file blue[/] ({COLOR_DYNAMIC_FILE_HEX}): file-probe dynamic properties"
    )
    left.append(
        f"  [{COLOR_DYNAMIC_STATE_HEX}]dynamic state violet[/] ({COLOR_DYNAMIC_STATE_HEX}): state/health dynamic properties"
    )
    left.append("")
    left.append("- date column styles (table.columns_style.date):")
    date_styles = getattr(app, "table_date_color_ranges", {})
    for view in ("all", "active", "archive"):
        view_rules = date_styles.get(view, {}) if isinstance(date_styles, dict) else {}
        if not isinstance(view_rules, dict) or not view_rules:
            continue
        for col in ("created", "modified", "active", "archived_at"):
            rule = view_rules.get(col, {})
            if not isinstance(rule, dict):
                continue
            stops = rule.get("stops", [])
            if not isinstance(stops, list) or not stops:
                continue
            parts: list[str] = []
            for stop in stops:
                if not isinstance(stop, dict):
                    continue
                try:
                    days = float(stop.get("days", 0.0))
                except (TypeError, ValueError):
                    continue
                color = str(stop.get("color", "")).strip()
                if not color:
                    continue
                day_text = str(int(days)) if days.is_integer() else f"{days:g}"
                parts.append(f"[{color}]{day_text}[/]")
            if parts:
                left.append(f"  {view}.{col}: {' > '.join(parts)}")

    return "\n".join(left), ""


def preview_entries(path: Path, *, limit: int = 8) -> list[str]:
    if not path.exists() or not path.is_dir():
        return ["[dim](no directory preview)[/]"]
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except (OSError, ValueError) as exc:
        return [f"[red](preview failed: {exc})[/]"]

    lines: list[str] = []
    for p in entries[:limit]:
        name = p.name + ("/" if p.is_dir() else "")
        lines.append(f"[dim]-[/] {name}")
    if len(entries) > limit:
        lines.append(f"[dim]... +{len(entries) - limit} more[/]")
    if not lines:
        lines.append("[dim](empty)[/]")
    return lines


def run_cmd(cwd: Path, *cmd: str) -> tuple[str, str | None]:
    try:
        process = subprocess.run(
            list(cmd),
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        return "", str(exc)
    out = (process.stdout or "").strip()
    if process.returncode != 0:
        err = (process.stderr or "").strip() or f"exit={process.returncode}"
        return out, err
    return out, None


_GIT_MAX_BRANCHES = 5
_GIT_MAX_STATUS = 40
_GIT_MAX_COMMITS = 10
_GIT_MAX_REMOTES = 8


def _git_header_lines(app: Any, row: ProjectRow, repo_path: Path) -> list[str]:
    out: list[str] = [
        f"[cyan]repo path[/]: [dim]{app._esc(repo_path)}[/]"
        f"{'  [dim](.git at project root)[/]' if row.repo_dir == '.' else ''}"
    ]
    if row.worktree_of:
        out.append(
            f"[cyan]worktree of[/]: [magenta]{app._esc(row.worktree_of)}[/] "
            f"[dim](this is a `git worktree` of the root project)[/]"
        )
        wt_block = _load_worktree_block(row.path)
        if wt_block is not None:
            parent_repo = str(wt_block.get("parent_path", "")).strip()
            if parent_repo:
                out.append(
                    f"[cyan]parent repo[/]: [dim]{app._esc(parent_repo)}[/]"
                )
    out.append(
        f"[cyan]branch[/]: [green]{app._esc(row.branch)}[/]"
        f"{'[yellow]*[/]' if row.dirty else ''}"
    )
    return out


def _git_tracking_lines(app: Any, repo_path: Path) -> list[str]:
    upstream, _err_upstream = run_cmd(
        repo_path,
        "git",
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )
    if not upstream:
        return ["[cyan]tracking[/]: [dim](none)[/]"]
    ahead_behind, _err_ab = run_cmd(
        repo_path,
        "git",
        "rev-list",
        "--left-right",
        "--count",
        "@{upstream}...HEAD",
    )
    if ahead_behind and "\t" in ahead_behind:
        behind, ahead = ahead_behind.split("\t", 1)
        return [
            f"[cyan]tracking[/]: {app._esc(upstream)} "
            f"[dim](ahead {app._esc(ahead.strip())}, "
            f"behind {app._esc(behind.strip())})[/]"
        ]
    return [f"[cyan]tracking[/]: {app._esc(upstream)}"]


def _git_last_commit_lines(app: Any, repo_path: Path) -> list[str]:
    last_commit, err_last = run_cmd(
        repo_path,
        "git",
        "log",
        "-1",
        "--pretty=%h %ad %s",
        "--date=iso-strict",
    )
    out = [f"[cyan]last commit[/]: {app._esc(last_commit or '-')}"]
    if err_last:
        out.append(f"[red]git log error:[/] {app._esc(err_last)}")
    return out


def _git_status_lines(app: Any, repo_path: Path) -> list[str]:
    status, err_status = run_cmd(repo_path, "git", "status", "--short")
    staged_stat, _err_staged_stat = run_cmd(
        repo_path, "git", "diff", "--cached", "--shortstat"
    )
    unstaged_stat, _err_unstaged_stat = run_cmd(
        repo_path, "git", "diff", "--shortstat"
    )
    entries = status.splitlines() if status else []
    untracked_count = sum(1 for ln in entries if ln.startswith("??"))
    staged_count = sum(
        1 for ln in entries if len(ln) >= 2 and ln[0] not in {" ", "?"}
    )
    unstaged_count = sum(
        1 for ln in entries if len(ln) >= 2 and ln[1] not in {" ", "?"}
    )
    out: list[str] = [
        f"[cyan]status summary[/]: staged={staged_count} "
        f"unstaged={unstaged_count} untracked={untracked_count}"
    ]
    if staged_stat:
        out.append(f"[cyan]staged stat[/]: {app._esc(staged_stat)}")
    if unstaged_stat:
        out.append(f"[cyan]unstaged stat[/]: {app._esc(unstaged_stat)}")
    out.append(f"[cyan]status entries[/]: [dim](max {_GIT_MAX_STATUS})[/]")
    if status:
        out.extend(app._esc(ln) for ln in entries[:_GIT_MAX_STATUS])
        if len(entries) > _GIT_MAX_STATUS:
            out.append(f"[dim]... +{len(entries) - _GIT_MAX_STATUS} more[/]")
    else:
        out.append("[dim]clean working tree[/]")
    if err_status:
        out.append(f"[red]git status error:[/] {app._esc(err_status)}")
    return out


def _git_branch_lines(app: Any, repo_path: Path) -> list[str]:
    branches, err_branches = run_cmd(
        repo_path,
        "git",
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(if)%(HEAD)%(then)* %(else)  %(end)%(refname:short)  %(committerdate:relative)",
        "refs/heads",
    )
    out = [f"[cyan]branches[/]: [dim](max {_GIT_MAX_BRANCHES})[/]"]
    if branches:
        branch_lines = branches.splitlines()
        out.extend(app._esc(ln) for ln in branch_lines[:_GIT_MAX_BRANCHES])
        if len(branch_lines) > _GIT_MAX_BRANCHES:
            out.append(f"[dim]... +{len(branch_lines) - _GIT_MAX_BRANCHES} more[/]")
    else:
        out.append("[dim]-[/]")
    if err_branches:
        out.append(f"[red]branches error:[/] {app._esc(err_branches)}")
    return out


def _git_remote_lines(app: Any, repo_path: Path) -> list[str]:
    remotes, err_remotes = run_cmd(repo_path, "git", "remote", "-v")
    out = [f"[cyan]remotes[/]: [dim](max {_GIT_MAX_REMOTES})[/]"]
    if remotes:
        uniq: list[str] = []
        seen: set[str] = set()
        for ln in remotes.splitlines():
            key = ln.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(key)
        out.extend(app._esc(ln) for ln in uniq[:_GIT_MAX_REMOTES])
        if len(uniq) > _GIT_MAX_REMOTES:
            out.append(f"[dim]... +{len(uniq) - _GIT_MAX_REMOTES} more[/]")
    else:
        out.append("[dim]-[/]")
    if err_remotes:
        out.append(f"[red]remotes error:[/] {app._esc(err_remotes)}")
    return out


def _git_recent_commits_lines(app: Any, repo_path: Path) -> list[str]:
    recent, err_recent = run_cmd(
        repo_path,
        "git",
        "log",
        f"-{_GIT_MAX_COMMITS}",
        "--pretty=%h %ad %s",
        "--date=iso-strict",
    )
    out = [f"[cyan]recent commits[/]: [dim](max {_GIT_MAX_COMMITS})[/]"]
    if recent:
        commits = recent.splitlines()
        out.extend(app._esc(ln) for ln in commits[:_GIT_MAX_COMMITS])
    else:
        out.append("[dim]-[/]")
    if err_recent:
        out.append(f"[red]git recent error:[/] {app._esc(err_recent)}")
    return out


def build_side_git_text(app: Any, row: ProjectRow) -> str:
    if row.packed:
        return "[dim]packed archive: git details unavailable until unpacked[/]"
    if not row.repo_dir:
        return "[dim]not a git repository (set repo_dir in .base.yaml, or run `b fix --repo-dir`)[/]"
    repo_path = row.path / row.repo_dir
    if not (repo_path / ".git").exists():
        return "[dim]not a git repository[/]"
    lines: list[str] = []
    lines.extend(_git_header_lines(app, row, repo_path))
    lines.extend(_git_tracking_lines(app, repo_path))
    lines.extend(_git_last_commit_lines(app, repo_path))
    lines.extend(_git_status_lines(app, repo_path))
    lines.extend(_git_branch_lines(app, repo_path))
    lines.extend(_git_remote_lines(app, repo_path))
    lines.extend(_git_recent_commits_lines(app, repo_path))
    return "\n".join(lines)


def build_side_project_events_text(
    app: Any,
    row: ProjectRow,
    *,
    load_base_data: Callable[[Path], object],
    fmt_age_short_from_iso: Callable[[str], str],
) -> str:
    data = load_base_data(row.path)
    log_val = data.get("log", {}) if isinstance(data, dict) else {}
    events = log_val.get("events", []) if isinstance(log_val, dict) else []
    if not isinstance(events, list) or not events:
        return "[dim]no project events[/]"

    items: list[dict[str, object]] = [ev for ev in events if isinstance(ev, dict)]
    if not items:
        return "[dim]no project events[/]"

    lines: list[str] = []
    total = len(items)
    lines.append(f"[cyan]events[/]: showing {min(50, total)} of {total} (newest first)")
    for ev in reversed(items[-50:]):
        ts_raw = str(ev.get("_ts", "-")).strip() or "-"
        ts = app._esc(ts_raw)
        rel = fmt_age_short_from_iso(ts_raw)
        name = app._esc(ev.get("_event", "event"))
        lines.append(f"[dim]{ts} ({rel})[/] [bold cyan]{name}[/]")

        keys = [k for k in sorted(ev.keys()) if k not in {"_ts", "_event"}]
        if not keys:
            lines.append("  [dim](no details)[/]")
        else:
            for key in keys:
                value = app._esc(ev.get(key, ""))
                lines.append(f"  [magenta]{app._esc(key)}[/]: {value}")
        lines.append("")
    return "\n".join(lines)


_FILES_MAX_DIRS = 30
_FILES_MAX_FILES = 50


def _packed_files_text(
    app: Any, row: ProjectRow, fmt_size_human: Callable[[int], str]
) -> str:
    return "\n".join(
        [
            "[cyan]packed[/]: yes (.tgz)",
            f"[cyan]file[/]: {app._esc(row.path.name)}",
            f"[cyan]size[/]: {fmt_size_human(row.size_bytes)} "
            f"[dim]({row.size_bytes} bytes, cached)[/]",
            "[dim]unpack to inspect files[/]",
        ]
    )


def _path_excluded(
    rel_posix: str, name: str, is_dir: bool, patterns: list[str]
) -> bool:
    rel = rel_posix.lstrip("./")
    for pat in patterns:
        p = pat.strip()
        if not p:
            continue
        if p.endswith("/**"):
            base = p[:-3].rstrip("/")
            if base and (rel == base or rel.startswith(base + "/")):
                return True
            continue
        is_plain = "/" not in p and not any(ch in p for ch in "*?[]")
        if is_plain:
            if name == p:
                return True
            if rel == p or f"/{p}/" in f"/{rel}/":
                return True
            continue
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p):
            return True
        if is_dir and fnmatch.fnmatch(f"{rel}/", p):
            return True
    return False


@dataclass
class _FileScanResult:
    total_files: int = 0
    total_dirs: int = 0
    hidden_files: int = 0
    hidden_dirs: int = 0
    excluded_dirs: int = 0
    excluded_files: int = 0
    sample_dirs: list[str] = field(default_factory=list)
    sample_files: list[tuple[str, int]] = field(default_factory=list)


def _walk_files_scan(
    row_path: Path, patterns: list[str]
) -> _FileScanResult:
    res = _FileScanResult()
    for root, dirs, files in os.walk(row_path):
        rel_root = Path(root).resolve().relative_to(row_path)
        rel_root_posix = rel_root.as_posix()
        kept_dirs = []
        for d in dirs:
            rel_dir = d if rel_root_posix == "." else f"{rel_root_posix}/{d}"
            if _path_excluded(rel_dir, d, True, patterns):
                res.excluded_dirs += 1
            else:
                kept_dirs.append(d)
        dirs[:] = kept_dirs
        res.total_dirs += len(dirs)
        filtered_files: list[str] = []
        for name in files:
            rel_file = name if rel_root_posix == "." else f"{rel_root_posix}/{name}"
            if _path_excluded(rel_file, name, False, patterns):
                res.excluded_files += 1
                continue
            filtered_files.append(name)
        res.total_files += len(filtered_files)
        for dname in dirs:
            if dname.startswith("."):
                res.hidden_dirs += 1
            if len(res.sample_dirs) < _FILES_MAX_DIRS:
                res.sample_dirs.append((rel_root / dname).as_posix())
        for name in filtered_files:
            if name.startswith("."):
                res.hidden_files += 1
            try:
                size = (Path(root) / name).stat().st_size
            except OSError:
                size = 0
            if len(res.sample_files) < _FILES_MAX_FILES:
                res.sample_files.append(((rel_root / name).as_posix(), size))
    return res


def _files_summary_lines(
    app: Any,
    row: ProjectRow,
    res: _FileScanResult,
    file_view_exclude_patterns: list[str],
    fmt_size_human: Callable[[int], str],
) -> list[str]:
    return [
        f"[bold white]{app._esc(row.name)}[/]",
        f"[dim]{app._esc(row.path)}[/]",
        "[cyan]summary[/]: "
        f"dirs={res.total_dirs} files={res.total_files} "
        f"size=[yellow]{fmt_size_human(row.size_bytes)}[/] "
        f"[dim]({row.size_bytes} bytes, cached)[/]",
        f"[cyan]hidden[/]: dirs={res.hidden_dirs} files={res.hidden_files}",
        f"[cyan]exclude patterns[/]: dirs={res.excluded_dirs} "
        f"files={res.excluded_files} "
        f"[dim]({', '.join(file_view_exclude_patterns)})[/]",
        "",
    ]


def _files_dirs_listing(app: Any, res: _FileScanResult) -> list[str]:
    shown_dirs = sorted(res.sample_dirs)[:_FILES_MAX_DIRS]
    out = [
        f"[cyan]directories (max {_FILES_MAX_DIRS})[/]: "
        f"showing {len(shown_dirs)} of {res.total_dirs}"
    ]
    if shown_dirs:
        out.extend(f"  [dim]-[/] {app._esc(d)}/" for d in shown_dirs)
        if res.total_dirs > len(shown_dirs):
            out.append(
                f"  [dim]... +{res.total_dirs - len(shown_dirs)} more[/]"
            )
    else:
        out.append("  [dim](none)[/]")
    return out


def _files_files_listing(
    app: Any, res: _FileScanResult, fmt_size_human: Callable[[int], str]
) -> list[str]:
    shown_files = sorted(res.sample_files, key=lambda item: item[0])[
        :_FILES_MAX_FILES
    ]
    out = [
        f"[cyan]files (max {_FILES_MAX_FILES})[/]: "
        f"showing {len(shown_files)} of {res.total_files}"
    ]
    if shown_files:
        for rel, size in shown_files:
            out.append(
                f"  [dim]-[/] {app._esc(rel)} [dim]({fmt_size_human(size)})[/]"
            )
        if res.total_files > len(shown_files):
            out.append(
                f"  [dim]... +{res.total_files - len(shown_files)} more[/]"
            )
    else:
        out.append("  [dim](none)[/]")
    return out


def build_side_files_text(
    app: Any,
    row: ProjectRow,
    *,
    file_view_exclude_patterns: list[str],
    fmt_size_human: Callable[[int], str],
) -> str:
    if row.packed:
        return _packed_files_text(app, row, fmt_size_human)
    patterns = list(file_view_exclude_patterns)
    try:
        res = _walk_files_scan(row.path, patterns)
    except (OSError, ValueError) as exc:
        return f"[red]scan failed:[/] {app._esc(exc)}"
    lines: list[str] = []
    lines.extend(
        _files_summary_lines(
            app, row, res, file_view_exclude_patterns, fmt_size_human
        )
    )
    lines.extend(_files_dirs_listing(app, res))
    lines.append("")
    lines.extend(_files_files_listing(app, res, fmt_size_human))
    return "\n".join(lines)


def action_context_lines(app: Any, *, base_dir: Path) -> list[str]:
    rows = app._target_rows()
    selected = app._selected_row()
    lines: list[str] = ["[bold]Action Template Context[/]"]

    def _display_value(key: str, value: str, ctx: dict[str, str]) -> str:
        if key.endswith("_q"):
            raw_key = key[:-2]
            raw_value = ctx.get(raw_key)
            if raw_value is not None:
                return json.dumps(raw_value)
        return value

    always = action_template.build_always_context(app, base_dir)
    lines.append("[cyan]always[/]:")
    for key in sorted(always):
        lines.append(f"  {key}: {app._esc(_display_value(key, always[key], always))}")

    if selected is not None:
        per_row = action_template.build_per_row_context(app, selected, base_dir)
        lines.append("")
        lines.append("[cyan]per_row[/]:")
        for key in sorted(per_row):
            lines.append(f"  {key}: {app._esc(_display_value(key, per_row[key], per_row))}")
    else:
        lines.append("")
        lines.append("[cyan]per_row[/]: [dim](no selected row)[/]")

    if rows:
        listed = action_template.build_list_context(app, list(rows), base_dir)
        lines.append("")
        lines.append("[cyan]joined[/]:")
        for key in sorted(listed):
            lines.append(f"  {key}: {app._esc(_display_value(key, listed[key], listed))}")
    else:
        lines.append("")
        lines.append("[cyan]joined[/]: [dim](no selected rows)[/]")

    picker = action_template.build_filepicker_context("")
    lines.append("")
    lines.append("[cyan]filepicker[/]:")
    for key in sorted(picker):
        lines.append(f"  {key}: {app._esc(_display_value(key, picker[key], picker))}")
    return lines


def stats_and_context_lines(app: Any, *, base_dir: Path) -> list[str]:
    lines: list[str] = ["[bold]Stats and context[/]"]
    lines.extend(global_info_lines(app))
    lines.append("[dim]----------------------------------------[/]")
    lines.extend(stats_summary_lines(app))
    lines.append("[dim]----------------------------------------[/]")
    lines.extend(action_context_lines(app, base_dir=base_dir))
    return lines


def stats_summary_lines(app: Any) -> list[str]:
    rows = app._current_rows()
    active_total = len(app.active_rows)
    archived_total = len(app.archived_rows)
    untagged_total = sum(1 for r in app.active_rows if not r.tags)
    out: list[str] = []
    out.append(f"active total: {active_total}")
    out.append(f"archive total: {archived_total}")
    out.append(f"visible now: {len(rows)}")
    out.append(f"active untagged: {untagged_total}")
    return out
