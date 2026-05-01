from __future__ import annotations

import sys
from typing import Callable

PROMPT_CANCEL_TOKENS = {"q", "quit", "exit", "cancel", "abort"}


def prompt_readline(
    prompt: str,
    *,
    default: str | None = None,
    non_interactive_default: str | None = None,
) -> str | None:
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        try:
            raw = input(prompt)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return None
        except EOFError:
            return default
    else:
        try:
            raw = sys.stdin.readline()
        except OSError:
            raw = ""
        if raw == "" and non_interactive_default is not None:
            return non_interactive_default
        if raw == "":
            return default

    text = raw.strip()
    if not text:
        return default
    if text.lower() in PROMPT_CANCEL_TOKENS:
        return None
    return text


def prompt_yes_no(question: str, *, default: bool, read: Callable[..., str | None]) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    while True:
        raw = read(
            f"{question} {suffix} ",
            default="",
            non_interactive_default="",
        )
        if raw is None:
            return False
        answer = raw.strip().lower()
        if not answer:
            if not interactive:
                print(f"{question} {suffix} -> non-interactive, using default")
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        if not interactive:
            print(f"{question} {suffix} -> invalid non-interactive answer, using default")
            return default
        print("Please answer y or n.")


def confirm(read: Callable[..., str | None]) -> None:
    answer = read(
        "\npress enter to confirm, ^C to abort: ",
        default="",
        non_interactive_default="",
    )
    if answer is None:
        raise KeyboardInterrupt
