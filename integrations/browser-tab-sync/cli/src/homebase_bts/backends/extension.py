"""Chrome/Vivaldi backend via the extension over native messaging.

The CLI process is not the native host (the browser launches that). This
backend reaches the running extension through the host's local channel; the
plumbing is implemented alongside nativehost.py in a later MVP.
"""

from __future__ import annotations

from homebase_bts.models import Profile
from homebase_bts.protocol import EnsureResult, ProfileSnapshot


class ExtensionBackend:
    name = "extension"

    def __init__(self, browser: str) -> None:
        self.browser = browser

    def available(self) -> bool:
        raise NotImplementedError("MVP 1")

    def ensure(self, profile: Profile) -> EnsureResult:
        raise NotImplementedError("MVP 1")

    def focus(self, profile_id: str) -> EnsureResult:
        raise NotImplementedError("MVP 1")

    def snapshot(self, profile_id: str) -> ProfileSnapshot:
        raise NotImplementedError("MVP 2")
