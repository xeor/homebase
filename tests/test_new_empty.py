from __future__ import annotations

from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, base)


def test_empty_creates_project(tmp_path: Path) -> None:
    rc = _run(tmp_path, ["myproj"])
    assert rc == 0
    target = tmp_path / "myproj"
    assert target.is_dir()
    assert (target / ".base.yaml").is_file()


def test_empty_with_tmp_suffix(tmp_path: Path) -> None:
    rc = _run(tmp_path, ["myproj", "--tmp"])
    assert rc == 0
    assert (tmp_path / "myproj.tmp").is_dir()


def test_empty_with_explicit_name(tmp_path: Path) -> None:
    rc = _run(tmp_path, ["myproj", "altname"])
    assert rc == 0
    assert (tmp_path / "altname").is_dir()
    assert not (tmp_path / "myproj").exists()


def test_empty_conflict_fails(tmp_path: Path) -> None:
    (tmp_path / "exists").mkdir()
    rc = _run(tmp_path, ["exists"])
    assert rc == 1


def test_empty_dry_run_creates_nothing(tmp_path: Path) -> None:
    rc = _run(tmp_path, ["preview", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "preview").exists()


def test_empty_with_tag(tmp_path: Path) -> None:
    rc = _run(tmp_path, ["tagged", "--tag", "work"])
    assert rc == 0
    target = tmp_path / "tagged"
    assert target.is_dir()
    text = (target / ".base.yaml").read_text()
    assert "work" in text


def test_url_input_without_git_signal_routes_to_download(tmp_path: Path) -> None:
    # URL with no .git/ssh/adapter match → DownloadSource. Use --dry-run
    # to avoid a real fetch.
    rc = _run(tmp_path, ["https://example.com/x", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "x").exists()


def test_path_input_routes_to_local(tmp_path: Path) -> None:
    # ./thing doesn't exist → LocalDirSource path-not-found error
    rc = _run(tmp_path, ["./thing"])
    assert rc == 1


def test_too_many_positionals(tmp_path: Path) -> None:
    with pytest.MonkeyPatch.context() as m:
        m.setenv("BASE_FOLDER", str(tmp_path))
        rc = _run(tmp_path, ["a", "b", "c"])
        assert rc == 2
