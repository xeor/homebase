"""Controller core: diff desired (Profile) vs actual (ProfileSnapshot).

Pure planning — produces the resolved tab set and a summary. Backends execute
the plan; this module performs no IO. See IDEA.md "Reconcile algorithm".
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

from homebase_bts.models import GroupColor, MatchPolicy, Profile, TabSpec
from homebase_bts.protocol import ProfileSnapshot, SnapshotTab
from homebase_bts.urlnorm import normalize


@dataclass(frozen=True)
class ResolvedTab:
    """A desired tab mapped onto actual state."""

    url: str
    existing_tab_id: int | None  # reused browser_tab_id, or None => create


@dataclass
class Plan:
    group: str  # "new" | "existing"
    group_title: str
    focus: str
    tabs: list[ResolvedTab] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for t in self.tabs if t.existing_tab_id is None)

    @property
    def existing(self) -> int:
        return sum(1 for t in self.tabs if t.existing_tab_id is not None)

    @property
    def moved(self) -> int:
        return 0  # group-membership moves: modeled once snapshots carry groups

    @property
    def removed(self) -> int:
        return 0  # delete_missing handling: later MVP


@dataclass
class ApplyResult:
    """Outcome of an apply/dry-run, rendered uniformly across backends."""

    browser: str
    group: str  # "new" | "existing"
    group_title: str
    created: int
    existing: int
    moved: int
    removed: int
    focus: str
    applied: bool

    def render(self, title: str, *, source: Path | None = None) -> str:
        mode = "applied" if self.applied else "dry-run"
        return "\n".join(
            [
                title,
                f"  browser: {self.browser} ({mode})",
                f"  group:   {self.group} ({self.group_title})",
                f"  tabs:    {self.existing} existing, {self.created} created, "
                f"{self.moved} moved, {self.removed} removed",
                f"  focus:   {self.focus}",
                f"  file:    {source.name if source else '-'} (unchanged)",
            ]
        )


@dataclass
class MergeSummary:
    added: int = 0
    removed: int = 0
    kept: int = 0
    group_changed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.group_changed)


def merge_snapshot(profile: Profile, snapshot: ProfileSnapshot) -> tuple[Profile, MergeSummary]:
    """Merge actual browser state (snapshot) into the desired file (profile).

    Tabs are matched by their managed URL (the URL they were opened for, which
    survives redirects); the file's clean URLs/ids are preserved. New tabs are
    added in browser order; closed tabs are dropped only if sync.delete_missing.
    """
    file_tabs = list(profile.tabs)
    used = [False] * len(file_tabs)
    new_tabs: list[TabSpec] = []
    summary = MergeSummary()

    for snap in sorted(snapshot.tabs, key=lambda t: t.index):
        identity = snap.managed_url or snap.url
        if not identity:
            continue
        match_i = next(
            (
                i
                for i, ft in enumerate(file_tabs)
                if not used[i] and normalize(ft.url) == normalize(identity)
            ),
            None,
        )
        if match_i is not None:
            used[match_i] = True
            new_tabs.append(file_tabs[match_i])
            summary.kept += 1
        else:
            new_tabs.append(TabSpec(url=snap.url, title=snap.title))
            summary.added += 1

    closed = [ft for i, ft in enumerate(file_tabs) if not used[i]]
    if profile.sync.delete_missing:
        summary.removed = len(closed)
    else:
        new_tabs.extend(closed)

    new_group = profile.group
    if snapshot.group is not None:
        update: dict[str, object] = {}
        if snapshot.group.title is not None and snapshot.group.title != profile.group.title:
            update["title"] = snapshot.group.title
        if snapshot.group.color is not None and snapshot.group.color != profile.group.color.value:
            with contextlib.suppress(ValueError):
                update["color"] = GroupColor(snapshot.group.color)
        if (
            snapshot.group.collapsed is not None
            and snapshot.group.collapsed != profile.group.collapsed
        ):
            update["collapsed"] = snapshot.group.collapsed
        if update:
            new_group = profile.group.model_copy(update=update)
            summary.group_changed = True

    merged = profile.model_copy(update={"tabs": new_tabs, "group": new_group})
    return merged, summary


def result_from_plan(profile: Profile, p: Plan, *, applied: bool) -> ApplyResult:
    return ApplyResult(
        browser=profile.browser.preferred.value,
        group=p.group,
        group_title=p.group_title,
        created=p.created,
        existing=p.existing,
        moved=p.moved,
        removed=p.removed,
        focus=p.focus,
        applied=applied,
    )


def _tabs_match(desired: TabSpec, actual: SnapshotTab, policy: MatchPolicy) -> bool:
    if policy is MatchPolicy.exact_url:
        return desired.url == actual.url
    if (
        policy is MatchPolicy.title_url
        and desired.title is not None
        and actual.title is not None
        and desired.title == actual.title
    ):
        return True
    return normalize(desired.url) == normalize(actual.url)


def _find(
    desired: TabSpec, actual: list[SnapshotTab], policy: MatchPolicy, used: set[int]
) -> SnapshotTab | None:
    for tab in actual:
        if tab.browser_tab_id in used:
            continue
        if _tabs_match(desired, tab, policy):
            return tab
    return None


def plan(profile: Profile, snapshot: ProfileSnapshot | None) -> Plan:
    """Resolve every desired tab against actual state.

    snapshot is None when no managed group was found yet (must be created).
    """
    actual = snapshot.tabs if snapshot else []
    group_title = profile.group.title or profile.title or profile.id
    p = Plan(
        group="existing" if snapshot else "new",
        group_title=group_title,
        focus=profile.group.focus,
    )
    used: set[int] = set()

    for tab in profile.tabs:
        match = _find(tab, actual, profile.sync.match, used)
        existing_id = match.browser_tab_id if match else None
        if match:
            used.add(match.browser_tab_id)
        p.tabs.append(
            ResolvedTab(
                url=tab.url,
                existing_tab_id=existing_id,
            )
        )
    return p
