from __future__ import annotations

from pathlib import Path

import yaml

from homebase.commands import example


def _generate(tmp_path: Path, count: int = 20, seed: int = 99) -> Path:
    target = tmp_path / "demo"
    rc = example.cmd_example_generate(str(target), count, seed)
    assert rc == 0, f"generator returned {rc}"
    return target


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def test_refuses_to_overwrite_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    target.mkdir()
    rc = example.cmd_example_generate(str(target), 5, 1)
    assert rc == 2


def test_rejects_zero_count(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    rc = example.cmd_example_generate(str(target), 0, 1)
    assert rc == 2
    assert not target.exists()


def test_layout_basics(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=20, seed=11)
    assert (target / ".homebase" / "config.yaml").is_file()
    assert (target / "_archive").is_dir()


def test_active_count_matches_request(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=15, seed=5)
    active = [
        p for p in target.iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    ]
    worktree_count = sum(
        1
        for p in active
        if isinstance((_read_yaml(p / ".base.yaml") or {}).get("worktree"), dict)
    )
    non_worktree = len(active) - worktree_count
    assert non_worktree == 15
    assert worktree_count >= 2


def test_max_wip_respected(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=30, seed=7)
    wip_total = 0
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        data = _read_yaml(p / ".base.yaml")
        if data.get("wip") is True:
            wip_total += 1
    assert wip_total <= example.MAX_WIP


def test_descriptions_at_or_below_ratio(tmp_path: Path) -> None:
    count = 40
    target = _generate(tmp_path, count=count, seed=3)
    described = 0
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        data = _read_yaml(p / ".base.yaml")
        if data.get("worktree") is not None:
            continue
        if isinstance(data.get("description"), str) and data["description"].strip():
            described += 1
    expected = round(count * example.DESCRIPTION_RATIO)
    assert described == expected


def test_git_ratio_approximate(tmp_path: Path) -> None:
    count = 30
    target = _generate(tmp_path, count=count, seed=21)
    git_repos = 0
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        data = _read_yaml(p / ".base.yaml")
        if data.get("worktree") is not None:
            continue
        if (p / "repo" / ".git").is_dir():
            git_repos += 1
    assert git_repos == round(count * example.GIT_RATIO)


def test_worktrees_link_to_real_parents(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=20, seed=42)
    worktree_dirs = []
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        data = _read_yaml(p / ".base.yaml")
        if isinstance(data.get("worktree"), dict):
            worktree_dirs.append((p, data["worktree"]))
    low, high = example.WORKTREE_COUNT_RANGE
    assert low <= len(worktree_dirs) <= high
    for path, wt in worktree_dirs:
        assert (path / "repo" / ".git").is_file()
        parent_path = Path(wt["parent_path"])
        assert parent_path.is_dir()
        assert (parent_path / ".git").is_dir()
        assert (parent_path / ".git" / "worktrees" / wt["gitdir_id"]).is_dir()


def test_archive_layout(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=10, seed=4)
    archive_root = target / "_archive"
    year_dirs = sorted(p.name for p in archive_root.iterdir() if p.is_dir())
    assert all(name.isdigit() and len(name) == 4 for name in year_dirs)
    entries = []
    for year_dir in archive_root.iterdir():
        if not year_dir.is_dir():
            continue
        entries.extend(year_dir.iterdir())
    total_entries = len(entries)
    packed = sum(1 for e in entries if e.suffix == ".tgz")
    assert total_entries == example.ARCHIVE_COUNT
    assert packed == example.ARCHIVE_PACKED_COUNT


def test_date_spread(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=40, seed=13)
    import time

    now = int(time.time())
    fifteen_years_s = 365 * 15 * 86400
    oldest = now
    newest = 0
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        mtime = int(p.stat().st_mtime)
        oldest = min(oldest, mtime)
        newest = max(newest, mtime)
    span = newest - oldest
    # 40 projects across 4 buckets should produce wide span; require at
    # least a year.
    assert span >= 365 * 86400
    # Nothing older than ~15 years.
    assert (now - oldest) <= fifteen_years_s + 86400


def test_tags_shared_across_projects(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=30, seed=8)
    from collections import Counter

    counter: Counter[str] = Counter()
    for p in target.iterdir():
        if not p.is_dir() or p.name.startswith((".", "_")):
            continue
        data = _read_yaml(p / ".base.yaml")
        for tag in data.get("tags", []) or []:
            counter[str(tag)] += 1
    shared = [tag for tag, n in counter.items() if n >= 2]
    assert len(shared) >= 5, counter


def test_seed_is_deterministic(tmp_path: Path) -> None:
    t1 = tmp_path / "a"
    t2 = tmp_path / "b"
    example.cmd_example_generate(str(t1), 12, 1234)
    example.cmd_example_generate(str(t2), 12, 1234)

    def _names(root: Path) -> list[str]:
        return sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and not p.name.startswith((".", "_"))
        )
    assert _names(t1) == _names(t2)


def test_config_yaml_parses(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=8, seed=55)
    cfg = yaml.safe_load((target / ".homebase" / "config.yaml").read_text())
    assert isinstance(cfg, dict)
    assert "tag_rules" in cfg and isinstance(cfg["tag_rules"], list)
    assert "properties" in cfg and isinstance(cfg["properties"], dict)
    assert "GIT" in cfg["properties"]


def test_cache_warms(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=10, seed=2)
    from homebase.cache.api import cache_load_rows

    active, archived, _ts = cache_load_rows(target)
    assert len(active) >= 10  # active + worktrees
    assert len(archived) == example.ARCHIVE_COUNT


def test_tag_symlinks_populated(tmp_path: Path) -> None:
    target = _generate(tmp_path, count=20, seed=12)
    tags_root = target / "_tags"
    assert tags_root.is_dir()
    tag_dirs = [p for p in tags_root.iterdir() if p.is_dir()]
    assert tag_dirs, "_tags/ should contain at least one tag directory"
    total_links = 0
    for tag_dir in tag_dirs:
        for entry in tag_dir.iterdir():
            assert entry.is_symlink(), f"{entry} should be a symlink"
            total_links += 1
    assert total_links >= len(tag_dirs)
