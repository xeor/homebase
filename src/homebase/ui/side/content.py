from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow


def global_info_lines(app: Any) -> list[str]:
    rows = app._current_rows()
    selected = app._selected_row()
    query_text = str(getattr(app, "query", "")).strip()
    selected_text = selected.name if selected is not None else "-"
    open_panes_total = sum(int(n) for n in app.open_pane_count_by_project.values())
    return [
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
    dynamic_property_defs: list[Any],
    color_error_hex: str,
    color_warn_hex: str,
    color_info_hex: str,
) -> tuple[str, str]:
    rows = app._current_rows()
    active_total = len(app.active_rows)
    archived_total = len(app.archived_rows)
    untagged_total = sum(1 for r in app.active_rows if not r.tags)

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
    left.append("- ctrl+g           jump to existing tmux pane for selected project")
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
    left.append(
        f"- dynamic properties: [{color_error_hex}]E[/]=metadata error, [{color_warn_hex}]W[/]=metadata warning"
    )
    left.append("- metadata issues are explained in Selected -> Overview")
    left.append("")
    left.append("- filter syntax examples (combine with AND/OR and parentheses):")
    left.append("  #tag              exact tag")
    left.append("  !prop             property key/label/token")
    left.append("  .tmp              suffix")
    left.append("  tags=0            rows with no tags")
    left.append("  tags>4            rows with more than 4 tags")
    left.append("  props=0           rows with no properties")
    left.append("  props>0           rows with at least one property")
    left.append("  created=@-3y      created within last 3 years")
    left.append("  created=@-2y100d  relative spans can be combined")
    left.append("  created=@-2y20m   m=months, d=days (always summed)")
    left.append("  last=@-7d         changed within last 7 days")
    left.append("  created=2025      created in year 2025")
    left.append("  created=2025-01   created in Jan 2025")
    left.append("  created=2025-01-05 created on exact date")
    left.append("  created<=2025     created in/before year 2025")

    right: list[str] = []
    right.append(f"- active total:   {active_total}")
    right.append(f"- archive total:  {archived_total}")
    right.append(f"- visible now:    {len(rows)}")
    right.append(f"- active untagged:{untagged_total}")
    right.append("")
    prop_counts = property_count_map(app, all_property_defs=all_property_defs)
    dynamic_keys = {p.key for p in dynamic_property_defs}
    for pdef in all_property_defs():
        token = f"[{color_info_hex}]{pdef.token}[/]" if pdef.key in dynamic_keys else pdef.token
        right.append(f"- {token:<14} {pdef.key:<8} {prop_counts.get(pdef.key, 0)}")
    right.append("")
    top_tags = tag_count_map(app)
    if top_tags:
        for tag, count in top_tags:
            right.append(f"- {tag}: {count}")
    else:
        right.append("- (none)")
    right.append("")

    right.append("Actions in Current View")
    for key, label in app.view_config[app.view_mode]["actions"]:
        right.append(f"- {key}: {label}")

    return "\n".join(left), "\n".join(right)


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
        process = subprocess.run(list(cmd), cwd=cwd, text=True, capture_output=True, check=False)
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        return "", str(exc)
    out = (process.stdout or "").strip()
    if process.returncode != 0:
        err = (process.stderr or "").strip() or f"exit={process.returncode}"
        return out, err
    return out, None


def build_side_git_text(app: Any, row: ProjectRow) -> str:
    if row.packed:
        return "[dim]packed archive: git details unavailable until unpacked[/]"
    if not (row.path / ".git").is_dir():
        return "[dim]not a git repository[/]"
    lines: list[str] = []
    max_branches = 5
    max_status = 40
    max_commits = 10
    max_remotes = 8

    lines.append(
        f"[cyan]branch[/]: [green]{app._esc(row.branch)}[/]{'[yellow]*[/]' if row.dirty else ''}"
    )

    upstream, _err_upstream = run_cmd(
        row.path,
        "git",
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    )
    if upstream:
        ahead_behind, _err_ab = run_cmd(
            row.path,
            "git",
            "rev-list",
            "--left-right",
            "--count",
            "@{upstream}...HEAD",
        )
        if ahead_behind and "\t" in ahead_behind:
            behind, ahead = ahead_behind.split("\t", 1)
            lines.append(
                f"[cyan]tracking[/]: {app._esc(upstream)} [dim](ahead {app._esc(ahead.strip())}, behind {app._esc(behind.strip())})[/]"
            )
        else:
            lines.append(f"[cyan]tracking[/]: {app._esc(upstream)}")
    else:
        lines.append("[cyan]tracking[/]: [dim](none)[/]")

    last_commit, err_last = run_cmd(
        row.path,
        "git",
        "log",
        "-1",
        "--pretty=%h %ad %s",
        "--date=iso-strict",
    )
    lines.append(f"[cyan]last commit[/]: {app._esc(last_commit or '-')}")
    if err_last:
        lines.append(f"[red]git log error:[/] {app._esc(err_last)}")

    status, err_status = run_cmd(row.path, "git", "status", "--short")
    staged_stat, _err_staged_stat = run_cmd(row.path, "git", "diff", "--cached", "--shortstat")
    unstaged_stat, _err_unstaged_stat = run_cmd(row.path, "git", "diff", "--shortstat")
    entries = status.splitlines() if status else []
    untracked_count = sum(1 for ln in entries if ln.startswith("??"))
    staged_count = sum(1 for ln in entries if len(ln) >= 2 and ln[0] not in {" ", "?"})
    unstaged_count = sum(1 for ln in entries if len(ln) >= 2 and ln[1] not in {" ", "?"})
    lines.append(
        f"[cyan]status summary[/]: staged={staged_count} unstaged={unstaged_count} untracked={untracked_count}"
    )
    if staged_stat:
        lines.append(f"[cyan]staged stat[/]: {app._esc(staged_stat)}")
    if unstaged_stat:
        lines.append(f"[cyan]unstaged stat[/]: {app._esc(unstaged_stat)}")

    lines.append(f"[cyan]status entries[/]: [dim](max {max_status})[/]")
    if status:
        for ln in entries[:max_status]:
            lines.append(app._esc(ln))
        if len(entries) > max_status:
            lines.append(f"[dim]... +{len(entries) - max_status} more[/]")
    else:
        lines.append("[dim]clean working tree[/]")
    if err_status:
        lines.append(f"[red]git status error:[/] {app._esc(err_status)}")

    branches, err_branches = run_cmd(
        row.path,
        "git",
        "for-each-ref",
        "--sort=-committerdate",
        "--format=%(if)%(HEAD)%(then)* %(else)  %(end)%(refname:short)  %(committerdate:relative)",
        "refs/heads",
    )
    lines.append(f"[cyan]branches[/]: [dim](max {max_branches})[/]")
    if branches:
        branch_lines = branches.splitlines()
        lines.extend(app._esc(ln) for ln in branch_lines[:max_branches])
        if len(branch_lines) > max_branches:
            lines.append(f"[dim]... +{len(branch_lines) - max_branches} more[/]")
    else:
        lines.append("[dim]-[/]")
    if err_branches:
        lines.append(f"[red]branches error:[/] {app._esc(err_branches)}")

    remotes, err_remotes = run_cmd(row.path, "git", "remote", "-v")
    lines.append(f"[cyan]remotes[/]: [dim](max {max_remotes})[/]")
    if remotes:
        uniq: list[str] = []
        seen: set[str] = set()
        for ln in remotes.splitlines():
            key = ln.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            uniq.append(key)
        lines.extend(app._esc(ln) for ln in uniq[:max_remotes])
        if len(uniq) > max_remotes:
            lines.append(f"[dim]... +{len(uniq) - max_remotes} more[/]")
    else:
        lines.append("[dim]-[/]")
    if err_remotes:
        lines.append(f"[red]remotes error:[/] {app._esc(err_remotes)}")

    recent, err_recent = run_cmd(
        row.path,
        "git",
        "log",
        f"-{max_commits}",
        "--pretty=%h %ad %s",
        "--date=iso-strict",
    )
    lines.append(f"[cyan]recent commits[/]: [dim](max {max_commits})[/]")
    if recent:
        commits = recent.splitlines()
        lines.extend(app._esc(ln) for ln in commits[:max_commits])
    else:
        lines.append("[dim]-[/]")
    if err_recent:
        lines.append(f"[red]git recent error:[/] {app._esc(err_recent)}")
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


def build_side_files_text(
    app: Any,
    row: ProjectRow,
    *,
    file_view_exclude_patterns: list[str],
    fmt_size_human: Callable[[int], str],
) -> str:
    if row.packed:
        lines = ["[cyan]packed[/]: yes (.base-pkg.tgz)"]
        lines.append(f"[cyan]file[/]: {app._esc(row.path.name)}")
        lines.append(
            f"[cyan]size[/]: {fmt_size_human(row.size_bytes)} [dim]({row.size_bytes} bytes, cached)[/]"
        )
        lines.append("[dim]unpack to inspect files[/]")
        return "\n".join(lines)
    lines: list[str] = []
    total_files = 0
    total_dirs = 0
    hidden_files = 0
    hidden_dirs = 0
    excluded_dirs = 0
    excluded_files = 0
    sample_dirs: list[str] = []
    sample_files: list[tuple[str, int]] = []
    max_dirs = 30
    max_files = 50
    patterns = list(file_view_exclude_patterns)

    def excluded(rel_posix: str, name: str, is_dir: bool) -> bool:
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

    try:
        for root, dirs, files in os.walk(row.path):
            rel_root = Path(root).resolve().relative_to(row.path)
            rel_root_posix = rel_root.as_posix()
            kept_dirs = []
            for d in dirs:
                rel_dir = d if rel_root_posix == "." else f"{rel_root_posix}/{d}"
                if excluded(rel_dir, d, is_dir=True):
                    excluded_dirs += 1
                else:
                    kept_dirs.append(d)
            dirs[:] = kept_dirs
            total_dirs += len(dirs)
            filtered_files: list[str] = []
            for name in files:
                rel_file = name if rel_root_posix == "." else f"{rel_root_posix}/{name}"
                if excluded(rel_file, name, is_dir=False):
                    excluded_files += 1
                    continue
                filtered_files.append(name)
            total_files += len(filtered_files)
            for dname in dirs:
                if dname.startswith("."):
                    hidden_dirs += 1
                if len(sample_dirs) < max_dirs:
                    rel = (rel_root / dname).as_posix()
                    sample_dirs.append(rel)
            for name in filtered_files:
                p = Path(root) / name
                if name.startswith("."):
                    hidden_files += 1
                size = 0
                try:
                    size = p.stat().st_size
                except OSError:
                    size = 0
                if len(sample_files) < max_files:
                    rel_file = (rel_root / name).as_posix()
                    sample_files.append((rel_file, size))
    except (OSError, ValueError) as exc:
        lines.append(f"[red]scan failed:[/] {app._esc(exc)}")
        return "\n".join(lines)

    lines.append(f"[bold white]{app._esc(row.name)}[/]")
    lines.append(f"[dim]{app._esc(row.path)}[/]")
    lines.append(
        "[cyan]summary[/]: "
        f"dirs={total_dirs} files={total_files} "
        f"size=[yellow]{fmt_size_human(row.size_bytes)}[/] "
        f"[dim]({row.size_bytes} bytes, cached)[/]"
    )
    lines.append(f"[cyan]hidden[/]: dirs={hidden_dirs} files={hidden_files}")
    lines.append(
        f"[cyan]exclude patterns[/]: dirs={excluded_dirs} files={excluded_files} [dim]({', '.join(file_view_exclude_patterns)})[/]"
    )
    lines.append("")

    shown_dirs = sorted(sample_dirs)[:max_dirs]
    lines.append(f"[cyan]directories (max {max_dirs})[/]: showing {len(shown_dirs)} of {total_dirs}")
    if shown_dirs:
        lines.extend(f"  [dim]-[/] {app._esc(d)}/" for d in shown_dirs)
        if total_dirs > len(shown_dirs):
            lines.append(f"  [dim]... +{total_dirs - len(shown_dirs)} more[/]")
    else:
        lines.append("  [dim](none)[/]")

    lines.append("")
    shown_files = sorted(sample_files, key=lambda item: item[0])[:max_files]
    lines.append(f"[cyan]files (max {max_files})[/]: showing {len(shown_files)} of {total_files}")
    if shown_files:
        for rel, size in shown_files:
            lines.append(f"  [dim]-[/] {app._esc(rel)} [dim]({fmt_size_human(size)})[/]")
        if total_files > len(shown_files):
            lines.append(f"  [dim]... +{total_files - len(shown_files)} more[/]")
    else:
        lines.append("  [dim](none)[/]")
    return "\n".join(lines)
