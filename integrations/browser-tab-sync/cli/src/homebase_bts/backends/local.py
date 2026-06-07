"""File-backed local browser simulator.

A development/test backend that runs the full file -> plan -> apply ->
idempotent re-apply loop without a real browser. State is persisted as JSON so
re-running across processes shows the same idempotency a real browser would.

Drop-in target: swap for ExtensionBackend once native messaging is wired.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, cast

from homebase_bts.models import Profile
from homebase_bts.protocol import ProfileSnapshot, SnapshotTab
from homebase_bts.reconcile import ApplyResult, Plan, plan, result_from_plan

_Store = dict[str, dict[str, Any]]


class LocalBackend:
    name = "local"

    def __init__(self, store: Path) -> None:
        self.store = store

    def available(self) -> bool:
        return True

    def apply(self, profile: Profile, *, dry_run: bool) -> ApplyResult:
        p = plan(profile, self.snapshot(profile.id))
        if not dry_run:
            self.commit(profile, p)
        return result_from_plan(profile, p, applied=not dry_run)

    def _read(self) -> _Store:
        if not self.store.exists():
            return {}
        return cast(_Store, json.loads(self.store.read_text(encoding="utf-8")))

    def _write(self, data: _Store) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(data, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(
            dir=self.store.parent, prefix=f".{self.store.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.store)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def snapshot(self, profile_id: str) -> ProfileSnapshot | None:
        entry = self._read().get(profile_id)
        if entry is None:
            return None
        tabs = [SnapshotTab(**t) for t in entry["tabs"]]
        return ProfileSnapshot(
            profile_id=profile_id,
            browser="local",
            window_id=entry.get("window_id"),
            group_id=entry.get("group_id"),
            tabs=tabs,
        )

    def commit(self, profile: Profile, plan: Plan) -> None:
        """Materialize the resolved tab set into the simulated browser."""
        data = self._read()
        entry = data.get(profile.id, {"group_id": None, "next_tab_id": 1, "tabs": []})
        next_id = int(entry["next_tab_id"])
        if entry["group_id"] is None:
            entry["group_id"] = next_id
            next_id += 1

        tabs = []
        for index, resolved in enumerate(plan.tabs):
            tab_id = resolved.existing_tab_id
            if tab_id is None:
                tab_id = next_id
                next_id += 1
            tabs.append(
                {
                    "browser_tab_id": tab_id,
                    "url": resolved.url,
                    "active": False,
                    "index": index,
                }
            )

        entry["next_tab_id"] = next_id
        entry["tabs"] = tabs
        data[profile.id] = entry
        self._write(data)
