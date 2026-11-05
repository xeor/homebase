from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from homebase.cache.clients import (
    ClientInfo,
    clients_dir,
    list_clients,
    register_client,
    unregister_client,
)


def _dead_pid() -> int:
    proc = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True, check=True)
    return int(proc.stdout)


def test_register_list_unregister(tmp_path: Path) -> None:
    me = ClientInfo(pid=os.getpid(), started_ts=10.0, tty="/dev/ttys001", cwd="/x")
    register_client(tmp_path, me)
    assert list_clients(tmp_path) == [me]
    unregister_client(tmp_path, os.getpid())
    unregister_client(tmp_path, os.getpid())  # already gone
    assert list_clients(tmp_path) == []


def test_list_drops_dead_and_broken_entries(tmp_path: Path) -> None:
    register_client(tmp_path, ClientInfo(pid=_dead_pid(), started_ts=1.0, tty="", cwd=""))
    (clients_dir(tmp_path) / "junk.json").write_text("{", encoding="utf-8")
    live = ClientInfo(pid=os.getpid(), started_ts=2.0, tty="", cwd="")
    register_client(tmp_path, live)
    assert list_clients(tmp_path) == [live]
    assert [p.name for p in clients_dir(tmp_path).iterdir()] == [f"{os.getpid()}.json"]


def test_list_without_dir(tmp_path: Path) -> None:
    assert list_clients(tmp_path) == []
