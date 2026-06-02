from __future__ import annotations

import os
import subprocess
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.metadata.api import save_base_tags
from homebase.workspace.new import cmd_new
from homebase.workspace.tag_sync import sync_tag_symlinks


def _run_new(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args, "--no-open"])
    return cmd_new(ns, base, cwd)


def _init_project_repo(base: Path, name: str) -> Path:
    project = base / name
    repo = project / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    (project / ".base.yaml").write_text("tags: []\nrepo_dir: repo\n", encoding="utf-8")
    return project


def test_parent_and_worktree_can_share_tag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    parent = _init_project_repo(tmp_path, "foo")
    assert _run_new(tmp_path, tmp_path, ["featx", "--as", "worktree", "--from", "foo"]) == 0
    wt = tmp_path / "foo-featx"

    save_base_tags(tmp_path, parent, ["work"])
    save_base_tags(tmp_path, wt, ["work"])

    err = sync_tag_symlinks(tmp_path)
    assert err is None

    tag_dir = tmp_path / "_tags" / "work"
    assert tag_dir.is_dir()
    links = sorted(os.listdir(tag_dir))
    assert "foo" in links
    assert "foo-featx" in links
    parent_link = tag_dir / "foo"
    wt_link = tag_dir / "foo-featx"
    assert parent_link.is_symlink() and wt_link.is_symlink()
    assert Path(os.readlink(parent_link)).name == "foo"
    assert Path(os.readlink(wt_link)).name == "foo-featx"
