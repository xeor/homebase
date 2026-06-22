from __future__ import annotations

import os
import types
from pathlib import Path

from homebase.tmux import registry as tmux_registry


def test_register_and_load_current_tmux_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.setenv("TMUX_PANE", "%7")
    monkeypatch.setattr(os, "getpid", lambda: 123)

    tmux_registry.register_current_tmux_context(
        tmp_path,
        open_profile="tmux_tab_load_or_goto",
        project_panes={
            tmp_path / "project": [
                types.SimpleNamespace(
                    pane_id="%1",
                    target="main:2.0",
                    window_name="project",
                    command="fish",
                    cwd=tmp_path / "project",
                    active=True,
                )
            ]
        },
        now=10.0,
    )

    context = tmux_registry.load_active_tmux_context(tmp_path, now=11.0)
    assert context is not None
    assert context["socket_path"] == "/tmp/tmux-sock"
    assert context["tmux_pane"] == "%7"
    assert context["open_profile"] == "tmux_tab_load_or_goto"
    assert context["project_panes"] == {
        str((tmp_path / "project").resolve()): [
            {
                "active": True,
                "command": "fish",
                "cwd": str(tmp_path / "project"),
                "pane_id": "%1",
                "target": "main:2.0",
                "window_name": "project",
            }
        ]
    }


def test_load_active_tmux_context_ignores_stale_entries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.setattr(os, "getpid", lambda: 123)
    tmux_registry.register_current_tmux_context(tmp_path, now=10.0)

    assert tmux_registry.load_active_tmux_context(tmp_path, now=100.0) is None


def test_load_tmux_contexts_returns_newest_first(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TMUX", "/tmp/first,1,2")
    monkeypatch.setattr(os, "getpid", lambda: 123)
    tmux_registry.register_current_tmux_context(tmp_path, now=10.0)

    monkeypatch.setenv("TMUX", "/tmp/second,1,2")
    monkeypatch.setattr(os, "getpid", lambda: 456)
    tmux_registry.register_current_tmux_context(tmp_path, now=20.0)

    contexts = tmux_registry.load_tmux_contexts(tmp_path, now=21.0)

    assert [context["socket_path"] for context in contexts] == [
        "/tmp/second",
        "/tmp/first",
    ]


def test_unregister_current_tmux_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TMUX", "/tmp/tmux-sock,1,2")
    monkeypatch.setattr(os, "getpid", lambda: 123)
    tmux_registry.register_current_tmux_context(tmp_path, now=10.0)

    tmux_registry.unregister_current_tmux_context(tmp_path)

    assert tmux_registry.load_active_tmux_context(tmp_path, now=11.0) is None
