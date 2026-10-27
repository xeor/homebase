from __future__ import annotations

import json
import shutil
import socket
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from homebase.herdr import client


@pytest.fixture
def server() -> Iterator[tuple[Path, list[dict[str, object]], list[bytes]]]:
    """A one-reply-per-connection unix socket server, like herdr's.
    Lives under /tmp because socket paths are limited to ~100 chars."""
    root = Path(tempfile.mkdtemp(prefix="hb-herdr-", dir="/tmp"))
    path = root / "s.sock"
    seen: list[dict[str, object]] = []
    replies: list[bytes] = []
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    listener.listen()

    def serve() -> None:
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            with conn, conn.makefile("rb") as reader:
                seen.append(json.loads(reader.readline()))
                conn.sendall(replies.pop(0) if replies else b"")

    threading.Thread(target=serve, daemon=True).start()
    yield path, seen, replies
    listener.close()
    shutil.rmtree(root, ignore_errors=True)


def test_is_inside_herdr_needs_env_and_pane(monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.is_inside_herdr() is False
    assert client.current_pane_id() == ""
    monkeypatch.setenv("HERDR_ENV", "1")
    assert client.is_inside_herdr() is False
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p2")
    monkeypatch.setenv("HERDR_WORKSPACE_ID", "w1")
    assert client.is_inside_herdr() is True
    assert client.current_pane_id() == "w1:p2"
    assert client.current_workspace_id() == "w1"


def test_socket_path_only_for_a_socket(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, server) -> None:
    assert client.socket_path() is None
    plain = tmp_path / "file"
    plain.write_text("x")
    monkeypatch.setenv("HERDR_SOCKET_PATH", str(plain))
    assert client.socket_path() is None
    monkeypatch.setenv("HERDR_SOCKET_PATH", str(server[0]))
    assert client.socket_path() == server[0]


def test_call_sends_request_and_returns_result(server) -> None:
    path, seen, replies = server
    replies.append(b'{"id":"homebase","result":{"type":"pane_list","panes":[]}}\n')
    assert client.call("pane.list", {"workspace_id": "w1"}, sock=path) == {
        "type": "pane_list",
        "panes": [],
    }
    assert seen == [{"id": "homebase", "method": "pane.list", "params": {"workspace_id": "w1"}}]


@pytest.mark.parametrize(
    ("reply", "message"),
    [
        (b'{"id":"x","error":{"code":"pane_not_found","message":"pane nope not found"}}\n', "pane nope not found"),
        (b'{"id":"x","error":{"code":"pane_not_found"}}\n', "pane_not_found"),
        (b"not json\n", "bad reply"),
        (b"[1]\n", "bad reply"),
        (b'{"id":"x"}\n', "no result"),
    ],
)
def test_call_raises_on_bad_replies(server, reply: bytes, message: str) -> None:
    path, _seen, replies = server
    replies.append(reply)
    with pytest.raises(client.HerdrError, match=message):
        client.call("pane.get", {"pane_id": "nope"}, sock=path)


def test_call_without_server(tmp_path: Path) -> None:
    with pytest.raises(client.HerdrError, match="not running"):
        client.call("pane.list")
    with pytest.raises(client.HerdrError, match="pane.list"):
        client.call("pane.list", sock=tmp_path / "missing.sock")
