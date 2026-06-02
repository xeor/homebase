"""Tests for ``ui/screens/multiline_input.MultilineInputScreen``."""
from __future__ import annotations

from homebase.ui.screens.multiline_input import MultilineInputScreen


class _StaticStub:
    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


class _TextAreaStub:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def focus(self) -> None:  # pragma: no cover - not exercised here
        return None


def _make_screen(
    *,
    title: str = "Edit",
    placeholder: str = "",
    value: str = "",
    side_info: str = "",
    heading_level: int = 3,
):
    screen = MultilineInputScreen.__new__(MultilineInputScreen)
    screen.__dict__["title_text"] = title
    screen.__dict__["placeholder_text"] = placeholder
    screen.__dict__["initial_value"] = value
    screen.__dict__["side_info"] = side_info
    screen.__dict__["heading_level"] = max(1, int(heading_level))
    screen._dismissed: list[str | None] = []
    screen.dismiss = screen._dismissed.append  # type: ignore[method-assign]
    return screen


# ---- _heading_warning -----------------------------------------------


def test_heading_warning_empty_when_no_headings() -> None:
    screen = _make_screen(heading_level=3)
    assert screen._heading_warning("just text\nmore text\n") == ""


def test_heading_warning_for_h1_at_h3_entry_level() -> None:
    """A row entered at h3 expects h4-h5 subheadings — an h1 anywhere
    in the body is flagged."""
    screen = _make_screen(heading_level=3)
    warning = screen._heading_warning("# top\nbody\n")
    assert "heading level 1" in warning


def test_heading_warning_ignores_lines_without_space_after_hash() -> None:
    """``#fragment`` and code-style ``#!shebang`` lines are not
    markdown headings — the helper requires a space after the hashes."""
    screen = _make_screen(heading_level=3)
    assert screen._heading_warning("#nope\n#!bin/bash\n") == ""


def test_heading_warning_accepts_within_recommended_range() -> None:
    """Entry at level 3 → recommend levels 4 and 5; an h4 fits and
    must not warn."""
    screen = _make_screen(heading_level=3)
    assert screen._heading_warning("#### sub\n") == ""


def test_heading_warning_flags_too_deep_heading() -> None:
    screen = _make_screen(heading_level=3)
    warning = screen._heading_warning("###### h6\n")
    assert "heading level 6" in warning


def test_heading_warning_caps_recommended_at_h6() -> None:
    """Entry at h6 means there's no deeper "recommended" range — only
    headings at or above the entry level get flagged."""
    screen = _make_screen(heading_level=6)
    assert screen._heading_warning("## too shallow\n") != ""
    # h6 is at the entry level — still flagged.
    assert screen._heading_warning("###### deep\n") != ""


def test_heading_warning_uses_first_offending_line() -> None:
    """Multiple bad headings still return one warning — the first
    one found."""
    screen = _make_screen(heading_level=3)
    out = screen._heading_warning("# first\n# second\n")
    assert "heading level 1" in out
    assert out.count("heading level") == 1


# ---- _refresh_side --------------------------------------------------


def test_refresh_side_shows_warning_and_side_info(monkeypatch) -> None:
    screen = _make_screen(
        heading_level=3,
        side_info="created by foo",
    )
    body = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: body)
    screen._refresh_side("# heading\n")
    assert "warning" in body.text
    assert "created by foo" in body.text


def test_refresh_side_no_warning_section_for_clean_text(monkeypatch) -> None:
    screen = _make_screen(heading_level=3, side_info="hint")
    body = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: body)
    screen._refresh_side("just a plain body")
    assert "warning" not in body.text
    assert "hint" in body.text


def test_refresh_side_empty_when_no_side_info_and_no_warning(monkeypatch) -> None:
    screen = _make_screen(heading_level=3)
    body = _StaticStub()
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: body)
    screen._refresh_side("nothing here")
    assert body.text == ""


# ---- actions --------------------------------------------------------


def test_action_accept_dismisses_with_textarea_value(monkeypatch) -> None:
    screen = _make_screen()
    area = _TextAreaStub("collected text")
    monkeypatch.setattr(screen, "query_one", lambda *_a, **_kw: area)
    screen.action_accept()
    assert screen._dismissed == ["collected text"]


def test_action_cancel_dismisses_with_none() -> None:
    screen = _make_screen()
    screen.action_cancel()
    assert screen._dismissed == [None]


def test_action_open_note_calls_app_hook_when_present(monkeypatch) -> None:
    screen = _make_screen()
    captured: list[str] = []

    class _App:
        def _run_notes_button_action(self, action: str) -> None:
            captured.append(action)

    monkeypatch.setattr(type(screen), "app", property(lambda _s: _App()))
    screen.action_open_note()
    assert captured == ["notes_create"]


def test_action_open_note_noop_when_app_hook_missing(monkeypatch) -> None:
    screen = _make_screen()

    class _App:
        pass

    monkeypatch.setattr(type(screen), "app", property(lambda _s: _App()))
    # Must not raise — the screen quietly skips the action.
    screen.action_open_note()


def test_action_open_note_noop_when_hook_not_callable(monkeypatch) -> None:
    screen = _make_screen()

    class _App:
        _run_notes_button_action = "not-a-function"

    monkeypatch.setattr(type(screen), "app", property(lambda _s: _App()))
    screen.action_open_note()
