"""Extension-free macOS fallback (AppleScript/JXA/chrome-cli). MVP 5.

Supports open/find/focus/list and one-window-per-profile. Cannot robustly
control native tab groups (title/color/collapsed/membership).
"""

from __future__ import annotations

from homebase_bts.models import Profile
from homebase_bts.protocol import EnsureResult, ProfileSnapshot


class MacOSAutomationBackend:
    name = "macos-automation"

    def __init__(self, browser: str) -> None:
        self.browser = browser

    def available(self) -> bool:
        raise NotImplementedError("MVP 5")

    def ensure(self, profile: Profile) -> EnsureResult:
        raise NotImplementedError("MVP 5")

    def focus(self, profile_id: str) -> EnsureResult:
        raise NotImplementedError("MVP 5")

    def snapshot(self, profile_id: str) -> ProfileSnapshot:
        raise NotImplementedError("MVP 5")
