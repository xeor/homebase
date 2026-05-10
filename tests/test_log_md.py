from __future__ import annotations

import pytest

from homebase.notes.log_md import (
    LOG_HEADING,
    NoteValidationError,
    detect_line_ending,
    insert_log_entry,
    validate_note,
)

TS = "2026-05-07T21:48:35+02:00"
TS2 = "2026-05-08T10:00:00+02:00"


def test_detect_line_ending_lf() -> None:
    assert detect_line_ending("a\nb\nc\n") == "\n"


def test_detect_line_ending_crlf() -> None:
    assert detect_line_ending("a\r\nb\r\n") == "\r\n"


def test_detect_line_ending_empty_defaults_to_lf() -> None:
    assert detect_line_ending("") == "\n"


def test_validate_note_passes_for_simple_layout() -> None:
    content = "# Demo\n\n## Log\n\n### 2026-05-04T22:18:32+02:00\n\nold\n"
    validate_note(content)


def test_validate_note_rejects_duplicate_log_sections() -> None:
    content = "# Demo\n\n## Log\n\nfirst\n\n## Log\n\nsecond\n"
    with pytest.raises(NoteValidationError, match="duplicate"):
        validate_note(content)


def test_validate_note_ignores_log_inside_code_fence() -> None:
    content = (
        "# Demo\n\n"
        "```\n## Log\n```\n\n"
        "## Log\n\nactual\n"
    )
    validate_note(content)


def test_validate_note_ignores_log_inside_tilde_fence() -> None:
    content = (
        "# Demo\n\n"
        "~~~\n## Log\n~~~\n\n"
        "## Log\n\nactual\n"
    )
    validate_note(content)


def test_insert_log_entry_creates_new_file_when_content_none() -> None:
    out = insert_log_entry(None, project_name="Projectname", timestamp=TS, text="hello")
    assert out == (
        "# Projectname\n"
        "\n"
        "## Log\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "hello\n"
        "\n"
    )


def test_insert_log_entry_appends_under_existing_log() -> None:
    existing = (
        "# Projectname\n"
        "\n"
        "## Log\n"
        "\n"
        "### 2026-05-04T22:18:32+02:00\n"
        "\n"
        "Text from log\n"
    )
    out = insert_log_entry(
        existing, project_name="Projectname", timestamp=TS, text="Some text here from inputbox"
    )
    expected = (
        "# Projectname\n"
        "\n"
        "## Log\n"
        "\n"
        "### 2026-05-04T22:18:32+02:00\n"
        "\n"
        "Text from log\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "Some text here from inputbox\n"
    )
    assert out == expected


def test_insert_log_entry_creates_log_when_missing() -> None:
    existing = "# Projectname\n\nSome existing prose.\n"
    out = insert_log_entry(
        existing, project_name="Projectname", timestamp=TS, text="first entry"
    )
    expected = (
        "# Projectname\n"
        "\n"
        "Some existing prose.\n"
        "\n"
        "## Log\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "first entry\n"
    )
    assert out == expected


def test_insert_log_entry_rejects_duplicate_log_sections() -> None:
    existing = "# Demo\n\n## Log\n\na\n\n## Log\n\nb\n"
    with pytest.raises(NoteValidationError):
        insert_log_entry(existing, project_name="Demo", timestamp=TS, text="x")


def test_insert_log_entry_preserves_content_after_log_section() -> None:
    existing = (
        "# Demo\n"
        "\n"
        "## Log\n"
        "\n"
        "### old\n"
        "\n"
        "old content\n"
        "\n"
        "## Other\n"
        "\n"
        "tail content\n"
    )
    out = insert_log_entry(existing, project_name="Demo", timestamp=TS, text="new")
    expected = (
        "# Demo\n"
        "\n"
        "## Log\n"
        "\n"
        "### old\n"
        "\n"
        "old content\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "new\n"
        "\n"
        "## Other\n"
        "\n"
        "tail content\n"
    )
    assert out == expected


def test_insert_log_entry_preserves_crlf_line_endings() -> None:
    existing = "# Demo\r\n\r\n## Log\r\n\r\n### old\r\n\r\nold\r\n"
    out = insert_log_entry(existing, project_name="Demo", timestamp=TS, text="new")
    assert "\r\n" in out
    assert "\n" not in out.replace("\r\n", "")
    assert out.endswith("\r\n")
    assert "### old\r\n" in out
    assert f"### {TS}\r\n" in out


def test_insert_log_entry_handles_empty_log_section() -> None:
    existing = "# Demo\n\n## Log\n"
    out = insert_log_entry(existing, project_name="Demo", timestamp=TS, text="first")
    expected = (
        "# Demo\n"
        "\n"
        "## Log\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "first\n"
    )
    assert out == expected


def test_insert_log_entry_supports_multiline_text() -> None:
    out = insert_log_entry(None, project_name="Demo", timestamp=TS, text="line1\nline2\n  line3")
    assert "line1\nline2\n  line3\n" in out


def test_insert_log_entry_does_not_modify_input_lines_outside_log() -> None:
    existing = (
        "# Demo\n"
        "\n"
        "## Intro\n"
        "\n"
        "intro body\n"
        "\n"
        "## Log\n"
        "\n"
        "### old\n"
        "\n"
        "old\n"
    )
    out = insert_log_entry(existing, project_name="Demo", timestamp=TS, text="new")
    assert "## Intro\n\nintro body\n" in out
    assert "### old" in out
    assert "## Log" in out
    # Only one ## Log heading
    assert out.count(f"\n{LOG_HEADING}\n") == 1


def test_insert_log_entry_appends_log_when_only_h1_present() -> None:
    existing = "# Demo\n"
    out = insert_log_entry(existing, project_name="Demo", timestamp=TS, text="hi")
    expected = (
        "# Demo\n"
        "\n"
        "## Log\n"
        "\n"
        f"### {TS}\n"
        "\n"
        "hi\n"
    )
    assert out == expected


def test_insert_log_entry_round_trip_writes_two_entries() -> None:
    out1 = insert_log_entry(None, project_name="Demo", timestamp=TS, text="first")
    out2 = insert_log_entry(out1, project_name="Demo", timestamp=TS2, text="second")
    assert f"### {TS}\n" in out2
    assert f"### {TS2}\n" in out2
    assert out2.index(f"### {TS}") < out2.index(f"### {TS2}")


def test_insert_log_entry_supports_custom_section_heading() -> None:
    out = insert_log_entry(
        None,
        project_name="Demo",
        timestamp=TS,
        text="hello",
        section_title="Journal",
        section_level=3,
    )
    assert "### Journal\n" in out
    assert f"#### {TS}\n" in out
