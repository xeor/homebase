from __future__ import annotations

import subprocess
from pathlib import Path

from homebase.workspace import projects


def test_cmd_create_quick_creates_from_template_config(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "create_templates:\n"
        "  - key: tmp\n"
        "    options: [prefix-datetime, suffix-tmp]\n"
        "    tags: [scratch]\n",
        encoding="utf-8",
    )

    rc = projects.cmd_create_quick(tmp_path, "tmp", "demo")
    assert rc == 0

    created = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name not in {".copier", ".homebase"}
    ]
    assert len(created) == 1
    assert created[0].name.endswith("demo.tmp")
    assert (created[0] / ".base.yaml").is_file()


def test_cmd_create_quick_generate_name_when_configured(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "create_templates:\n"
        "  - key: gen\n"
        "    options: [generate-ts-name]\n",
        encoding="utf-8",
    )

    rc = projects.cmd_create_quick(tmp_path, "gen", None)
    assert rc == 0
    created = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name not in {".copier", ".homebase"}
    ]
    assert len(created) == 1
    assert created[0].name


def test_cmd_create_quick_generate_next_alpha_name(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "create_templates:\n"
        "  - key: alpha\n"
        "    options: [generate-next-alpha-name]\n",
        encoding="utf-8",
    )
    rc = projects.cmd_create_quick(tmp_path, "alpha", None)
    assert rc == 0
    assert (tmp_path / "b").is_dir()


def test_build_row_haystack_lower_lowercases_and_joins() -> None:
    hay = projects.build_row_haystack_lower(
        name="MyProject",
        description="A Demo",
        tags=["CLI", "Web"],
        properties=[],
        branch="MAIN",
        path=Path("/tmp/MyProject"),
    )
    assert hay == hay.lower()
    for needle in ("myproject", "a demo", "cli", "web", "main", "/tmp/myproject"):
        assert needle in hay


def test_project_row_populates_haystack_lower(tmp_path: Path) -> None:
    target = tmp_path / "demo-project"
    target.mkdir()
    (target / ".base.yaml").write_text("tags:\n  - cli\n  - web\n", encoding="utf-8")

    row = projects.project_row(target, include_git_dirty=False)
    assert row.haystack_lower
    assert "demo-project" in row.haystack_lower
    for tag in ("cli", "web"):
        assert tag in row.haystack_lower


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def test_git_info_caches_branch_and_ts_until_index_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    projects._git_clear_cache()

    branch1, dirty1, ts1 = projects.git_info(repo)
    assert dirty1 == ""
    assert repo in projects._GIT_INFO_CACHE

    branch2, dirty2, ts2 = projects.git_info(repo)
    assert (branch1, ts1) == (branch2, ts2)
    assert dirty2 == ""

    (repo / "f.txt").write_text("b\n", encoding="utf-8")
    _, dirty3, _ = projects.git_info(repo)
    assert dirty3 == "*"
    assert repo in projects._GIT_INFO_CACHE

    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "second"], cwd=repo, check=True)
    branch4, dirty4, ts4 = projects.git_info(repo)
    assert dirty4 == ""
    assert ts4 >= ts1


def test_git_info_returns_unverified_when_dirty_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    _init_git_repo(repo)
    projects._git_clear_cache()

    _, dirty_warm, _ = projects.git_info(repo, include_dirty=True)
    assert dirty_warm == ""

    _, dirty_skip, _ = projects.git_info(repo, include_dirty=False)
    assert dirty_skip == "~"


def test_cmd_create_quick_debug_dry_run(tmp_path: Path) -> None:
    (tmp_path / ".homebase").mkdir()
    (tmp_path / ".homebase" / "config.yaml").write_text(
        "create_templates:\n"
        "  - key: tmp\n"
        "    options: [generate-ts-name]\n",
        encoding="utf-8",
    )
    rc = projects.cmd_create_quick(tmp_path, "tmp", None, debug=True)
    assert rc == 0
    created_dirs = [
        p for p in tmp_path.iterdir() if p.is_dir() and p.name not in {".copier", ".homebase"}
    ]
    assert created_dirs == []
