from __future__ import annotations

from datetime import timezone
from pathlib import Path

import pytest

from homebase.core import utils as core_utils


def test_resolve_base_dir_prefers_argument() -> None:
    resolved = core_utils.resolve_base_dir("~/base", env_base_folder="/tmp/ignored")
    assert resolved == (Path.home() / "base").resolve()


def test_resolve_base_dir_uses_env_when_no_argument() -> None:
    resolved = core_utils.resolve_base_dir(None, env_base_folder="~/workspace")
    assert resolved == (Path.home() / "workspace").resolve()


def test_fmt_age_short_uses_deterministic_now() -> None:
    assert core_utils.fmt_age_short(1_700_000_000, now_ts=1_700_000_000 + 3661) == "-1h1m"


def test_parse_archive_timestamp_supports_zulu() -> None:
    ts = core_utils.parse_archive_timestamp("2025-01-02T03:04:05Z", timezone.utc)
    assert ts > 0


def test_split_archive_name_uses_parser() -> None:
    def parse_suffix(value: str) -> int:
        return 123 if value == "stamp" else 0

    assert core_utils.split_archive_name("proj.stamp", parse_suffix) == ("proj", 123)
    assert core_utils.split_archive_name("proj.invalid", parse_suffix) == ("proj.invalid", 0)


def test_normalize_restore_target_rejects_outside_base(tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ValueError, match="outside base"):
        core_utils.normalize_restore_target(base_dir, outside)
