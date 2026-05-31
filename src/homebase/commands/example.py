from __future__ import annotations

import os
import random
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..core.constants import (
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
)
from ..workspace.seed import (
    commit_files,
    git_init,
    make_active_project,
    make_archive_entry,
    pack_archive_entry,
    read_gitdir_id,
    write_project_marker,
)

LOREM_SENTENCES: tuple[str, ...] = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.",
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.",
    "Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia.",
    "Curabitur pretium tincidunt lacus nulla gravida orci a odio.",
    "Suspendisse in justo eu magna luctus suscipit sed lectus.",
    "Vivamus vestibulum sagittis sapien cum sociis natoque penatibus.",
    "Integer in sapien fermentum, malesuada augue at, fermentum nibh.",
    "Mauris massa vestibulum lacinia arcu eget nulla class aptent taciti.",
)

NAME_NOUNS: tuple[str, ...] = (
    "weather", "graph", "log", "config", "auth", "metric", "billing",
    "session", "playback", "render", "cache", "scheduler", "router",
    "ledger", "vault", "telemetry", "alert", "feed", "inventory",
    "notes", "todo", "habit", "diary", "recipe", "garden", "lab",
    "homelab", "router-2", "kindle", "photo", "audio", "video",
    "paper", "thesis", "rss", "twitter", "mastodon", "mail",
)

NAME_TOPICS: tuple[str, ...] = (
    "cli", "api", "engine", "monitor", "exporter", "shim",
    "service", "lab", "demo", "store", "kit", "pipe", "bridge",
    "agent", "tools", "stack", "ui", "dash", "sync", "snapshot",
)

TAG_TOPICAL: tuple[str, ...] = (
    "cli", "api", "web", "infra", "ml", "data", "db", "ops", "docs",
)
TAG_AREA: tuple[str, ...] = ("home", "work", "side-project")
TAG_LANGUAGE: tuple[str, ...] = (
    "lang:python", "lang:rust", "lang:go", "lang:typescript", "lang:bash",
)
TAG_DIRECT_LANG: tuple[str, ...] = ("python", "rust", "go", "typescript")
TAG_PRIORITY: tuple[str, ...] = ("prio:high", "prio:medium", "prio:low")
TAG_STATUS: tuple[str, ...] = ("fork", "scratch", "deprecated")

MAX_WIP = 5
DESCRIPTION_RATIO = 0.20
GIT_RATIO = 0.60
WORKTREE_COUNT_RANGE: tuple[int, int] = (2, 3)
ARCHIVE_COUNT = 10
ARCHIVE_PACKED_COUNT = 2
ARCHIVE_YEAR_SPAN = (2015, 2025)
AGE_BUCKETS_DAYS: tuple[tuple[int, int, float], ...] = (
    # (min_days, max_days, weight)
    (0, 30, 0.30),
    (30, 365, 0.30),
    (365, 365 * 5, 0.25),
    (365 * 5, 365 * 15, 0.15),
)


@dataclass
class _Project:
    name: str
    path: Path
    tags: list[str] = field(default_factory=list)
    description: str = ""
    wip: bool = False
    git: bool = False
    age_days: int = 0


def cmd_example_generate(path: str, count: int, seed: int | None) -> int:
    target = Path(path).expanduser()
    if target.exists():
        print(
            f"refusing to write into existing path: {target}",
            file=sys.stderr,
        )
        return 2
    if count < 1:
        print(f"count must be >= 1 (got {count})", file=sys.stderr)
        return 2
    rng = random.Random(seed)
    try:
        summary = _generate(target, count, rng)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"example generate failed: {exc}", file=sys.stderr)
        return 1
    _print_summary(target, summary)
    return 0


def _generate(target: Path, count: int, rng: random.Random) -> dict[str, int]:
    target.mkdir(parents=True)
    _write_homebase_dir(target)
    projects = _generate_active_projects(target, count, rng)
    worktrees = _attach_worktrees(target, projects, rng)
    archive_total, archive_packed = _generate_archive_entries(target, rng)
    _warm_cache(target, projects, rng)
    return {
        "active": len(projects),
        "git_repos": sum(1 for p in projects if p.git),
        "worktrees": worktrees,
        "wip": sum(1 for p in projects if p.wip),
        "described": sum(1 for p in projects if p.description),
        "archive": archive_total,
        "archive_packed": archive_packed,
    }


def _warm_cache(
    target: Path,
    projects: list[_Project],
    rng: random.Random,
) -> None:
    # Populate the sqlite cache so `b ls` and `b ls --archived` return
    # the freshly generated rows on first invocation. Without this, the
    # demo's first impression is an empty list until the TUI is opened.
    from ..cache.api import cache_set_opened_ts, cache_store_rows
    from ..workspace.rows import collect_workspace_rows

    # Some projects get a recent-ish opened_ts so the "last opened"
    # gradient lights up for screenshots; the rest stay at zero so the
    # "never opened" path is also visible.
    opened_candidates = [p for p in projects if rng.random() < 0.55]
    for project in opened_candidates:
        opened_age_days = rng.randint(0, 60)
        cache_set_opened_ts(
            target, project.path, _ts_from_age_days(opened_age_days),
        )

    active, archived = collect_workspace_rows(target, include_git_dirty=False)
    cache_store_rows(target, active, archived)


def _write_homebase_dir(target: Path) -> None:
    homebase_dir = target / HOMEBASE_DIR_NAME
    homebase_dir.mkdir()
    (homebase_dir / GLOBAL_CONFIG_FILE_NAME).write_text(_showcase_config_yaml())


def _generate_active_projects(
    target: Path,
    count: int,
    rng: random.Random,
) -> list[_Project]:
    names = _unique_names(count, rng)
    wip_indices = set(rng.sample(range(count), k=min(MAX_WIP, count)))
    description_target = max(1, round(count * DESCRIPTION_RATIO))
    description_indices = set(
        rng.sample(range(count), k=min(description_target, count)),
    )
    git_target = round(count * GIT_RATIO)
    git_indices = set(rng.sample(range(count), k=min(git_target, count)))

    projects: list[_Project] = []
    for idx, name in enumerate(names):
        tags = _pick_tags(rng)
        desc = _pick_description(rng) if idx in description_indices else ""
        wip = idx in wip_indices
        is_git = idx in git_indices
        age_days = _pick_age_days(rng)
        timestamp = _ts_from_age_days(age_days)

        path = make_active_project(
            target,
            name,
            tags=tags,
            description=desc,
            wip=wip,
            repo_dir="repo" if is_git else "",
        )
        if is_git:
            _seed_repo_content(path / "repo", name, rng, timestamp)
        else:
            _seed_flat_content(path, name, rng)
        _set_mtime_recursive(path, timestamp)

        projects.append(_Project(
            name=name,
            path=path,
            tags=tags,
            description=desc,
            wip=wip,
            git=is_git,
            age_days=age_days,
        ))
    return projects


def _attach_worktrees(
    target: Path,
    projects: list[_Project],
    rng: random.Random,
) -> int:
    git_projects = [p for p in projects if p.git]
    if len(git_projects) < 2:
        return 0
    wanted = rng.randint(*WORKTREE_COUNT_RANGE)
    candidates = rng.sample(git_projects, k=min(wanted, len(git_projects)))
    created = 0
    for parent in candidates:
        branch = rng.choice([
            "feature/oauth", "feature/import", "wip/rewrite",
            "topic/ui", "experiment/cache", "release/2026.04",
        ])
        sanitized = branch.replace("/", "--")
        wt_name = f"{parent.name}-{sanitized}"
        wt_path = target / wt_name
        if wt_path.exists():
            continue
        try:
            _make_worktree(parent, wt_path, branch, rng)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        created += 1
    return created


def _make_worktree(
    parent: _Project,
    wt_path: Path,
    branch: str,
    rng: random.Random,
) -> None:
    parent_repo = parent.path / "repo"
    wt_repo = wt_path / "repo"
    wt_path.mkdir()
    subprocess.run(
        ["git", "-C", str(parent_repo), "worktree", "add",
         "-b", branch, str(wt_repo)],
        check=True, capture_output=True,
    )
    gitdir_id = read_gitdir_id(parent_repo, wt_repo)
    age_days = max(0, parent.age_days - rng.randint(0, 30))
    timestamp = _ts_from_age_days(age_days)

    write_project_marker(
        wt_path,
        tags=[*parent.tags, "wip-branch"],
        repo_dir="repo",
        worktree={
            "of": parent.name,
            "branch": branch,
            "parent_path": str(parent_repo.resolve()),
            "gitdir_id": gitdir_id,
        },
    )
    _set_mtime_recursive(wt_path, timestamp)


def _generate_archive_entries(
    target: Path,
    rng: random.Random,
) -> tuple[int, int]:
    entries: list[Path] = []
    for i in range(ARCHIVE_COUNT):
        year = rng.randint(*ARCHIVE_YEAR_SPAN)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        topic = rng.choice(NAME_NOUNS)
        suffix = rng.choice(NAME_TOPICS)
        slug = f"{topic}-{suffix}-{i:02d}"
        tags = _pick_tags(rng, weighted_toward_status=True)
        desc = _pick_description(rng) if rng.random() < 0.30 else ""
        entry_path = make_archive_entry(
            target,
            date=date(year, month, day),
            slug=slug,
            tags=[*tags, "archived"],
            description=desc,
        )
        if rng.random() < 0.5:
            (entry_path / "README.md").write_text(_pick_description(rng) + "\n")
        _set_mtime_recursive(entry_path, _ts_from_date(year, month, day))
        entries.append(entry_path)

    packed = 0
    pack_targets = rng.sample(
        entries,
        k=min(ARCHIVE_PACKED_COUNT, len(entries)),
    )
    for entry in pack_targets:
        if pack_archive_entry(target, entry) is not None:
            packed += 1
    return len(entries), packed


def _unique_names(count: int, rng: random.Random) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    attempts = 0
    while len(names) < count and attempts < count * 30:
        attempts += 1
        noun = rng.choice(NAME_NOUNS)
        topic = rng.choice(NAME_TOPICS)
        candidate = f"{noun}-{topic}"
        if candidate in seen:
            continue
        seen.add(candidate)
        names.append(candidate)
    suffix = 0
    while len(names) < count:
        suffix += 1
        candidate = f"project-{suffix:03d}"
        if candidate not in seen:
            names.append(candidate)
            seen.add(candidate)
    return names


def _pick_tags(
    rng: random.Random,
    *,
    weighted_toward_status: bool = False,
) -> list[str]:
    pool: list[str] = []
    n_topical = rng.choices([0, 1, 2], weights=[1, 4, 3])[0]
    if n_topical:
        pool.extend(rng.sample(TAG_TOPICAL, k=n_topical))
    if rng.random() < 0.55:
        pool.append(rng.choice(TAG_LANGUAGE))
    if rng.random() < 0.35:
        pool.append(rng.choice(TAG_DIRECT_LANG))
    if rng.random() < 0.30:
        pool.append(rng.choice(TAG_PRIORITY))
    if rng.random() < 0.50:
        pool.append(rng.choice(TAG_AREA))
    if weighted_toward_status or rng.random() < 0.15:
        pool.append(rng.choice(TAG_STATUS))
    return pool


def _pick_description(rng: random.Random) -> str:
    n = rng.randint(1, 2)
    return " ".join(rng.sample(LOREM_SENTENCES, k=n))


def _pick_age_days(rng: random.Random) -> int:
    weights = [b[2] for b in AGE_BUCKETS_DAYS]
    bucket = rng.choices(AGE_BUCKETS_DAYS, weights=weights)[0]
    return rng.randint(bucket[0], bucket[1])


def _ts_from_age_days(age_days: int) -> int:
    dt = datetime.now(tz=timezone.utc) - timedelta(days=age_days)
    return int(dt.timestamp())


def _ts_from_date(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc).timestamp())


def _set_mtime_recursive(path: Path, ts: int) -> None:
    for sub in path.rglob("*"):
        try:
            os.utime(sub, (ts, ts), follow_symlinks=False)
        except OSError:
            continue
    try:
        os.utime(path, (ts, ts))
    except OSError:
        pass


def _seed_repo_content(
    repo_path: Path,
    name: str,
    rng: random.Random,
    base_ts: int,
) -> None:
    git_init(repo_path, user_email="demo@example.local", user_name="homebase demo")
    (repo_path / "README.md").write_text(f"# {name}\n\n{_pick_description(rng)}\n")
    if rng.random() < 0.35:
        (repo_path / "pyproject.toml").write_text(
            f"[project]\nname = '{name}'\nversion = '0.1.0'\n",
        )
    if rng.random() < 0.20:
        (repo_path / "Cargo.toml").write_text(
            f"[package]\nname = '{name}'\nversion = '0.1.0'\nedition = '2021'\n",
        )
    if rng.random() < 0.20:
        (repo_path / "go.mod").write_text(
            f"module {name}\n\ngo 1.22\n",
        )
    n_commits = rng.randint(1, 4)
    for c in range(n_commits):
        commit_ts = base_ts + c * rng.randint(3600, 86400)
        (repo_path / f"notes-{c:02d}.md").write_text(f"{_pick_description(rng)}\n")
        commit_files(
            repo_path,
            f"seed {c}",
            author_date=datetime.fromtimestamp(commit_ts, tz=timezone.utc),
        )


def _seed_flat_content(path: Path, name: str, rng: random.Random) -> None:
    if rng.random() < 0.5:
        (path / "README.md").write_text(f"# {name}\n\n{_pick_description(rng)}\n")
    if rng.random() < 0.3:
        (path / "NOTES.md").write_text(
            f"# {name}\n\n## Log\n\n### seed\n{_pick_description(rng)}\n",
        )
    if rng.random() < 0.25:
        (path / "pyproject.toml").write_text(
            f"[project]\nname = '{name}'\nversion = '0.1.0'\n",
        )


def _print_summary(target: Path, summary: dict[str, int]) -> None:
    print(f"generated demo base at: {target}")
    print(f"  active projects: {summary['active']}")
    print(f"  git repos:       {summary['git_repos']}")
    print(f"  worktrees:       {summary['worktrees']}")
    print(f"  wip:             {summary['wip']}")
    print(f"  with description: {summary['described']}")
    print(f"  archive entries: {summary['archive']}")
    print(f"  packed (.tgz):   {summary['archive_packed']}")
    print()
    print("try it:")
    print(f"  BASE_FOLDER={target} b")
    print(f"  BASE_FOLDER={target} b ls -l")
    print(f"  BASE_FOLDER={target} b ls --archived")
    print(f"  BASE_FOLDER={target} b tags ls")


def _showcase_config_yaml() -> str:
    return """\
# Generated by `b example generate`.
# Trim/extend to taste; see docs/kitchen-sink-config.md for the full reference.

archive:
  timezone: Europe/Oslo

filters:
  saved:
    - "#wip"
    - ":tags=0"
    - ":modified>=@-30d"
    - "!git"
  named:
    hot: "#cli OR #api"
    stale: ":modified<=@-365d"
    code: "##programming"
    urgent: "##priority"

properties:
  GIT:
    label: Git repo
    key: git
    color: "#86b8ff"
    # Match both flat (.git/) and nested (repo/.git/) layouts.
    dir-exists: [.git, repo/.git]
  WT:
    label: Git worktree
    key: wt
    color: "#8d84c6"
    file-exists: [.git, repo/.git]
  ANYGIT:
    label: Git repo or worktree
    key: anygit
    color: "#7dd3a7"
    path-exists: [.git, repo/.git]
  PY:
    label: Python project
    key: py
    color: "#f4c542"
    file-exists: [pyproject.toml, repo/pyproject.toml]
  RS:
    label: Rust project
    key: rs
    color: "#d97757"
    file-exists: [Cargo.toml, repo/Cargo.toml]
  GO:
    label: Go project
    key: go
    color: "#7fd1ae"
    file-exists: [go.mod, repo/go.mod]
  README:
    label: Has README
    key: readme
    color: "#9aa0a6"
    file-exists: [README.md, repo/README.md]
  NOTES:
    label: Has NOTES.md
    key: n
    color: "#c7a8ff"
    file-exists: [NOTES.md, repo/NOTES.md]

tag_rules:
  - match: "^prio:"
    parents: [priority]
    color: "#ff5555"
    bold: true
    prefix: "! "
  - match: "^lang:"
    parents: [programming]
    color: "#88ccff"
  # Compiled languages get a second parent so `##compiled` lights up too.
  # Order matters: first-match-wins, so the compiled set must come before
  # the wider `programming`-only rule.
  - tags: [rust, go]
    parents: [programming, compiled]
  - tags: [python, typescript]
    parents: [programming]
  - match: "^wip-branch$"
    color: "#ffb86c"
    bold: true
    suffix: " *"
  - tags: [priority]
    parents: [meta]
    group_only: true
  - tags: [meta]
    group_only: true

table:
  behavior:
    pin_wip_top: true
    side_width_pct: 33
  columns_style:
    date:
      all:
        modified:
          0: "#38bdf8"
          10: "#22c55e"
          100: "#facc15"
          365: "#f97316"
          1825: "#ef4444"
      active:
        active:
          0: "#38bdf8"
          3: "#22c55e"
          14: "#facc15"
          30: "#f97316"
          90: "#ef4444"
        created:
          0: "#38bdf8"
          30: "#22c55e"
          120: "#facc15"
          365: "#f97316"
          730: "#ef4444"
      archive:
        archived_at:
          0: "#38bdf8"
          90: "#22c55e"
          365: "#facc15"
          730: "#f97316"
          1825: "#ef4444"

suffixes: [tmp, fork, old]

actions:
  open_in_editor:
    kind: shell
    scope: target
    multi: joined
    command: "$EDITOR {{ paths_q }}"
  add_log_to_note:
    kind: note
    scope: target
    op: add_log

hotbar:
  - action: open_selected
    label: open
  - action: notes_create
    label: notes
    style:
      - bg_color: "#d8e9ff"
        fg_color: "#1b3558"
        underline: true
        when: "!n"
  - action: add_log_to_note
    label: log
    style:
      - bg_color: "#ffe9b8"
        fg_color: "#5a4200"
        italic: true
        when: "#wip"

keys:
  "f5": open_in_editor

notes:
  path_template: "{{ PROJECT_PATH }}/NOTES.md"
  open_command: "${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  create_command: "mkdir -p \\"$(dirname {{ NOTE_PATH_Q }})\\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  log:
    section:
      title: Log
      level: 2
    entry:
      timestamp_format: iso-seconds

open_mode:
  profile: shell_cd

hooks_post:
  rename:
    - name: notes_rename
      source: bundled
      enabled: true
    - name: tag_symlink_sync
      source: bundled
      enabled: true
  tag_change:
    - name: tag_symlink_sync
      source: bundled
      enabled: true
  new_project:
    - name: tag_symlink_sync
      source: bundled
      enabled: true
  delete:
    - name: tag_symlink_sync
      source: bundled
      enabled: true

state:
  view: active
  sort: last
"""
