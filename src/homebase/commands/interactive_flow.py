from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable


def no_arg_flow(
    base_dir: Path,
    cwd: Path,
    *,
    initial_filter_expr: str,
    cmd_list: Callable[[Path], int],
    run_textual_ui: Callable[[Path, Path, str], tuple[str, Path | None, list[str]]],
    run_post_commands: Callable[[Path, list[str]], None],
    open_with_mode: Callable[[Path, Path], int],
    cmd_archive_mv: Callable[[Path, str], int],
    open_shell_in_dir: Callable[[Path], int],
    cmd_archive_restore_entry: Callable[[Path, str], int],
    cmd_rm: Callable[[str], int],
) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return cmd_list(base_dir)

    action, path, post_commands = run_textual_ui(base_dir, cwd, initial_filter_expr)
    if action == "quit":
        return 0
    if action == "open" and path:
        try:
            run_post_commands(path, post_commands)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return open_with_mode(base_dir, path)
    if action == "archive" and path:
        rc = cmd_archive_mv(base_dir, str(path))
        if rc == 0:
            return open_shell_in_dir(path.parent)
        return rc
    if action == "restore" and path:
        return cmd_archive_restore_entry(base_dir, str(path))
    if action == "delete" and path:
        rc = cmd_rm(str(path))
        if rc == 0 and cwd == path:
            return open_shell_in_dir(path.parent)
        return rc
    if action == "lazygit" and path:
        subprocess.run(["lazygit"], cwd=path, check=False)
        return 0
    return 0
