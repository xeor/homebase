from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from homebase.archive import date_detect
from homebase.core import utils as core_utils

_TZ = timezone.utc


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


def test_detect_mtime_skips_dotfiles(tmp_path: Path) -> None:
    d = tmp_path / "no-date"
    d.mkdir()
    (d / ".git").mkdir()
    (d / ".git" / "HEAD").write_text("ref: refs/heads/main")
    # Set .git file mtime to a recent time we don't want to win.
    recent = int(datetime(2030, 1, 1, tzinfo=_TZ).timestamp())
    os.utime(d / ".git" / "HEAD", (recent, recent))
    visible = d / "code.py"
    visible.write_text("x")
    target_ts = int(datetime(2019, 8, 1, tzinfo=_TZ).timestamp())
    os.utime(visible, (target_ts, target_ts))
    out = date_detect.detect_folder_date(d, parse_timestamp=_parse_ts, archive_tz=_TZ)
    assert out is not None
    # The .git file should be skipped, so the only mtime considered is
    # the visible file's.
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
    assert date_detect.strip_date_prefix("2024-03-15") == "2024-03-15"
