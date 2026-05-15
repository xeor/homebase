from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..core.models import HookInfo, HookRuntime, HookTarget

AskCallable = Callable[..., str | None]
AddEventCallable = Callable[[Path, str, dict[str, object]], None]
NotifyCallable = Callable[[str, str], None]
StatusUpdateCallable = Callable[[str, str], None]
LogCallable = Callable[[str, str], None]


@dataclass(frozen=True)
class HookContext:
    event: str
    timing: str
    view: str
    base_dir: Path
    targets: tuple[HookTarget, ...]
    change: dict[str, object]
    runtime: HookRuntime
    hook: HookInfo
    add_event: AddEventCallable
    notify: NotifyCallable
    status_update: StatusUpdateCallable
    log: LogCallable
    ask: AskCallable
