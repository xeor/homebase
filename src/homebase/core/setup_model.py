from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_SKIP = "SKIP"

_VALID_STATUSES = frozenset({STATUS_PASS, STATUS_WARN, STATUS_FAIL, STATUS_SKIP})


# --- intent enum for the apply phase ---------------------------------

INTENT_KEEP = "keep"  # selected, currently_correct → noop
INTENT_CREATE = "create"  # selected, not correct, apply_create available
INTENT_REMOVE = "remove"  # unselected, currently_present, apply_remove available
INTENT_ABSENT = "absent"  # unselected, not present → noop
INTENT_CANNOT_CREATE = "cannot_create"  # selected but no apply_create available
INTENT_CANNOT_REMOVE = "cannot_remove"  # unselected, present, no apply_remove


@dataclass(frozen=True)
class SetupCheck:
    id: str
    name: str
    status: str
    detail: str
    required: bool = False
    extra_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(f"SetupCheck.status invalid: {self.status!r}")


@dataclass
class SetupFix:
    id: str
    title: str
    description: str = ""
    currently_present: bool = False
    currently_correct: bool = False
    required: bool = False
    recommended: bool = False
    apply_create: Callable[[], None] | None = None
    apply_remove: Callable[[], None] | None = None
    requires: tuple[str, ...] = ()
    preview_create: tuple[str, ...] = ()
    preview_remove: tuple[str, ...] = ()
    current_state_text: str = ""

    @property
    def selected_default(self) -> bool:
        if self.currently_correct:
            return True
        return self.apply_create is not None and (self.required or self.recommended)

    def intent(self, *, selected: bool) -> str:
        if selected:
            if self.currently_correct:
                return INTENT_KEEP
            if self.apply_create is not None:
                return INTENT_CREATE
            return INTENT_CANNOT_CREATE
        if self.currently_present:
            if self.apply_remove is not None:
                return INTENT_REMOVE
            return INTENT_CANNOT_REMOVE
        return INTENT_ABSENT


@dataclass
class FixResult:
    id: str
    title: str
    intent: str
    success: bool
    error: str | None = None

    @property
    def changed(self) -> bool:
        return self.success and self.intent in {INTENT_CREATE, INTENT_REMOVE}

    @property
    def skipped(self) -> bool:
        return self.intent in {INTENT_KEEP, INTENT_ABSENT}


@dataclass(frozen=True)
class SetupContext:
    base_dir: Path
    bin_dir: Path
    homebase_dir: Path
    config_path: Path
    homebase_gitignore: Path
    target: Path
    dest_dir: Path
    dest: Path
    launcher_path: Path | None
    uv_bin: str | None
    git_bin: str | None
    tmux_bin: str | None
    tmuxp_bin: str | None
    runtime_ok: bool
    runtime_detail: str
    in_path: bool
    tmux_conf_path: Path
    tmux_conf_text: str
    expected_tmux_binding: str
    existing_tmux_binding_lines: tuple[str, ...]
    completion_shell: str
    completion_target: Path | None
    expected_completion: str
    completion_ok: bool
    shell_init_target: Path | None
    shell_init_rc: Path | None
    expected_shell_init: str
    shell_init_ok: bool
    update_cmd: str
    update_detail: str
    config_exists: bool
    config_valid: bool
    macos_fast_focus_installed: bool


@dataclass
class ApplyOutcome:
    """Returned from the Textual app to ``cmd_setup``.

    - ``action="exit"``: user wants to close setup completely
    - ``action="continue"``: user wants to keep editing — caller should
      refresh state and re-launch the app
    - ``action="cancel"``: user cancelled without applying anything
    """
    action: str
    results: list["FixResult"] = field(default_factory=list)


@dataclass
class SetupSummary:
    pass_count: int
    warn_count: int
    fail_count: int
    hard_fail: bool
    create_count: int = 0
    remove_count: int = 0
    keep_count: int = 0
    failed_count: int = 0
    selected_titles: list[str] = field(default_factory=list)
    succeeded_titles: list[str] = field(default_factory=list)
    failed_titles: list[str] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return 1 if self.hard_fail else 0


__all__ = [
    "ApplyOutcome",
    "FixResult",
    "INTENT_ABSENT",
    "INTENT_CANNOT_CREATE",
    "INTENT_CANNOT_REMOVE",
    "INTENT_CREATE",
    "INTENT_KEEP",
    "INTENT_REMOVE",
    "SetupCheck",
    "SetupContext",
    "SetupFix",
    "SetupSummary",
    "STATUS_FAIL",
    "STATUS_PASS",
    "STATUS_SKIP",
    "STATUS_WARN",
]
