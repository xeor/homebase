from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homebase.commands import archive as commands_archive

_HAS_GIT = shutil.which("git") is not None
_requires_git = pytest.mark.skipif(not _HAS_GIT, reason="git not available")


def _make_base(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    base.mkdir()
    (base / ".homebase").mkdir()
    return base


def _setup_env(monkeypatch, base: Path) -> None:
    monkeypatch.setenv("BASE_DIR", str(base))
    monkeypatch.chdir(base)


def test_archive_mv_uses_mtime_when_no_date_in_name(
    tmp_path: Path, monkeypatch,
) -> None:
    """The default behavior: when name has no date and there's no
    ``.git/``, the newest regular file's mtime drives the archive
    date — *not* today."""
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "oldwork"
    proj.mkdir()
    (proj / ".base.yaml").write_text("")  # dotfile — skipped by detector
    src_file = proj / "notes.md"
    src_file.write_text("x")
    target_ts = int(datetime(2021, 3, 5, tzinfo=timezone.utc).timestamp())
    os.utime(src_file, (target_ts, target_ts))

    rc = commands_archive.cmd_archive_mv(base, ["oldwork"], yes=True)
    assert rc == 0
    assert not proj.exists()
    moved = base / "_archive" / "2021" / "2021-03-05_oldwork"
    assert moved.is_dir()


def test_archive_mv_picks_year_from_name(tmp_path: Path, monkeypatch) -> None:
    """When the folder name contains a plausible year (no full date),
    the year-only fallback should win and produce ``YYYY-01-01``."""
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "talk 2019"
    proj.mkdir()
    (proj / "slides.txt").write_text("x")

    rc = commands_archive.cmd_archive_mv(base, ["talk 2019"], yes=True)
    assert rc == 0
    moved = base / "_archive" / "2019" / "2019-01-01_talk 2019"
    assert moved.is_dir()


@_requires_git
def test_archive_mv_uses_git_head(tmp_path: Path, monkeypatch) -> None:
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "thing"
    proj.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_AUTHOR_DATE": "2023-11-20T08:00:00Z",
        "GIT_COMMITTER_DATE": "2023-11-20T08:00:00Z",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=proj, check=True, env=env)
    (proj / "main.py").write_text("x")
    subprocess.run(["git", "add", "."], cwd=proj, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init", "--no-gpg-sign"],
        cwd=proj, check=True, env=env,
    )

    rc = commands_archive.cmd_archive_mv(base, ["thing"], yes=True)
    assert rc == 0
    moved = base / "_archive" / "2023" / "2023-11-20_thing"
    assert moved.is_dir()


def test_archive_mv_falls_back_to_today_when_nothing_detected(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """No date in name, no git, no eligible regular files: with --yes
    we silently fall back to today."""
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "empty-proj"
    proj.mkdir()
    # Only a dotfile, which the detector skips. Nothing else.
    (proj / ".base.yaml").write_text("")

    rc = commands_archive.cmd_archive_mv(base, ["empty-proj"], yes=True)
    assert rc == 0
    today = datetime.now().strftime("%Y-%m-%d")
    year = today[:4]
    moved = base / "_archive" / year / f"{today}_empty-proj"
    assert moved.is_dir()
    out = capsys.readouterr().out
    assert "no date found" in out


def test_archive_mv_verbose_prints_trace(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """With ``HOMEBASE_VERBOSE=1`` the strategies that were tried and
    their outcomes are surfaced before the final ``date:`` line."""
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "something 2019"
    proj.mkdir()
    monkeypatch.setenv("HOMEBASE_VERBOSE", "1")

    rc = commands_archive.cmd_archive_mv(base, ["something 2019"], yes=True)
    assert rc == 0
    out = capsys.readouterr().out
    assert "date detection trace:" in out
    assert "git" in out
    assert "name-year" in out
    assert "match" in out
    assert "name year 2019" in out


def test_archive_mv_keeps_name_date_when_present(
    tmp_path: Path, monkeypatch,
) -> None:
    """A folder that already has a valid YYYY-MM-DD prefix keeps that
    date — name-prefix beats mtime in the detection chain."""
    base = _make_base(tmp_path)
    _setup_env(monkeypatch, base)
    proj = base / "2020-06-15_legacy"
    proj.mkdir()
    f = proj / "doc.txt"
    f.write_text("x")
    # mtime is from 2024 but the name-prefix from 2020 must win.
    recent = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp())
    os.utime(f, (recent, recent))

    rc = commands_archive.cmd_archive_mv(base, ["2020-06-15_legacy"], yes=True)
    assert rc == 0
    moved = base / "_archive" / "2020" / "2020-06-15_legacy"
    assert moved.is_dir()
