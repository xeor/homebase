from __future__ import annotations

from typing import Any, Callable

from .actions import cmd_help_actions
from .hotkeys import cmd_help_hotkeys

HelpHandler = Callable[..., int]

TOPICS: dict[str, str] = {
    "actions": "list all known actions, their kind/scope, and current bindings",
    "hotkeys": "list every hotkey (built-in + custom) and recommended free slots",
}


def list_topics() -> int:
    print("usage: b help <topic>\n")
    print("topics:")
    width = max(len(t) for t in TOPICS)
    for name, desc in TOPICS.items():
        print(f"  {name.ljust(width)}  {desc}")
    return 0


def cmd_help(
    topic: str,
    *,
    print_default_help: Callable[[], None],
    handlers: dict[str, HelpHandler],
    **kwargs: Any,
) -> int:
    topic = topic.strip().lower()
    if not topic:
        print_default_help()
        return 0
    if topic == "topics":
        return list_topics()
    if topic not in handlers:
        print_default_help()
        print()
        print(f"unknown help topic: {topic!r}")
        return list_topics() or 2
    return handlers[topic](**kwargs)


__all__ = [
    "TOPICS",
    "cmd_help",
    "cmd_help_actions",
    "cmd_help_hotkeys",
    "list_topics",
]
