from __future__ import annotations

import os
import shlex
import webbrowser
from pathlib import Path
from typing import Any, Callable


def open_editor_for_path(
    app: Any,
    path: Path,
    *,
    wait: bool = False,
    on_done: Callable[[], None] | None = None,
) -> None:
    editor_raw = str(os.environ.get("EDITOR", "")).strip()
    if not editor_raw:
        raise ValueError("$EDITOR is not set")
    editor_cmd = shlex.split(editor_raw)
    if not editor_cmd:
        raise ValueError("$EDITOR is empty")
    command_display = " ".join(shlex.quote(part) for part in [*editor_cmd, str(path)])
    app._start_managed_process(
        [*editor_cmd, str(path)],
        cwd=path.parent,
        label=f"editor: {path.name}",
        command_display=command_display,
        wait=wait,
        terminate_on_quit=True,
        on_done=on_done,
    )


def readme_button_actions(selected: Any) -> list[tuple[str, str]]:
    if selected is None or bool(getattr(selected, "packed", False)):
        return []
    path = Path(str(getattr(selected, "path", "")))
    try:
        if not path.is_dir():
            return []
    except OSError:
        return []
    readme_path = path / "README.md"
    try:
        if readme_path.is_file():
            return [("readme_edit", "[white]Edit README.md in $EDITOR[/]")]
    except OSError:
        return []
    return [("readme_create", "[white]Create README.md in $EDITOR[/]")]


def notes_button_actions(
    selected: Any,
    *,
    resolve_notes_path_for_row: Callable[[Any], Path],
) -> list[tuple[str, str]]:
    if selected is None:
        return []
    try:
        note_path = resolve_notes_path_for_row(selected)
    except (OSError, ValueError, RuntimeError):
        return []
    try:
        if note_path.is_file():
            return [("notes_open", "[white]Open Notes markdown[/]")]
    except OSError:
        return []
    return [("notes_create", "[white]Create Notes markdown[/]")]


def handle_side_markdown_link(
    href: str,
    *,
    side_selected_tab: str,
    side_readme_source_path: Path | None,
    side_notes_source_path: Path | None,
    show_runtime_error: Callable[[str, Exception], None],
    set_runtime_status: Callable[[str, str], None] | Callable[..., None],
    level_warn: str,
) -> None:
    href = str(href).strip()
    if not href:
        return
    if href.startswith(("http://", "https://", "mailto:")):
        try:
            ok = bool(webbrowser.open(href, new=2))
        except (OSError, RuntimeError, ValueError, webbrowser.Error) as exc:
            show_runtime_error(f"open external link ({href})", exc)
            return
        if not ok:
            set_runtime_status(f"failed to open link in browser: {href}", level_warn, ttl_s=6.0)
        return

    source = side_readme_source_path if side_selected_tab == "readme" else side_notes_source_path
    if source is None:
        return
    target_ref, anchor = (href.split("#", 1) + [""])[:2]
    target_ref = target_ref.strip()
    anchor = anchor.strip()
    target = source if not target_ref else (source.parent / target_ref).resolve()
    try:
        if not target.exists():
            raise FileNotFoundError(str(target))
        if target.is_dir():
            raise IsADirectoryError(str(target))
        uri = target.as_uri()
        if anchor:
            uri = f"{uri}#{anchor}"
        ok = bool(webbrowser.open(uri, new=2))
        if not ok:
            set_runtime_status(
                f"failed to open link in browser: {target.name}",
                level_warn,
                ttl_s=6.0,
            )
    except (OSError, UnicodeDecodeError, ValueError, RuntimeError, webbrowser.Error) as exc:
        show_runtime_error(f"open markdown link ({href})", exc)
