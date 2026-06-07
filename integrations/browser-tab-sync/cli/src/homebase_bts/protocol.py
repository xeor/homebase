"""Native-messaging wire models. Mirror of schema/native-messaging.schema.json.

Frames on stdin/stdout: uint32 little-endian length prefix + UTF-8 JSON body.
"""

from __future__ import annotations

import asyncio
import socket
import struct
import sys
from typing import Annotated, BinaryIO, Literal

from pydantic import BaseModel, Field, TypeAdapter

from homebase_bts.models import Profile


class _Msg(BaseModel):
    request_id: str


class EnsureProfile(_Msg):
    type: Literal["ensure_profile"] = "ensure_profile"
    profile: Profile


class HealthCheck(_Msg):
    type: Literal["health_check"] = "health_check"


class FocusProfile(_Msg):
    type: Literal["focus_profile"] = "focus_profile"
    profile_id: str
    group_title: str
    focus: str = "first"


class SnapshotRequest(_Msg):
    type: Literal["snapshot_request"] = "snapshot_request"
    profile_id: str
    group_title: str


class WatchProfile(_Msg):
    """CLI -> host: observe a profile's group.

    debug=False registers a persistent sync target (host writes file_path on
    changes, survives restarts). debug=True is a read-only subscription: the host
    forwards snapshots to this connection and writes nothing.
    """

    type: Literal["watch_profile"] = "watch_profile"
    profile_id: str
    group_title: str
    file_path: str | None = None
    debug: bool = False


class StartWatch(_Msg):
    """Host -> extension: begin observing the managed group."""

    type: Literal["start_watch"] = "start_watch"
    profile_id: str
    group_title: str


class StopWatch(BaseModel):
    """Host -> extension: stop observing the managed group."""

    type: Literal["stop_watch"] = "stop_watch"
    profile_id: str


class SnapshotTab(BaseModel):
    browser_tab_id: int
    url: str
    managed_url: str | None = None  # desired URL the tab was opened for (survives redirects)
    title: str | None = None
    active: bool = False
    index: int


class SnapshotGroup(BaseModel):
    title: str | None = None
    color: str | None = None
    collapsed: bool | None = None


class ProfileSnapshot(BaseModel):
    type: Literal["profile_snapshot"] = "profile_snapshot"
    request_id: str | None = None
    profile_id: str
    browser: str
    window_id: int | None = None
    group_id: int | None = None
    group: SnapshotGroup | None = None
    tabs: list[SnapshotTab]


class EnsureResult(_Msg):
    type: Literal["ensure_result"] = "ensure_result"
    ok: bool
    error: str | None = None
    created_tabs: int = 0
    existing_tabs: int = 0
    moved_tabs: int = 0
    removed_tabs: int = 0
    group_created: bool = False
    focused: bool = False


Message = Annotated[
    EnsureProfile
    | HealthCheck
    | FocusProfile
    | SnapshotRequest
    | WatchProfile
    | StartWatch
    | StopWatch
    | ProfileSnapshot
    | EnsureResult,
    Field(discriminator="type"),
]
_adapter: TypeAdapter[Message] = TypeAdapter(Message)
MAX_FRAME_BYTES = 8 * 1024 * 1024


def _check_frame_length(length: int) -> None:
    if length > MAX_FRAME_BYTES:
        raise ValueError(f"native-messaging frame too large: {length} bytes")


def read_message(stream: BinaryIO = sys.stdin.buffer) -> Message | None:
    """Read one length-prefixed frame. None on clean EOF."""
    header = stream.read(4)
    if not header:
        return None
    if len(header) != 4:
        raise EOFError("truncated native-messaging length prefix")
    (length,) = struct.unpack("<I", header)
    _check_frame_length(length)
    body = stream.read(length)
    if len(body) != length:
        raise EOFError("truncated native-messaging body")
    return _adapter.validate_json(body)


def write_message(msg: Message, stream: BinaryIO = sys.stdout.buffer) -> None:
    body = msg.model_dump_json(by_alias=True).encode("utf-8")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


def encode_frame(msg: Message) -> bytes:
    """uint32 little-endian length prefix + UTF-8 JSON body."""
    body = _adapter.dump_json(msg, by_alias=True)
    return struct.pack("<I", len(body)) + body


def decode_frame(body: bytes) -> Message:
    return _adapter.validate_json(body)


async def read_frame(reader: asyncio.StreamReader) -> Message:
    """Read one frame from an asyncio stream. Raises IncompleteReadError on EOF."""
    header = await reader.readexactly(4)
    (length,) = struct.unpack("<I", header)
    _check_frame_length(length)
    body = await reader.readexactly(length)
    return _adapter.validate_json(body)


def _recv_exactly(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def send_frame(sock: socket.socket, msg: Message) -> None:
    sock.sendall(encode_frame(msg))


def recv_frame(sock: socket.socket) -> Message | None:
    """Read one frame from a blocking socket. None on clean EOF."""
    header = _recv_exactly(sock, 4)
    if header is None:
        return None
    (length,) = struct.unpack("<I", header)
    _check_frame_length(length)
    body = _recv_exactly(sock, length)
    if body is None:
        return None
    return decode_frame(body)
