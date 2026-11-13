from __future__ import annotations

import sys
from pathlib import Path

from homebase.core.startup_warm import (
    module_files,
    read_module_files,
    record_module_files,
    warm_files,
)


def test_module_files_includes_this_module_and_its_cache() -> None:
    paths = {path.name for path in module_files()}
    own = Path(sys.modules[__name__].__file__ or "")
    assert own.name in paths
    assert any(name.endswith(".pyc") for name in paths)


def test_record_and_read_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "state" / "startup-files.txt"
    count = record_module_files(target)
    recorded = read_module_files(target)
    assert count == len(recorded) > 0
    assert set(recorded) == set(module_files())


def test_record_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    target = tmp_path / "startup-files.txt"
    record_module_files(target)
    assert [item.name for item in tmp_path.iterdir()] == [target.name]


def test_read_missing_list_is_empty(tmp_path: Path) -> None:
    assert read_module_files(tmp_path / "nope.txt") == []


def test_record_into_unwritable_path_reports_nothing(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    assert record_module_files(blocker / "list.txt") == 0


def test_warm_files_counts_bytes_and_skips_missing(tmp_path: Path) -> None:
    present = tmp_path / "a.py"
    present.write_bytes(b"x" * 2048)
    files, size = warm_files([present, tmp_path / "gone.py", tmp_path])
    assert (files, size) == (1, 2048)
