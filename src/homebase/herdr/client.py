from __future__ import annotations

import json
import os
import socket
import stat
from pathlib import Path
from typing import Any, Callable

from ..core.constants import HERDR_CALL_TIMEOUT_S, HERDR_DEFAULT_SOCKET

# One request per connection: herdr answers a single JSON line and closes.
HerdrCall = Callable[[str, dict[str, Any]], dict[str, Any]]


class HerdrError(RuntimeError):
    """herdr is unreachable or answered with an error."""


def is_inside_herdr() -> bool:
    """True when this process runs inside a herdr pane."""
    return os.environ.get("HERDR_ENV", "") == "1" and bool(os.environ.get("HERDR_PANE_ID", ""))


def current_pane_id() -> str:
    return os.environ.get("HERDR_PANE_ID", "").strip() if is_inside_herdr() else ""


def current_workspace_id() -> str:
    return os.environ.get("HERDR_WORKSPACE_ID", "").strip() if is_inside_herdr() else ""


def socket_path() -> Path | None:
    """The herdr server socket, or None when no server is listening there."""
    raw = os.environ.get("HERDR_SOCKET_PATH", "").strip() or HERDR_DEFAULT_SOCKET
    path = Path(raw).expanduser()
    try:
        return path if stat.S_ISSOCK(path.stat().st_mode) else None
    except OSError:
        return None


def call(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    sock: Path | None = None,
    timeout: float = HERDR_CALL_TIMEOUT_S,
) -> dict[str, Any]:
    """Send one request and return its ``result`` object."""
    path = sock or socket_path()
    if path is None:
        raise HerdrError("herdr is not running")
    request = json.dumps({"id": "homebase", "method": method, "params": params or {}})
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(str(path))
            conn.sendall(request.encode("utf-8") + b"\n")
            with conn.makefile("rb") as reader:
                line = reader.readline()
    except OSError as exc:
        raise HerdrError(f"herdr {method}: {exc}") from exc
    try:
        reply = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HerdrError(f"herdr {method}: bad reply") from exc
    if not isinstance(reply, dict):
        raise HerdrError(f"herdr {method}: bad reply")
    error = reply.get("error")
    if isinstance(error, dict):
        raise HerdrError(f"herdr {method}: {error.get('message') or error.get('code') or 'error'}")
    result = reply.get("result")
    if not isinstance(result, dict):
        raise HerdrError(f"herdr {method}: no result")
    return result
