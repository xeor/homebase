"""Regression tests for the benchmark dataset seeder.

The point of these tests is to lock the *structural* output of the
seeder (names, counts, tag pattern, wip set, archive layout, packed
count) so that swapping the implementation to use shared seed
primitives doesn't silently shift what historical benchmark runs were
measured against. Timings are not asserted here."""
from __future__ import annotations

from pathlib import Path

import yaml

from homebase.workspace.benchmark import (
    _BENCHMARK_TAGS_POOL,
    _seed_benchmark_dataset,
)


def _read_meta(path: Path) -> dict:
    return yaml.safe_load((path / ".base.yaml").read_text()) or {}


def _seed_small(base: Path) -> dict[str, object]:
    from homebase.commands.archive import archive_pack_internal

    base.mkdir()
    return _seed_benchmark_dataset(
        base,
        active_count=12,
        archived_dir_count=8,
        archived_pack_count=3,
        archive_pack_internal=archive_pack_internal,
    )


def test_active_project_count_includes_three_git_repos(tmp_path: Path) -> None:
    base = tmp_path / "base"
    summary = _seed_small(base)
    assert summary["active_projects"] == 12 + 3
    assert summary["git_small"] == 1
    assert summary["git_medium"] == 1
    assert summary["git_large"] == 1


def test_project_names_follow_index_rules(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    names = sorted(
        p.name for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(("_", "."))
    )
    expected = (
        # idx 0 → 0 % 11 == 0 → .tmp; idx 11 → .tmp
        ["bench-0000.tmp"]
        + [f"bench-{i:04d}" for i in range(1, 11)]
        + ["bench-0011.tmp"]
        + ["bench-git-large", "bench-git-medium", "bench-git-small"]
    )
    assert names == sorted(expected)


def test_fork_suffix_at_idx_17(tmp_path: Path) -> None:
    # idx=17 wouldn't fit in 12 — assert with larger dataset where it
    # actually fires (17 % 11 != 0, 17 % 17 == 0 → .fork).
    base = tmp_path / "base"
    base.mkdir()
    _seed_benchmark_dataset(
        base, active_count=20, archived_dir_count=1, archived_pack_count=0,
    )
    assert (base / "bench-0017.fork").is_dir()
    # idx=11 keeps .tmp suffix (precedence: .tmp over .fork)
    assert (base / "bench-0011.tmp").is_dir()


def test_tags_rotate_by_index_modulo(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    # idx=3 → tag_count = 3, k=0,1,2 → pool[3], pool[4], pool[5]
    p3 = base / "bench-0003"
    assert _read_meta(p3)["tags"] == sorted(
        [_BENCHMARK_TAGS_POOL[i] for i in (3, 4, 5)]
    )
    # idx=0 → tag_count = 0, no tags
    p0 = base / "bench-0000.tmp"
    assert "tags" not in _read_meta(p0)


def test_wip_fires_every_seventh(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    wip = {
        p.name for p in base.iterdir()
        if p.is_dir() and p.name.startswith("bench-")
        and not p.name.startswith("bench-git-")
        and _read_meta(p).get("wip") is True
    }
    assert wip == {"bench-0000.tmp", "bench-0007"}


def test_opened_ts_is_not_written_to_yaml(tmp_path: Path) -> None:
    # Regression: pre-seed-primitives, this key landed in .base.yaml
    # and triggered a schema warning ("unknown key(s): opened_ts").
    # The shared writer now filters it out.
    base = tmp_path / "base"
    _seed_small(base)
    for p in base.iterdir():
        if not p.is_dir() or not p.name.startswith("bench-"):
            continue
        if p.name.startswith("bench-git-"):
            continue
        meta = _read_meta(p)
        assert "opened_ts" not in meta, p.name


def test_decoy_files_follow_index_modulo(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    # idx % 3 == 0 → pyproject.toml: 0, 3, 6, 9
    assert (base / "bench-0000.tmp" / "pyproject.toml").is_file()
    assert (base / "bench-0003" / "pyproject.toml").is_file()
    assert not (base / "bench-0001" / "pyproject.toml").is_file()
    # idx % 4 == 0 → .envrc: 0, 4, 8
    assert (base / "bench-0004" / ".envrc").is_file()
    assert not (base / "bench-0005" / ".envrc").is_file()
    # idx % 6 == 0 → requirements.txt: 0, 6
    assert (base / "bench-0006" / "requirements.txt").is_file()
    assert not (base / "bench-0001" / "requirements.txt").is_file()


def test_git_repos_have_no_marker_but_have_history(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    for name in ("bench-git-small", "bench-git-medium", "bench-git-large"):
        repo = base / name
        # These are flat git repos used as raw inputs to git_info /
        # project_row timings, NOT homebase projects.
        assert (repo / ".git").is_dir()
        assert not (repo / ".base.yaml").exists()
    # Commit count matches the configured commits argument exactly.
    import subprocess

    def _commits(repo: Path) -> int:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-list", "--count", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return int(out)
    assert _commits(base / "bench-git-small") == 4
    assert _commits(base / "bench-git-medium") == 8
    assert _commits(base / "bench-git-large") == 12


def test_archive_layout_under_year_subdir(tmp_path: Path) -> None:
    base = tmp_path / "base"
    summary = _seed_small(base)
    archive_root = base / "_archive"
    # Years present must all be 4-digit numeric.
    years = sorted(p.name for p in archive_root.iterdir() if p.is_dir())
    assert all(y.isdigit() and len(y) == 4 for y in years)

    entries = []
    for year_dir in archive_root.iterdir():
        if not year_dir.is_dir():
            continue
        entries.extend(year_dir.iterdir())
    dirs = [e for e in entries if e.is_dir()]
    packed = [e for e in entries if e.suffix == ".tgz"]
    # 8 created, 3 packed → 5 dirs left + 3 .tgz files
    assert len(dirs) == 8 - 3
    assert len(packed) == 3
    assert summary["archived_dirs"] == 8
    assert summary["archived_packed"] == 3


def test_archive_entry_has_required_metadata(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _seed_small(base)
    # Find arch-0004 (still a dir — 0..2 got packed).
    matches = list(base.rglob("*_arch-0004"))
    assert len(matches) == 1
    entry = matches[0]
    assert entry.is_dir()
    meta = _read_meta(entry)
    assert meta["description"] == "archived benchmark 4"
    # tags = ["arch", f"g{4 % 9}"] = ["arch", "g4"]
    assert meta["tags"] == ["arch", "g4"]
    # opened_ts dropped — same regression as for active projects.
    assert "opened_ts" not in meta


def test_summary_shape_matches_report_contract(tmp_path: Path) -> None:
    # benchmark_report consumers expect these keys verbatim.
    base = tmp_path / "base"
    summary = _seed_small(base)
    required = {
        "active_projects",
        "archived_dirs",
        "archived_packed",
        "git_small",
        "git_medium",
        "git_large",
        "git_paths",
    }
    assert required.issubset(summary.keys())
    paths = summary["git_paths"]
    assert isinstance(paths, dict)
    assert set(paths.keys()) == {"small", "medium", "large"}
