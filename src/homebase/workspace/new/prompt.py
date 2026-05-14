from __future__ import annotations

import sys


class PromptError(RuntimeError):
    """Raised when a `--ask-*` prompt is requested but stdin isn't a TTY."""


def _require_tty() -> None:
    if not sys.stdin.isatty():
        raise PromptError("requires an interactive terminal")


def ask_name(default: str | None = None) -> str:
    _require_tty()
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"name{suffix}: ").strip()
    except EOFError as exc:
        raise PromptError("no input") from exc
    if not raw:
        if default:
            return default
        raise PromptError("name required")
    return raw


def ask_source(available: list[str], default: str | None = None) -> str:
    _require_tty()
    options = "/".join(available)
    suffix = f" [{default}]" if default else ""
    try:
        raw = input(f"source ({options}){suffix}: ").strip()
    except EOFError as exc:
        raise PromptError("no input") from exc
    if not raw:
        if default:
            return default
        raise PromptError("source required")
    if raw not in available:
        raise PromptError(f"unknown source: {raw}")
    return raw


def confirm(message: str = "apply?") -> bool:
    _require_tty()
    try:
        raw = input(f"{message} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return raw in {"y", "yes"}
