"""Native backend: talks to the Chrome-owned host over a unix socket.

The host (homebase-bts-host) is spawned by Chrome when the extension
connects, and listens on config.host_sock(). This backend sends one request,
reads one reply, and exits — fully ad-hoc, no daemon to maintain.
"""

from __future__ import annotations

import socket
import uuid
from pathlib import Path

from homebase_bts.models import Profile
from homebase_bts.protocol import (
    EnsureProfile,
    EnsureResult,
    FocusProfile,
    Message,
    ProfileSnapshot,
    SnapshotRequest,
    WatchProfile,
    recv_frame,
    send_frame,
)
from homebase_bts.reconcile import ApplyResult, plan, result_from_plan

REQUEST_TIMEOUT_SECONDS = 30.0
SNAPSHOT_TIMEOUT_SECONDS = 5.0


class HostUnavailable(RuntimeError):
    pass


class NativeBackend:
    name = "native"

    def __init__(self, sock_path: Path, *, timeout: float = REQUEST_TIMEOUT_SECONDS) -> None:
        self.sock_path = str(sock_path)
        self.timeout = timeout

    def available(self) -> bool:
        return Path(self.sock_path).exists()

    def _connect(self, timeout: float | None = None) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout or self.timeout)
        try:
            sock.connect(self.sock_path)
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            sock.close()
            raise HostUnavailable(
                "native host not reachable — is the browser running with the "
                "extension loaded? run `homebase-bts doctor`"
            ) from exc
        except TimeoutError as exc:
            sock.close()
            raise HostUnavailable("native host connection timed out") from exc
        return sock

    def _read_reply(self, sock: socket.socket, timeout: float) -> Message:
        try:
            reply = recv_frame(sock)
        except TimeoutError as exc:
            raise HostUnavailable(
                f"native host did not reply within {timeout:g}s; "
                "restart the browser/extension and run `homebase-bts doctor`"
            ) from exc
        if reply is None:
            raise HostUnavailable("native host closed the connection unexpectedly")
        return reply

    def enable_sync(self, profile_id: str, file_path: str, group_title: str) -> None:
        """Register persistent host-side two-way sync."""
        sock = self._connect()
        with sock:
            send_frame(
                sock,
                WatchProfile(
                    request_id=str(uuid.uuid4()),
                    profile_id=profile_id,
                    group_title=group_title,
                    file_path=file_path,
                ),
            )
            reply = self._read_reply(sock, self.timeout)
        if not isinstance(reply, EnsureResult):
            raise HostUnavailable(f"unexpected reply from host: {reply.type}")
        if not reply.ok:
            raise HostUnavailable(reply.error or "sync registration failed")

    def _roundtrip(self, msg: Message, *, timeout: float | None = None) -> Message:
        request_timeout = timeout or self.timeout
        sock = self._connect(request_timeout)
        with sock:
            send_frame(sock, msg)
            return self._read_reply(sock, request_timeout)

    def focus(self, profile: Profile) -> EnsureResult:
        reply = self._roundtrip(
            FocusProfile(
                request_id=str(uuid.uuid4()),
                profile_id=profile.id,
                group_title=profile.group.title or profile.title or profile.id,
                focus=profile.group.focus,
            )
        )
        if not isinstance(reply, EnsureResult):
            raise HostUnavailable(f"unexpected reply from host: {reply.type}")
        if not reply.ok:
            raise HostUnavailable(reply.error or "focus failed")
        return reply

    def snapshot(self, profile: Profile) -> ProfileSnapshot:
        reply = self._roundtrip(
            SnapshotRequest(
                request_id=str(uuid.uuid4()),
                profile_id=profile.id,
                group_title=profile.group.title or profile.title or profile.id,
            ),
            timeout=SNAPSHOT_TIMEOUT_SECONDS,
        )
        if isinstance(reply, EnsureResult):
            raise HostUnavailable(reply.error or "snapshot failed")
        if not isinstance(reply, ProfileSnapshot):
            raise HostUnavailable(f"unexpected reply from host: {reply.type}")
        return reply

    def apply(self, profile: Profile, *, dry_run: bool) -> ApplyResult:
        if dry_run:
            return result_from_plan(profile, plan(profile, self.snapshot(profile)), applied=False)
        reply = self._roundtrip(EnsureProfile(request_id=str(uuid.uuid4()), profile=profile))
        if not isinstance(reply, EnsureResult):
            raise HostUnavailable(f"unexpected reply from host: {reply.type}")
        if not reply.ok:
            raise HostUnavailable(reply.error or "ensure failed")
        return ApplyResult(
            browser=profile.browser.preferred.value,
            group="new" if reply.group_created else "existing",
            group_title=profile.group.title or profile.title or profile.id,
            created=reply.created_tabs,
            existing=reply.existing_tabs,
            moved=reply.moved_tabs,
            removed=reply.removed_tabs,
            focus=profile.group.focus,
            applied=True,
        )
