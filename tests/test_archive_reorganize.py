from __future__ import annotations

import re
from pathlib import Path

from homebase.commands import workspace as commands_workspace
from homebase.core import utils as core_utils

YEAR_RE = re.compile(r"^\d{4}$")


def _run(base: Path, *, dry_run: bool = False) -> int:
    return commands_workspace.cmd_archive_reorganize(
        base,
        archive_dir_name="_archive",
        year_from_name=core_utils.archive_year_from_name,
        is_year_dir=lambda name: bool(YEAR_RE.match(name)),
        normalize_name=core_utils.normalize_date_prefix,
        confirm=lambda: None,
        dry_run=dry_run,
    )


def test_reorganize_moves_directory_into_year(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    entry = arch / "2025-01-15_foo"
    entry.mkdir(parents=True)
    (entry / ".base.yaml").write_text("{}\n")

    rc = _run(base)
    assert rc == 0
    assert (arch / "2025" / "2025-01-15_foo" / ".base.yaml").is_file()
    assert not entry.exists()


def test_reorganize_moves_tgz_into_year(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    arch.mkdir(parents=True)
    tgz = arch / "2009-04-14_old.tgz"
    tgz.write_bytes(b"x")

    rc = _run(base)
    assert rc == 0
    assert (arch / "2009" / "2009-04-14_old.tgz").is_file()
    assert not tgz.exists()


def test_reorganize_normalizes_zero_segments(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    entry = arch / "2003-00-00_invisible"
    entry.mkdir(parents=True)

    rc = _run(base)
    assert rc == 0
    assert (arch / "2003" / "2003-01-01_invisible").is_dir()
    assert not entry.exists()


def test_reorganize_normalizes_zero_day_only(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    entry = arch / "2008-09-00_phpmylogin.tgz"
    entry.parent.mkdir(parents=True)
    entry.write_bytes(b"x")

    rc = _run(base)
    assert rc == 0
    assert (arch / "2008" / "2008-09-01_phpmylogin.tgz").is_file()
    assert not entry.exists()


def test_reorganize_skips_entries_without_year_prefix(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    arch.mkdir(parents=True)
    odd = arch / "weird-no-date"
    odd.mkdir()

    rc = _run(base)
    assert rc == 0
    assert odd.is_dir()


def test_reorganize_is_idempotent(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    nested = arch / "2024" / "2024-05-01_x"
    nested.mkdir(parents=True)

    rc1 = _run(base)
    rc2 = _run(base)
    assert rc1 == 0
    assert rc2 == 0
    assert nested.is_dir()


def test_reorganize_dry_run_does_not_move(tmp_path: Path) -> None:
    base = tmp_path / "base"
    arch = base / "_archive"
    entry = arch / "2025-01-15_foo"
    entry.mkdir(parents=True)

    rc = _run(base, dry_run=True)
    assert rc == 0
    assert entry.is_dir()
    assert not (arch / "2025").exists()
