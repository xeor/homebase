from __future__ import annotations

import pytest

from homebase.commands.help import TOPICS, cmd_help, cmd_help_hotkeys, list_topics
from homebase.config.workspace import load_keys
from homebase.core.constants import BUILTIN_HOTKEYS, reserved_hotkeys
from homebase.core.models import Action, KeyEntry


def _make_actions() -> dict[str, Action]:
    return {
        "open_code": Action(
            id="open_code",
            label="Open Code",
            kind="shell",
            scope="target",
            multi="joined",
            command="code {{ paths_q }}",
            source="config",
        ),
    }


def test_topics_lists_known_help_topics() -> None:
    assert "actions" in TOPICS
    assert "hotkeys" in TOPICS


def test_list_topics_prints_each_topic(capsys) -> None:
    rc = list_topics()
    out = capsys.readouterr().out
    assert rc == 0
    for topic in TOPICS:
        assert topic in out


def test_cmd_help_routes_topic_to_handler() -> None:
    calls: list[str] = []
    rc = cmd_help(
        "hotkeys",
        print_default_help=lambda: calls.append("default"),
        handlers={"hotkeys": lambda: (calls.append("hotkeys") or 0)},
    )
    assert rc == 0
    assert calls == ["hotkeys"]


def test_cmd_help_unknown_topic_lists_topics(capsys) -> None:
    rc = cmd_help(
        "bogus",
        print_default_help=lambda: print("DEFAULT"),
        handlers={"hotkeys": lambda: 0},
    )
    out = capsys.readouterr().out
    assert rc == 2
    assert "DEFAULT" in out
    assert "unknown help topic" in out


def test_cmd_help_hotkeys_emits_builtin_and_user(capsys) -> None:
    keys = {"f5": KeyEntry(action="open_code", label="")}
    rc = cmd_help_hotkeys(keys=keys)
    out = capsys.readouterr().out
    assert rc == 0
    assert "BUILT-IN" in out
    assert "ctrl+l" in out
    assert "cycle_tabs" in out
    assert "USER" in out
    assert "f5" in out
    assert "open_code" in out
    assert "RECOMMENDED" in out


def test_cmd_help_hotkeys_recommended_excludes_used_keys(capsys) -> None:
    keys = {"f5": KeyEntry(action="open_code")}
    cmd_help_hotkeys(keys=keys)
    out = capsys.readouterr().out
    # The recommended free function-keys line should NOT advertise f5
    # (it's taken by the user binding).
    fn_line = next(
        line for line in out.splitlines() if "function keys" in line
    )
    assert "f5" not in fn_line
    assert "f1" in fn_line


def test_cmd_help_hotkeys_works_with_empty_user_keys(capsys) -> None:
    rc = cmd_help_hotkeys(keys={})
    out = capsys.readouterr().out
    assert rc == 0
    assert "(none)" in out


def test_reserved_hotkeys_includes_all_builtins() -> None:
    reserved = reserved_hotkeys()
    for hk in BUILTIN_HOTKEYS:
        assert hk.key in reserved


def test_load_keys_rejects_collision_with_builtin() -> None:
    data = {"keys": {"ctrl+l": "open_code"}}
    with pytest.raises(ValueError, match="ctrl\\+l"):
        load_keys(data, actions=_make_actions())


def test_load_keys_rejects_collision_with_context_reserved() -> None:
    # space is reserved by select-mode toggle
    data = {"keys": {"space": "open_code"}}
    with pytest.raises(ValueError, match="space"):
        load_keys(data, actions=_make_actions())


def test_load_keys_accepts_free_slot() -> None:
    data = {"keys": {"f5": "open_code"}}
    out = load_keys(data, actions=_make_actions())
    assert out["f5"].action == "open_code"
