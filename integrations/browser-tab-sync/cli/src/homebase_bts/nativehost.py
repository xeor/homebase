"""Native messaging host entrypoint.

Launched by the browser, not the user. Bridges two channels:

  - native messaging: length-prefixed JSON frames on stdin/stdout to the
    extension (Chrome owns this process's lifecycle).
  - a unix socket (config.host_sock()) that short-lived `homebase-bts`
    commands connect to.

A request from the CLI is forwarded to the extension and the matching reply
(by request_id) is routed back to that CLI connection. Nothing but native
messaging frames may go to stdout — logs go to a file. Exits when stdin closes
(browser gone).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from homebase_bts import config, profileio, reconcile
from homebase_bts.protocol import (
    EnsureResult,
    Message,
    ProfileSnapshot,
    StartWatch,
    WatchProfile,
    encode_frame,
    read_frame,
)

log = logging.getLogger("homebase_bts.host")

REPLY_TIMEOUT = 30.0


class Bridge:
    def __init__(self) -> None:
        self.pending: dict[str, asyncio.Future[Message]] = {}
        # profile_id -> (file_path, group_title): persistent host-side sync targets
        self.sync_targets: dict[str, tuple[Path, str]] = {}
        # profile_id -> read-only debug connections (receive raw snapshots)
        self.debug_subscribers: dict[str, list[asyncio.StreamWriter]] = {}
        self._stdout = sys.stdout.buffer
        self._load_targets()

    def _to_extension(self, msg: Message) -> None:
        self._stdout.write(encode_frame(msg))
        self._stdout.flush()

    def _load_targets(self) -> None:
        store = config.sync_store()
        if not store.exists():
            return
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.exception("could not read sync store %s", store)
            return
        for pid, entry in data.items():
            try:
                self.sync_targets[pid] = _validate_sync_target(
                    pid, entry["file_path"], entry["group_title"]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
                OSError,
                ValidationError,
                json.JSONDecodeError,
            ):
                log.exception("invalid sync target profile=%s", pid)

    def _save_targets(self) -> None:
        data = {
            pid: {"file_path": str(path), "group_title": title}
            for pid, (path, title) in self.sync_targets.items()
        }
        with contextlib.suppress(OSError):
            _write_json_atomic(config.sync_store(), data)

    def rearm(self) -> None:
        """Re-tell the extension to observe every persisted sync target."""
        for pid, (_path, title) in self.sync_targets.items():
            log.info("re-arming sync profile=%s", pid)
            self._to_extension(StartWatch(request_id="rearm", profile_id=pid, group_title=title))

    async def handle_cli(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            msg = await read_frame(reader)
        except (asyncio.IncompleteReadError, ValueError) as exc:
            log.warning("bad CLI request: %s", exc)
            writer.close()
            return

        if isinstance(msg, WatchProfile):
            await self._handle_watch(msg, reader, writer)
            return

        request_id = getattr(msg, "request_id", None) or ""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Message] = loop.create_future()
        self.pending[request_id] = future
        log.info("CLI -> extension %s id=%s", msg.type, request_id)
        self._to_extension(msg)

        reply: Message
        try:
            reply = await asyncio.wait_for(future, timeout=REPLY_TIMEOUT)
        except TimeoutError:
            reply = EnsureResult(request_id=request_id, ok=False, error="extension timeout")
        finally:
            self.pending.pop(request_id, None)

        writer.write(encode_frame(reply))
        with contextlib.suppress(ConnectionError):
            await writer.drain()
        writer.close()

    async def _handle_watch(
        self, msg: WatchProfile, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._to_extension(
            StartWatch(
                request_id=msg.request_id, profile_id=msg.profile_id, group_title=msg.group_title
            )
        )
        if msg.debug:
            # Read-only viewer: stream raw snapshots while connected, write nothing.
            self.debug_subscribers.setdefault(msg.profile_id, []).append(writer)
            log.info("debug subscribe profile=%s", msg.profile_id)
            try:
                await reader.read()  # blocks until the CLI disconnects
            finally:
                conns = self.debug_subscribers.get(msg.profile_id, [])
                if writer in conns:
                    conns.remove(writer)
                writer.close()
            return

        # Persistent sync target (fire-and-forget): host writes the file.
        if msg.file_path:
            try:
                target = _validate_sync_target(msg.profile_id, msg.file_path, msg.group_title)
            except (OSError, ValidationError, json.JSONDecodeError, ValueError) as exc:
                log.warning(
                    "invalid sync target profile=%s file=%s: %s",
                    msg.profile_id,
                    msg.file_path,
                    exc,
                )
                writer.write(
                    encode_frame(EnsureResult(request_id=msg.request_id, ok=False, error=str(exc)))
                )
                with contextlib.suppress(ConnectionError):
                    await writer.drain()
                writer.close()
                return
            self.sync_targets[msg.profile_id] = target
            self._save_targets()
            writer.write(encode_frame(EnsureResult(request_id=msg.request_id, ok=True)))
            with contextlib.suppress(ConnectionError):
                await writer.drain()
            log.info("sync enabled profile=%s file=%s", msg.profile_id, target[0])
        writer.close()

    async def read_extension(self, reader: asyncio.StreamReader) -> None:
        while True:
            try:
                msg = await read_frame(reader)
            except asyncio.IncompleteReadError:
                log.info("stdin closed; browser gone")
                return
            except ValueError as exc:
                log.warning("bad extension frame: %s", exc)
                return
            if isinstance(msg, ProfileSnapshot):
                await self._on_snapshot(msg)
                continue
            request_id = getattr(msg, "request_id", None)
            future = self.pending.get(request_id) if request_id else None
            if future and not future.done():
                future.set_result(msg)
            else:
                log.debug("unsolicited message from extension: %s", msg.type)

    async def _on_snapshot(self, snapshot: ProfileSnapshot) -> None:
        target = self.sync_targets.get(snapshot.profile_id)
        if target is not None:
            self._sync_to_file(target[0], snapshot)
        await self._forward_to_debug(snapshot)

    async def _forward_to_debug(self, snapshot: ProfileSnapshot) -> None:
        frame = encode_frame(snapshot)
        for writer in list(self.debug_subscribers.get(snapshot.profile_id, [])):
            with contextlib.suppress(ConnectionError):
                writer.write(frame)
                await writer.drain()

    def _sync_to_file(self, path: Path, snapshot: ProfileSnapshot) -> None:
        try:
            current = profileio.load(path)
            merged, summary = reconcile.merge_snapshot(current, snapshot)
            if current.model_dump() == merged.model_dump():
                return
            profileio.write_atomic(path, merged)
        except (OSError, ValidationError, json.JSONDecodeError):
            log.exception("sync failed for %s", path)
            return
        log.info(
            "synced profile=%s file=%s +%d -%d group=%s tabs=%d",
            snapshot.profile_id,
            path.name,
            summary.added,
            summary.removed,
            summary.group_changed,
            len(merged.tabs),
        )


def _setup_logging() -> None:
    config.ensure_dirs()
    logging.basicConfig(
        filename=str(config.log_file()),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _validate_sync_target(profile_id: str, file_path: str, group_title: str) -> tuple[Path, str]:
    path = Path(file_path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"sync target is not a file: {path}")
    profile = profileio.load(path)
    if profile.id != profile_id:
        raise ValueError(f"sync target profile id mismatch: {profile.id!r} != {profile_id!r}")
    if not group_title:
        raise ValueError("sync target group title is empty")
    return path, group_title


def _write_json_atomic(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise


async def amain() -> None:
    _setup_logging()
    sock_path = config.host_sock()
    with contextlib.suppress(FileNotFoundError):
        os.unlink(sock_path)

    bridge = Bridge()
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    server = await asyncio.start_unix_server(bridge.handle_cli, path=str(sock_path))
    os.chmod(sock_path, 0o600)
    log.info("native host started; socket=%s", sock_path)
    bridge.rearm()  # re-tell the extension to observe persisted sync targets
    try:
        async with server:
            await bridge.read_extension(reader)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(sock_path)
        log.info("native host stopped")


def main() -> None:
    asyncio.run(amain())
