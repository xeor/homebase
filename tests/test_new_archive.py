from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_")


def _archive_year_dir(base: Path) -> Path:
    return base / "_archive" / str(datetime.now().year)


def test_archive_on_empty(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["myproj", "--archive"])
    assert rc == 0
    archived_root = _archive_year_dir(tmp_path)
    assert archived_root.is_dir()
    entries = [p for p in archived_root.iterdir() if p.is_dir()]
    assert len(entries) == 1
    assert _DATE_RE.match(entries[0].name)
    assert entries[0].name.endswith("_myproj")
    assert not (tmp_path / "myproj").exists()


def test_archive_on_local(tmp_path: Path) -> None:
    src = tmp_path / "old-thing"
    src.mkdir()
    (src / "file.txt").write_text("data")
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [str(src), "--archive"])
    assert rc == 0
    archived = _archive_year_dir(base)
    entries = [p for p in archived.iterdir() if p.is_dir()]
    assert len(entries) == 1
    proj = entries[0]
    assert proj.name.endswith("_old-thing")
    assert (proj / "file.txt").read_text() == "data"
    assert (proj / ".base.yaml").is_file()
    assert not src.exists()


def test_archive_dry_run_no_writes(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["preview", "--archive", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "_archive").exists()
    assert not (tmp_path / "preview").exists()


def test_archive_with_explicit_name(tmp_path: Path) -> None:
    src = tmp_path / "thing"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [str(src), "renamed", "--archive"])
    assert rc == 0
    entries = list(_archive_year_dir(base).iterdir())
    assert len(entries) == 1
    assert entries[0].name.endswith("_renamed")
