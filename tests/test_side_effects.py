"""Unit tests for ``ui/side/effects.py``.

The side panel "effect" helpers are all pure-ish: they either decide
which buttons to show given a row, or kick off a managed process /
external link. We test the decisions directly and stub the side
effects via injected callables."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from homebase.ui.side import effects

# ---- shared stubs ---------------------------------------------------


class _Row:
    def __init__(self, path: Path, *, packed: bool = False) -> None:
        self.path = path
        self.packed = packed


class _SpyApp:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []

    def _start_managed_process(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        label: str,
        command_display: str,
        wait: bool,
        terminate_on_quit: bool,
        on_done,
    ) -> None:
        self.started.append({
            "cmd": cmd,
            "cwd": cwd,
            "label": label,
            "command_display": command_display,
            "wait": wait,
            "terminate_on_quit": terminate_on_quit,
            "on_done": on_done,
        })


# ---- open_editor_for_path -------------------------------------------


def test_open_editor_for_path_raises_when_editor_unset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EDITOR", raising=False)
    app = _SpyApp()
    with pytest.raises(ValueError, match=r"\$EDITOR is not set"):
        effects.open_editor_for_path(app, tmp_path / "x")


def test_open_editor_for_path_raises_when_editor_whitespace(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EDITOR", "   ")
    app = _SpyApp()
    with pytest.raises(ValueError, match=r"\$EDITOR is not set"):
        effects.open_editor_for_path(app, tmp_path / "x")


def test_open_editor_for_path_quotes_command_display(monkeypatch, tmp_path: Path) -> None:
    """The display string must be shell-safe — paths with spaces get
    quoted so users can paste it into a terminal."""
    monkeypatch.setenv("EDITOR", "nvim --headless")
    app = _SpyApp()
    spaced = tmp_path / "with space" / "README.md"
    effects.open_editor_for_path(app, spaced)
    assert app.started
    call = app.started[0]
    assert call["cmd"] == ["nvim", "--headless", str(spaced)]
    # The space-containing path is single-quoted in the display string.
    assert f"'{spaced}'" in call["command_display"]
    assert call["cwd"] == spaced.parent
    assert call["label"] == "editor: README.md"
    assert call["terminate_on_quit"] is True


def test_open_editor_for_path_passes_through_wait_and_on_done(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("EDITOR", "nvim")
    app = _SpyApp()
    sentinel = object()
    effects.open_editor_for_path(app, tmp_path / "x", wait=True, on_done=lambda: sentinel)
    call = app.started[0]
    assert call["wait"] is True
    assert call["on_done"]() is sentinel


# ---- readme_button_actions ------------------------------------------


def test_readme_actions_empty_for_no_selection() -> None:
    assert effects.readme_button_actions(None) == []


def test_readme_actions_empty_for_packed_archive(tmp_path: Path) -> None:
    """Packed archives are read-only — no edit/create buttons."""
    row = _Row(tmp_path, packed=True)
    assert effects.readme_button_actions(row) == []


def test_readme_actions_empty_when_path_is_not_a_directory(tmp_path: Path) -> None:
    """The selection's path must resolve to a directory; if it doesn't
    (e.g. project was deleted under us) the button list is empty."""
    row = _Row(tmp_path / "missing")
    assert effects.readme_button_actions(row) == []


def test_readme_actions_offers_edit_when_readme_exists(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# title")
    row = _Row(tmp_path)
    out = effects.readme_button_actions(row)
    assert out and out[0][0] == "readme_edit"


def test_readme_actions_offers_create_when_readme_missing(tmp_path: Path) -> None:
    row = _Row(tmp_path)
    out = effects.readme_button_actions(row)
    assert out and out[0][0] == "readme_create"


# ---- notes_button_actions -------------------------------------------


def test_notes_actions_empty_for_no_selection() -> None:
    assert effects.notes_button_actions(
        None, resolve_notes_path_for_row=lambda _r: Path("/"),
    ) == []


def test_notes_actions_empty_when_resolver_raises(tmp_path: Path) -> None:
    """If the notes-path resolver blows up (no notes config etc.), we
    drop the button rather than propagating the error."""
    row = _Row(tmp_path)

    def _resolver(_row):
        raise RuntimeError("no notes config")

    assert effects.notes_button_actions(row, resolve_notes_path_for_row=_resolver) == []


def test_notes_actions_offers_create_when_file_missing(tmp_path: Path) -> None:
    row = _Row(tmp_path)
    note = tmp_path / "notes.md"
    out = effects.notes_button_actions(row, resolve_notes_path_for_row=lambda _r: note)
    assert out and out[0][0] == "notes_create"


def test_notes_actions_offers_open_when_file_exists(tmp_path: Path) -> None:
    row = _Row(tmp_path)
    note = tmp_path / "notes.md"
    note.write_text("hello")
    out = effects.notes_button_actions(row, resolve_notes_path_for_row=lambda _r: note)
    assert out and out[0][0] == "notes_open"


def test_notes_actions_skips_open_on_case_mismatch(tmp_path: Path, monkeypatch) -> None:
    """When the on-disk filename differs only by case from the
    resolver's result, opening would resolve to the wrong file on
    case-insensitive filesystems — better to hide the button."""
    row = _Row(tmp_path)
    note = tmp_path / "Notes.md"
    note.write_text("hello")
    monkeypatch.setattr(
        effects, "existing_path_case_mismatch", lambda _p: tmp_path / "Notes.md",
    )
    out = effects.notes_button_actions(
        row, resolve_notes_path_for_row=lambda _r: note,
    )
    assert out == []


# ---- handle_side_markdown_link --------------------------------------


def _make_link_kwargs(**overrides):
    base = {
        "side_selected_tab": "readme",
        "side_readme_source_path": None,
        "side_notes_source_path": None,
        "show_runtime_error": lambda *a, **kw: None,
        "set_runtime_status": lambda *a, **kw: None,
        "level_warn": "warn",
    }
    base.update(overrides)
    return base


def test_handle_side_markdown_link_ignores_empty(monkeypatch) -> None:
    """A blank href is a no-op — webbrowser must not be invoked."""
    called = {"n": 0}
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda *a, **kw: (called.__setitem__("n", called["n"] + 1), True)[1],
    )
    effects.handle_side_markdown_link("", **_make_link_kwargs())
    effects.handle_side_markdown_link("   ", **_make_link_kwargs())
    assert called["n"] == 0


def test_handle_side_markdown_link_opens_http(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda url, new=0: opened.append(url) or True,
    )
    effects.handle_side_markdown_link("https://example.com", **_make_link_kwargs())
    assert opened == ["https://example.com"]


def test_handle_side_markdown_link_reports_failed_http(monkeypatch) -> None:
    monkeypatch.setattr(effects.webbrowser, "open", lambda *a, **kw: False)
    statuses: list[tuple[str, str]] = []

    def status(msg, level, ttl_s=None):
        statuses.append((msg, level))

    effects.handle_side_markdown_link(
        "https://example.com",
        **_make_link_kwargs(set_runtime_status=status),
    )
    assert statuses and "failed to open link" in statuses[0][0]


def test_handle_side_markdown_link_http_webbrowser_raises(monkeypatch) -> None:
    def boom(*_a, **_kw):
        raise OSError("no browser")

    monkeypatch.setattr(effects.webbrowser, "open", boom)
    errors: list[tuple[str, Exception]] = []
    effects.handle_side_markdown_link(
        "https://example.com",
        **_make_link_kwargs(show_runtime_error=lambda label, exc: errors.append((label, exc))),
    )
    assert errors and "open external link" in errors[0][0]


def test_handle_side_markdown_link_relative_in_readme(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "readme" / "README.md"
    source.parent.mkdir()
    source.write_text("hi")
    target = tmp_path / "readme" / "doc.md"
    target.write_text("doc")
    opened: list[str] = []
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda url, new=0: opened.append(url) or True,
    )
    effects.handle_side_markdown_link(
        "doc.md", **_make_link_kwargs(
            side_selected_tab="readme",
            side_readme_source_path=source,
        ),
    )
    assert opened
    assert opened[0].endswith("doc.md")
    assert opened[0].startswith("file://")


def test_handle_side_markdown_link_relative_with_anchor(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# hi")
    opened: list[str] = []
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda url, new=0: opened.append(url) or True,
    )
    effects.handle_side_markdown_link(
        "notes.md#section",
        **_make_link_kwargs(
            side_selected_tab="notes",
            side_notes_source_path=source,
        ),
    )
    assert opened and opened[0].endswith("#section")


def test_handle_side_markdown_link_anchor_only_targets_source(
    tmp_path: Path, monkeypatch,
) -> None:
    """``#anchor`` with no preceding path means "scroll the current
    document to that anchor" — the URI must reuse the source path."""
    source = tmp_path / "README.md"
    source.write_text("# top")
    opened: list[str] = []
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda url, new=0: opened.append(url) or True,
    )
    effects.handle_side_markdown_link(
        "#section",
        **_make_link_kwargs(
            side_selected_tab="readme",
            side_readme_source_path=source,
        ),
    )
    assert opened and opened[0] == f"{source.as_uri()}#section"


def test_handle_side_markdown_link_missing_target_reports_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "README.md"
    source.write_text("# top")
    errors: list[tuple[str, Exception]] = []
    effects.handle_side_markdown_link(
        "missing.md",
        **_make_link_kwargs(
            side_selected_tab="readme",
            side_readme_source_path=source,
            show_runtime_error=lambda label, exc: errors.append((label, exc)),
        ),
    )
    assert errors and isinstance(errors[0][1], FileNotFoundError)


def test_handle_side_markdown_link_directory_target_reports_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "README.md"
    source.write_text("# top")
    sub = tmp_path / "sub"
    sub.mkdir()
    errors: list[tuple[str, Exception]] = []
    effects.handle_side_markdown_link(
        "sub",
        **_make_link_kwargs(
            side_selected_tab="readme",
            side_readme_source_path=source,
            show_runtime_error=lambda label, exc: errors.append((label, exc)),
        ),
    )
    assert errors and isinstance(errors[0][1], IsADirectoryError)


def test_handle_side_markdown_link_relative_skipped_when_no_source(
    monkeypatch,
) -> None:
    """If neither readme nor notes has a source path on this tab, the
    relative link has no anchor to resolve from — quietly skip."""
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda *_a, **_kw: pytest.fail("should not open browser"),
    )
    effects.handle_side_markdown_link(
        "doc.md", **_make_link_kwargs(side_selected_tab="readme"),
    )


def test_handle_side_markdown_link_uses_notes_source_when_on_notes_tab(
    tmp_path: Path, monkeypatch,
) -> None:
    notes = tmp_path / "notes.md"
    notes.write_text("hi")
    target = tmp_path / "ref.md"
    target.write_text("ref")
    opened: list[str] = []
    monkeypatch.setattr(
        effects.webbrowser, "open",
        lambda url, new=0: opened.append(url) or True,
    )
    effects.handle_side_markdown_link(
        "ref.md",
        **_make_link_kwargs(
            side_selected_tab="notes",
            side_readme_source_path=tmp_path / "ignored.md",
            side_notes_source_path=notes,
        ),
    )
    assert opened and opened[0].endswith("ref.md")
