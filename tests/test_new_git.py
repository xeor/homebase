from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _make_bare_repo(path: Path) -> Path:
    """Create a small bare repo at `path` populated with one commit."""
    work = path.parent / (path.name + "-work")
    work.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "init", "--bare", "-q", str(path)], check=True)
    subprocess.run(
        ["git", "-C", str(work), "remote", "add", "origin", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "push", "-q", "-u", "origin", "HEAD"],
        check=True,
        capture_output=True,
    )
    shutil.rmtree(work)
    return path


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


def test_git_clones_into_repo_layout(tmp_path: Path) -> None:
    repo = _make_bare_repo(tmp_path / "remote.git")
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [f"file://{repo}"])
    assert rc == 0
    proj = base / "remote"
    assert proj.is_dir()
    assert (proj / ".base.yaml").is_file()
    assert (proj / "repo").is_dir()
    assert (proj / "repo" / ".git").is_dir()


def test_git_with_explicit_name(tmp_path: Path) -> None:
    repo = _make_bare_repo(tmp_path / "remote.git")
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [f"file://{repo}", "myname"])
    assert rc == 0
    assert (base / "myname" / "repo").is_dir()
    assert not (base / "remote").exists()


def test_git_failed_clone_rolls_back(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"file://{tmp_path / 'nonexistent.git'}", "ghost"])
    assert rc == 1
    assert not (base / "ghost").exists()


def test_git_dry_run(tmp_path: Path) -> None:
    repo = _make_bare_repo(tmp_path / "remote.git")
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"file://{repo}", "--dry-run"])
    assert rc == 0
    assert not (base / "remote").exists()


def test_git_with_tmp_suffix(tmp_path: Path) -> None:
    repo = _make_bare_repo(tmp_path / "remote.git")
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"file://{repo}", "--tmp"])
    assert rc == 0
    assert (base / "remote.tmp" / "repo").is_dir()


def test_github_url_routes_to_git_via_adapter(tmp_path: Path) -> None:
    # No network; just verify routing. Use --dry-run so clone never fires.
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, ["https://github.com/foo/bar", "--dry-run"])
    assert rc == 0


def test_dot_git_url_routes_to_git(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, ["https://example.com/p/r.git", "--dry-run"])
    assert rc == 0


def test_ssh_form_routes_to_git(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, ["git@github.com:foo/bar.git", "--dry-run"])
    assert rc == 0


def test_user_host_config_routes_to_git(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    cfg_dir = base / ".homebase"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "new:\n"
        "  sources:\n"
        "    git:\n"
        "      config:\n"
        "        hosts:\n"
        "          git.example.org: gitlab\n"
    )
    rc = _run(base, tmp_path, ["https://git.example.org/team/proj", "--dry-run"])
    assert rc == 0
