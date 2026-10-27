"""Registry of running `b` TUIs, so `b daemon` can show who uses the cache.

Each TUI writes ``runtime/clients/<pid>.json`` while it runs. Files of
processes that died without cleaning up are dropped when listed."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from ..core.constants import CLIENTS_DIR_NAME
from .owner import pid_alive, runtime_dir


@dataclass(frozen=True)
class ClientInfo:
    pid: int
    started_ts: float
    tty: str
    cwd: str


def clients_dir(base_dir: Path) -> Path:
    return runtime_dir(base_dir) / CLIENTS_DIR_NAME


def _client_path(base_dir: Path, pid: int) -> Path:
    return clients_dir(base_dir) / f"{pid}.json"


def register_client(base_dir: Path, info: ClientInfo) -> None:
    path = _client_path(base_dir, info.pid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(info), sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def unregister_client(base_dir: Path, pid: int) -> None:
    try:
        _client_path(base_dir, pid).unlink()
    except FileNotFoundError:
        pass


def _read_client(path: Path) -> ClientInfo | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ClientInfo(
            pid=int(raw["pid"]),
            started_ts=float(raw["started_ts"]),
            tty=str(raw.get("tty", "")),
            cwd=str(raw.get("cwd", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def list_clients(base_dir: Path) -> list[ClientInfo]:
    """Live clients, oldest first. Stale files are removed."""
    try:
        paths = sorted(clients_dir(base_dir).glob("*.json"))
    except OSError:
        return []
    clients: list[ClientInfo] = []
    for path in paths:
        info = _read_client(path)
        if info is not None and pid_alive(info.pid):
            clients.append(info)
            continue
        try:
            path.unlink()
        except OSError:
            pass
    return sorted(clients, key=lambda c: c.started_ts)
