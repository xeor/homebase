from __future__ import annotations

import os
import time
from pathlib import Path

from homebase.cache import owner


def test_owner_lock_is_exclusive_and_records_holder(tmp_path: Path) -> None:
    first = owner.try_acquire_cache_owner(tmp_path, role="daemon")
    assert first is not None
    assert owner.read_cache_owner(tmp_path) == f"{os.getpid()} daemon"
    assert owner.try_acquire_cache_owner(tmp_path, role="tui") is None
    # A failed attempt leaves the holder's record alone.
    assert owner.read_cache_owner(tmp_path) == f"{os.getpid()} daemon"
    owner.release_cache_owner(first)
    second = owner.try_acquire_cache_owner(tmp_path, role="tui")
    assert second is not None
    assert owner.read_cache_owner(tmp_path) == f"{os.getpid()} tui"
    owner.release_cache_owner(second)


def test_release_tolerates_none_and_closed(tmp_path: Path) -> None:
    owner.release_cache_owner(None)
    handle = owner.try_flock(tmp_path / "x.lock", "1")
    assert handle is not None
    owner.release_cache_owner(handle)
    owner.release_cache_owner(handle)


def test_read_cache_owner_without_lock_file(tmp_path: Path) -> None:
    assert owner.read_cache_owner(tmp_path) == ""


def test_refresh_request_is_taken_once(tmp_path: Path) -> None:
    assert owner.take_cache_refresh_request(tmp_path) is None
    before = time.time() - 1
    owner.request_cache_refresh(tmp_path, "tag update")
    taken = owner.take_cache_refresh_request(tmp_path)
    assert taken is not None
    assert taken[0] == "tag update"
    assert taken[1] >= before
    assert owner.take_cache_refresh_request(tmp_path) is None


def test_empty_request_gets_default_reason(tmp_path: Path) -> None:
    owner.request_cache_refresh(tmp_path, "")
    taken = owner.take_cache_refresh_request(tmp_path)
    assert taken is not None and taken[0] == "requested"


def test_pid_alive() -> None:
    assert owner.pid_alive(os.getpid()) is True
    assert owner.pid_alive(0) is False
    assert owner.pid_alive(2**22 + 12345) is False


def test_peek_leaves_request_in_place(tmp_path: Path) -> None:
    assert owner.peek_cache_refresh_request(tmp_path) is None
    owner.request_cache_refresh(tmp_path, "tag update")
    assert owner.peek_cache_refresh_request(tmp_path) == "tag update"
    taken = owner.take_cache_refresh_request(tmp_path)
    assert taken is not None and taken[0] == "tag update"
    assert owner.peek_cache_refresh_request(tmp_path) is None
