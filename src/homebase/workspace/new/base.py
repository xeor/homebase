from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar


@dataclass(frozen=True)
class NewOptions:
    tmp: bool = False
    timestamp: bool = False
    # Default to opening a shell in the new project — this is the
    # common case for ``b new``. Pass ``--no-open`` / ``--no-cd`` to
    # stay where you were.
    open: bool = True
    confirm: bool = False
    ts_name: bool = False
    alpha_name: bool = False
    ask_name: bool = False
    ask_source: bool = False
    archive: bool = False
    dry_run: bool = False
    yes: bool = False
    multi: bool = False
    template: str = ""
    tags: tuple[str, ...] = ()
    post: tuple[str, ...] = ()
    from_project: str = ""


@dataclass(frozen=True)
class NewConfig:
    """Source-specific structural config (not CLI-overridable)."""

    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass(frozen=True)
class NewContext:
    base_dir: Path
    cwd: Path


@dataclass
class NewPlan:
    source_key: str
    name: str
    target: Path
    steps: list[str]
    tags: list[str] = field(default_factory=list)
    template: str = ""
    post_commands: list[str] = field(default_factory=list)
    log_kind: str = "creation"
    log_payload: dict[str, Any] = field(default_factory=dict)
    signals: list[str] = field(default_factory=list)
    input: str | None = None
    open_shell: bool = False


@dataclass
class NewResult:
    target: Path
    open_shell: bool = False


class Source(ABC):
    key: ClassVar[str] = ""
    default_options: ClassVar[dict[str, Any]] = {}
    default_config: ClassVar[dict[str, Any]] = {}
    help_short: ClassVar[str] = ""
    supports_multi: ClassVar[bool] = True
    accepts_input: ClassVar[bool] = True
    """If False, the first CLI positional is treated as <name>, not <input>."""

    def __init__(self, config: NewConfig | None = None) -> None:
        self.config = config or NewConfig()

    def prepare(self, ns: object, ctx: NewContext) -> None:  # noqa: B027
        """Optional interactive setup hook, called after the source is
        constructed and options are resolved but before ``infer_name`` /
        ``plan``. Default: no-op. Subclasses can use this to prompt the
        user (e.g. ``DownloadedSource`` picks among recent files)."""
        return None

    @abstractmethod
    def detects(self, raw_input: str | None, ctx: NewContext) -> bool: ...

    @abstractmethod
    def infer_name(self, raw_input: str | None, ctx: NewContext) -> str | None: ...

    @abstractmethod
    def plan(
        self,
        raw_input: str | None,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan: ...

    @abstractmethod
    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult: ...
