"""Backend interface. One implementation per (browser, transport)."""

from __future__ import annotations

from typing import Protocol

from homebase_bts.models import Profile
from homebase_bts.protocol import EnsureResult, ProfileSnapshot


class Backend(Protocol):
    """Drives a browser to match desired state and reads its actual state.

    Backends own only browser IO; all diff/merge/policy lives in reconcile.py.
    """

    name: str

    def available(self) -> bool:
        """Whether this backend can currently operate (browser/host present)."""
        ...

    def ensure(self, profile: Profile) -> EnsureResult:
        """Make the browser match the profile (idempotent)."""
        ...

    def focus(self, profile: Profile) -> EnsureResult:
        """Focus an existing profile without creating missing tabs."""
        ...

    def snapshot(self, profile_id: str) -> ProfileSnapshot:
        """Read current browser state for a profile."""
        ...
