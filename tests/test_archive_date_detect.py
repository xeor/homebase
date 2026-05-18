from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from homebase.archive import date_detect
from homebase.core import utils as core_utils

_TZ = timezone.utc

_HAS_GIT = shutil.which("git") is not None
_requires_git = pytest.mark.skipif(not _HAS_GIT, reason="git not available")


def _parse_ts(value: str) -> int:
    return core_utils.parse_archive_timestamp(value, _TZ)


def test_detect_canonical_prefix(tmp_path: Path) -> None:
    d = tmp_path / "2024-03-15_my-thing"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-prefix"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2024-03-15"


def test_detect_invalid_prefix_falls_through(tmp_path: Path) -> None:
    d = tmp_path / "2024-13-99_bogus"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    # Embedded regex picks up the digits but rejects invalid date → None
    assert out is None or out.kind != "name-prefix"


def test_detect_legacy_suffix(tmp_path: Path) -> None:
    d = tmp_path / "thing.20240101T120000"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind in {"name-parse", "name-suffix"}
    assert datetime.fromtimestamp(out.ts, tz=_TZ).year == 2024


def test_detect_embedded_in_name(tmp_path: Path) -> None:
    d = tmp_path / "report-20220815-final"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2022-08-15"


def test_detect_mtime_fallback(tmp_path: Path) -> None:
    d = tmp_path / "thing-with-no-date-in-name"
    d.mkdir()
    f = d / "file.txt"
    f.write_text("x")
    ts = int(datetime(2021, 5, 10, tzinfo=_TZ).timestamp())
    os.utime(f, (ts, ts))
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "mtime"
    assert abs(out.ts - ts) < 2


def test_detect_mtime_skips_dotfile_and_underscore_entries(tmp_path: Path) -> None:
    d = tmp_path / "no-date"
    d.mkdir()
    # Dotfile and `_`-prefixed file should both be ignored even though
    # their mtimes are newer than the winning regular file.
    dotted = d / ".env"
    dotted.write_text("x")
    underscored = d / "_scratch.log"
    underscored.write_text("x")
    recent = int(datetime(2030, 1, 1, tzinfo=_TZ).timestamp())
    os.utime(dotted, (recent, recent))
    os.utime(underscored, (recent, recent))
    visible = d / "code.py"
    visible.write_text("x")
    target_ts = int(datetime(2019, 8, 1, tzinfo=_TZ).timestamp())
    os.utime(visible, (target_ts, target_ts))
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert abs(out.ts - target_ts) < 2


def test_detect_mtime_skips_directories_and_folder_itself(tmp_path: Path) -> None:
    d = tmp_path / "no-date"
    d.mkdir()
    # A subdir with a much-newer mtime — the directory itself must not
    # contribute. The folder's own mtime must not contribute either.
    sub = d / "sub"
    sub.mkdir()
    recent_dir_ts = int(datetime(2030, 1, 1, tzinfo=_TZ).timestamp())
    os.utime(sub, (recent_dir_ts, recent_dir_ts))
    os.utime(d, (recent_dir_ts, recent_dir_ts))
    file_in_sub = sub / "note.md"
    file_in_sub.write_text("x")
    sub_file_ts = int(datetime(2020, 6, 1, tzinfo=_TZ).timestamp())
    os.utime(file_in_sub, (sub_file_ts, sub_file_ts))
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    # Top-level had no eligible regular files, so one-level-deep wins.
    assert out is not None
    assert abs(out.ts - sub_file_ts) < 2


def test_detect_mtime_one_level_deep_only(tmp_path: Path) -> None:
    """Files two levels deep must not be considered."""
    d = tmp_path / "deep"
    deep = d / "a" / "b"
    deep.mkdir(parents=True)
    f = deep / "buried.txt"
    f.write_text("x")
    os.utime(f, (int(datetime(2030, 1, 1, tzinfo=_TZ).timestamp()),) * 2)
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is None


def test_detect_year_only_in_name(tmp_path: Path) -> None:
    d = tmp_path / "something 2022"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-year"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2022-01-01"


def test_detect_year_only_picks_most_recent(tmp_path: Path) -> None:
    d = tmp_path / "talk-2020-rev-2023"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    # 2020-2023 are both valid years; the largest wins.
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2023-01-01"


def test_detect_year_only_with_underscore_separator(tmp_path: Path) -> None:
    d = tmp_path / "proj_2019_notes"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-year"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2019-01-01"


@_requires_git
def test_detect_git_head_wins(tmp_path: Path) -> None:
    d = tmp_path / "repo-with-commit"
    d.mkdir()
    # Initialise a minimal git repo and make a commit with a fixed
    # committer date. Using env vars avoids depending on the user's
    # git identity.
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_AUTHOR_DATE": "2022-07-04T12:00:00Z",
        "GIT_COMMITTER_DATE": "2022-07-04T12:00:00Z",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    (d / "main.rs").write_text("fn main(){}")
    subprocess.run(["git", "add", "."], cwd=d, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init", "--no-gpg-sign"],
        cwd=d, check=True, env=env,
    )

    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "git"
    iso = datetime.fromtimestamp(out.ts, tz=_TZ).strftime("%Y-%m-%d")
    assert iso == "2022-07-04"


@_requires_git
def test_detect_git_head_beats_name_year(tmp_path: Path) -> None:
    """Git takes priority over name-year — even when the folder name
    has a clear year, the HEAD commit's date wins."""
    d = tmp_path / "thing 2010"
    d.mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_AUTHOR_DATE": "2024-09-09T00:00:00Z",
        "GIT_COMMITTER_DATE": "2024-09-09T00:00:00Z",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True, env=env)
    (d / "f").write_text("x")
    subprocess.run(["git", "add", "."], cwd=d, check=True, env=env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "x", "--no-gpg-sign"],
        cwd=d, check=True, env=env,
    )

    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "git"
    iso = datetime.fromtimestamp(out.ts, tz=_TZ).strftime("%Y-%m-%d")
    assert iso == "2024-09-09"


def test_detect_git_marker_without_commit_falls_through(tmp_path: Path) -> None:
    """A bogus ``.git/`` (no real repo) must not stop detection — the
    git probe returns None, and the rest of the chain runs."""
    d = tmp_path / "fake-repo"
    d.mkdir()
    (d / ".git").mkdir()
    (d / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    visible = d / "code.py"
    visible.write_text("x")
    target_ts = int(datetime(2018, 3, 5, tzinfo=_TZ).timestamp())
    os.utime(visible, (target_ts, target_ts))

    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "mtime"
    assert abs(out.ts - target_ts) < 2


def test_detect_returns_none_when_empty(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is None


def test_parse_user_date_strict() -> None:
    assert date_detect.parse_user_date("2024-03-15", _TZ) is not None
    assert date_detect.parse_user_date("2024-3-15", _TZ) is None
    assert date_detect.parse_user_date("2024-13-01", _TZ) is None
    assert date_detect.parse_user_date("not-a-date", _TZ) is None
    assert date_detect.parse_user_date("", _TZ) is None
    assert date_detect.parse_user_date("  2024-03-15  ", _TZ) is not None


def test_strip_date_prefix() -> None:
    assert date_detect.strip_date_prefix("2024-03-15_foo") == "foo"
    assert date_detect.strip_date_prefix("foo") == "foo"
    # A date-only name returns an empty stem; callers fall back to
    # using the original name.
    assert date_detect.strip_date_prefix("2024-03-15") == ""


def test_strip_date_prefix_handles_space_and_other_separators() -> None:
    assert date_detect.strip_date_prefix("2024-03-15 foo") == "foo"
    assert date_detect.strip_date_prefix("2024-03-15-foo") == "foo"
    assert date_detect.strip_date_prefix("2024-03-15.foo") == "foo"
    assert date_detect.strip_date_prefix("2024-03-15_b-rs") == "b-rs"


def test_detect_with_space_separator(tmp_path: Path) -> None:
    d = tmp_path / "2026-05-18 mappe"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-prefix"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2026-05-18"


def test_detect_with_zero_segments_loose_pass(tmp_path: Path) -> None:
    d = tmp_path / "2003-00-00_invisible"
    d.mkdir()
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-prefix-loose"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2003-01-01"


def test_detect_tgz_suffix_is_stripped(tmp_path: Path) -> None:
    f = tmp_path / "2024-05-01_old.tgz"
    f.write_bytes(b"x")
    out = date_detect.detect_folder_date(f, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    assert out.kind == "name-prefix"
    assert datetime.fromtimestamp(out.ts, tz=_TZ).date().isoformat() == "2024-05-01"
