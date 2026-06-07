import asyncio
import io
import json
import struct
from pathlib import Path

import pytest

from homebase_bts import config
from homebase_bts.models import Profile
from homebase_bts.nativehost import Bridge
from homebase_bts.protocol import (
    MAX_FRAME_BYTES,
    EnsureProfile,
    EnsureResult,
    WatchProfile,
    decode_frame,
    encode_frame,
    read_message,
)


class _FakeWriter:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buf.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _decode_writer_msg(writer: _FakeWriter) -> EnsureResult:
    (length,) = struct.unpack("<I", bytes(writer.buf[:4]))
    msg = decode_frame(bytes(writer.buf[4 : 4 + length]))
    assert isinstance(msg, EnsureResult)
    return msg


def _profile() -> Profile:
    return Profile.model_validate(
        {"schema": 1, "id": "vacation", "tabs": [{"url": "https://maps.google.com/"}]}
    )


async def _roundtrip() -> EnsureResult:
    bridge = Bridge()
    reader = asyncio.StreamReader()
    reader.feed_data(encode_frame(EnsureProfile(request_id="abc", profile=_profile())))
    reader.feed_eof()
    writer = _FakeWriter()

    def fake_to_extension(msg):
        # Simulate the extension replying to the forwarded request.
        bridge.pending[msg.request_id].set_result(
            EnsureResult(request_id=msg.request_id, ok=True, created_tabs=1, group_created=True)
        )

    bridge._to_extension = fake_to_extension  # type: ignore[method-assign]
    await bridge.handle_cli(reader, writer)

    reply = _decode_writer_msg(writer)
    assert writer.closed
    return reply


def _profile_file(path: Path, profile_id: str = "vacation") -> None:
    path.write_text(
        json.dumps({"schema": 1, "id": profile_id, "tabs": [{"url": "https://maps.google.com/"}]}),
        encoding="utf-8",
    )


async def _watch_roundtrip(profile_path: Path, profile_id: str = "vacation") -> EnsureResult:
    bridge = Bridge()
    reader = asyncio.StreamReader()
    reader.feed_data(
        encode_frame(
            WatchProfile(
                request_id="watch-1",
                profile_id=profile_id,
                group_title="Vacation",
                file_path=str(profile_path),
            )
        )
    )
    reader.feed_eof()
    writer = _FakeWriter()

    bridge._to_extension = lambda _msg: None  # type: ignore[method-assign]
    await bridge.handle_cli(reader, writer)
    return _decode_writer_msg(writer)


def test_bridge_forwards_request_and_routes_reply():
    reply = asyncio.run(_roundtrip())
    assert reply.ok
    assert reply.created_tabs == 1
    assert reply.group_created


def test_frame_round_trip():
    msg = EnsureResult(request_id="x", ok=True, created_tabs=3)
    frame = encode_frame(msg)
    (length,) = struct.unpack("<I", frame[:4])
    assert length == len(frame) - 4
    back = decode_frame(frame[4:])
    assert isinstance(back, EnsureResult)
    assert back.created_tabs == 3


def test_read_message_rejects_oversized_frame():
    stream = io.BytesIO(struct.pack("<I", MAX_FRAME_BYTES + 1))
    with pytest.raises(ValueError, match="frame too large"):
        read_message(stream)


def test_watch_registers_valid_sync_target(tmp_path, monkeypatch):
    store = tmp_path / "sync.json"
    monkeypatch.setattr(config, "sync_store", lambda: store)
    profile_path = tmp_path / "profile.json"
    _profile_file(profile_path)

    reply = asyncio.run(_watch_roundtrip(profile_path))
    assert reply.ok
    assert json.loads(store.read_text(encoding="utf-8")) == {
        "vacation": {"file_path": str(profile_path.resolve()), "group_title": "Vacation"}
    }


def test_watch_rejects_mismatched_sync_target(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "sync_store", lambda: tmp_path / "sync.json")
    profile_path = tmp_path / "profile.json"
    _profile_file(profile_path, profile_id="other")

    reply = asyncio.run(_watch_roundtrip(profile_path))
    assert not reply.ok
    assert "profile id mismatch" in (reply.error or "")
