from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


@dataclass(frozen=True)
class BuiltinActionMeta:
    id: str
    default_label: str
    help_text: str
    scope: Literal["target", "workspace", "tab"]
    view_scope: tuple[str, ...]
    default_confirm_prompt: str | None
    kind: Literal["builtin"] = "builtin"


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    kind: Literal["builtin", "shell", "filepicker", "note", "tab"]
    scope: Literal["target", "workspace", "tab"]
    multi: Literal["joined", "per_row"]
    command: str | None = None
    list_command: str | None = None
    op: str | None = None
    confirm: bool | str | None = None
    hidden: bool = False
    view_scope: tuple[str, ...] = ("active", "archive")
    source: Literal["builtin", "config", "overridden"] = "builtin"


@dataclass(frozen=True)
class HotbarEntry:
    action: str
    label: str = ""
    style: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class KeyEntry:
    action: str
    label: str = ""


class RestoreTargetExistsError(ValueError):
    def __init__(self, source: Path, target: Path) -> None:
        self.source = source
        self.target = target
        super().__init__(f"target already exists: {target}")


@dataclass(frozen=True)
class PropertyDef:
    key: str
    label: str
    token: str
    color: str = ""
    matcher: Callable[[Path], bool] | None = None
    file_exists: tuple[str, ...] = ()
    dir_exists: tuple[str, ...] = ()
    path_exists: tuple[str, ...] = ()
    queries: tuple[dict[str, object], ...] = ()
    cache_ttl_s: float = 15.0
    cache_profile: str = ""
    cache_profiles_by_view: dict[str, dict[str, object]] | None = None

    def cache_ttl_for_view(self, view: str) -> float:
        if isinstance(self.cache_profiles_by_view, dict):
            profile = self.cache_profiles_by_view.get(view, {})
            if isinstance(profile, dict):
                try:
                    return max(1.0, float(profile.get("cache_ttl_s", self.cache_ttl_s)))
                except (TypeError, ValueError):
                    return max(1.0, float(self.cache_ttl_s))
        return max(1.0, float(self.cache_ttl_s))

    def matches(self, root: Path) -> bool:
        if self.matcher is not None:
            try:
                if self.matcher(root):
                    return True
            except (OSError, TypeError, ValueError):
                return False

        for rel in self.file_exists:
            if (root / rel).is_file():
                return True
        for rel in self.dir_exists:
            if (root / rel).is_dir():
                return True
        for rel in self.path_exists:
            if (root / rel).exists():
                return True
        return False


@dataclass(frozen=True)
class PostCommandOption:
    key: str
    label: str
    command: str


@dataclass
class ProjectRow:
    path: Path
    name: str
    branch: str
    dirty: str
    last: str
    src: str
    created: str
    tags: list[str]
    properties: list[str]
    description: str
    created_ts: int
    last_ts: int
    git_ts: int
    opened_ts: int
    is_fork: bool
    is_tmp: bool
    archived: bool
    restore_target: Path | None
    archived_ts: int
    wip: bool
    suffix: str | None
    packed: bool = False
    pack_format: str | None = None
    stale: bool = False
    cache_age_s: int = 0
    last_cached_ts: int = 0
    last_reconciled_ts: int = 0
    size_bytes: int = 0
    size_refresh_count: int = 0
    haystack_lower: str = ""
    tags_lower: frozenset[str] = frozenset()
    worktree_of: str = ""
    repo_dir: str = ""

    def __post_init__(self) -> None:
        if not self.tags_lower and self.tags:
            self.tags_lower = frozenset(str(tag).lower() for tag in self.tags)


@dataclass
class PaneRef:
    pane_id: str
    target: str
    window_name: str
    command: str
    cwd: Path
    active: bool


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    error: str | None = None

    @classmethod
    def success(cls) -> "OperationResult":
        return cls(True, None)

    @classmethod
    def failure(cls, error: str) -> "OperationResult":
        return cls(False, error)


@dataclass
class CacheRefreshOutcome:
    epoch: int
    fresh_active: list["ProjectRow"] | None
    fresh_archived: list["ProjectRow"] | None
    result: OperationResult


@dataclass
class ArchiveActionOutcome:
    action: str
    total: int
    success: int
    failed: int
    removed_paths: list[Path]
    upsert_rows: list["ProjectRow"]
    logs: list[tuple[str, str]]


@dataclass
class RegressionCaseResult:
    name: str
    ok: bool
    detail: str
    elapsed_s: float


@dataclass
class ManagedProcess:
    pid: int
    label: str
    command: str
    cwd: Path
    started_ts: float
    wait_mode: bool
    terminate_on_quit: bool
    returncode: int | None = None
    ended_ts: float = 0.0


@dataclass(frozen=True)
class HookSpec:
    timing: str
    event: str
    name: str
    source: str
    enabled: bool
    views: tuple[str, ...]
    config: dict[str, object]
    slow_warn_s: float
    refresh_enabled: bool = False
    refresh_min_interval_s: float = 60.0


@dataclass(frozen=True)
class HookTarget:
    path: Path
    name: str
    archived: bool
    tags: list[str]
    properties: list[str]
    description: str
    wip: bool
    suffix: str | None
    packed: bool
    base_meta: dict[str, object]
    last_modified_ts: int
    created_ts: int
    archived_ts: int
    git_branch: str
    git_dirty: str


@dataclass(frozen=True)
class HookRuntime:
    invoker: str
    homebase_version: str
    now_iso: str
    now_ts: int
    user: str


@dataclass(frozen=True)
class HookInfo:
    name: str
    source: str
    timing: str
    event: str
    config: dict[str, object]


@dataclass(frozen=True)
class PreResult:
    decision: str
    reason: str = ""
    mutated_change: dict[str, object] | None = None


@dataclass(frozen=True)
class PreOutcome:
    cancelled: bool
    reason: str
    change: dict[str, object]
