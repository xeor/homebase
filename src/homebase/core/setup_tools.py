from __future__ import annotations

import os
import shlex
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Callable


def find_executable(name: str, extra_candidates: tuple[str, ...] = ()) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for raw in extra_candidates:
        path = Path(raw)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def recommended_tmux_save_binding(script_path: Path, uv_bin: str, tmux_bin: str) -> str:
    uv_q = shlex.quote(str(uv_bin))
    tmux_q = shlex.quote(str(tmux_bin))
    script_q = shlex.quote(str(script_path))
    return (
        "bind-key t run-shell -b "
        f"'TMUX_BIN={tmux_q} {uv_q} run --script {script_q} tmux save "
        '--pane-id "#{pane_id}" --session-id "#{q:session_id}"\''
    )


def compact_path_for_display(path_text: str) -> str:
    raw = str(path_text)
    home = str(Path.home())
    if home and raw.startswith(home):
        return "~" + raw[len(home) :]
    return raw


def binding_display_lines(binding: str, width: int = 88) -> list[str]:
    compact = compact_path_for_display(binding)
    return textwrap.wrap(compact, width=width, break_long_words=False, break_on_hyphens=False) or [compact]


def has_recommended_tmux_binding(tmux_conf_text: str, expected_line: str) -> bool:
    expected = expected_line.strip()
    return any(str(line).strip() == expected for line in tmux_conf_text.splitlines())


def has_any_tmux_save_binding(tmux_conf_text: str) -> bool:
    for raw in tmux_conf_text.splitlines():
        line = str(raw).strip()
        if not line or line.startswith("#"):
            continue
        if "b tmux save" not in line:
            continue
        if "bind-key" in line or line.startswith("bind "):
            return True
    return False


def write_tmux_binding(tmux_conf_path: Path, expected_line: str) -> None:
    current = ""
    if tmux_conf_path.exists():
        current = tmux_conf_path.read_text()
    lines = current.splitlines()
    replaced = False
    out_lines: list[str] = []
    for raw in lines:
        line = str(raw)
        stripped = line.strip()
        if (
            stripped
            and not stripped.startswith("#")
            and "b tmux save" in stripped
            and ("bind-key" in stripped or stripped.startswith("bind "))
        ):
            if not replaced:
                out_lines.append(expected_line)
                replaced = True
            continue
        out_lines.append(line)

    if not replaced:
        if out_lines and out_lines[-1].strip() != "":
            out_lines.append("")
        out_lines.append(expected_line)

    text = "\n".join(out_lines).rstrip("\n") + "\n"
    tmux_conf_path.parent.mkdir(parents=True, exist_ok=True)
    tmux_conf_path.write_text(text)


def cmd_cache_warm() -> int:
    try:
        import textual  # noqa: F401
        import yaml  # noqa: F401

        print("uv cache warm: textual + pyyaml ready")
        return 0
    except ImportError as exc:
        print(f"cache warm failed: {exc}", file=sys.stderr)
        return 1


def cmd_setup(
    bin_dir: Path,
    *,
    tmux_bin_candidates: tuple[str, ...],
    apply_tmux_binding: bool | None,
    cache_warm: Callable[[], int],
    prompt_yes_no: Callable[[str, bool], bool],
) -> int:
    target = (bin_dir / "b").resolve()
    dest_dir = Path.home() / ".local/bin"
    dest = dest_dir / "b"
    dest_dir.mkdir(parents=True, exist_ok=True)

    if dest.is_symlink():
        if dest.resolve() == target:
            print(f"already installed: {dest} -> {target}")
        else:
            dest.unlink()
            dest.symlink_to(target)
            print(f"installed: {dest} -> {target}")
    elif dest.exists():
        print(f"exists and is not symlink: {dest}", file=sys.stderr)
        return 1
    else:
        dest.symlink_to(target)
        print(f"installed: {dest} -> {target}")

    warm_rc = cache_warm()
    print("setup checks:")
    uv_bin = find_executable("uv", ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"))
    git_bin = find_executable("git")
    tmux_bin = find_executable("tmux", tmux_bin_candidates)
    tmuxp_bin = find_executable("tmuxp")

    print(f"- uv: ok ({uv_bin})" if uv_bin else "- uv: missing")
    print(f"- git: ok ({git_bin})" if git_bin else "- git: missing")
    print(f"- tmux: ok ({tmux_bin})" if tmux_bin else "- tmux: missing")
    print(
        f"- tmuxp: ok ({tmuxp_bin})"
        if tmuxp_bin
        else "- tmuxp: missing (optional for tmux load)"
    )

    path_entries = os.environ.get("PATH", "").split(":")
    in_path = any(Path(p).expanduser().resolve() == dest_dir.resolve() for p in path_entries if p)
    if in_path:
        print(f"- PATH: ok ({dest_dir})")
    else:
        print(f"- PATH: missing {dest_dir} (add it to shell profile)", file=sys.stderr)

    tmux_conf_path = Path.home() / ".tmux.conf"
    try:
        tmux_conf_text = tmux_conf_path.read_text() if tmux_conf_path.exists() else ""
    except OSError as exc:
        print(f"- tmux binding: failed reading {tmux_conf_path} ({exc})", file=sys.stderr)
        tmux_conf_text = ""

    active_tmux_bin = tmux_bin or "/opt/homebrew/bin/tmux"
    active_uv_bin = uv_bin or "/opt/homebrew/bin/uv"
    expected_binding = recommended_tmux_save_binding(target, active_uv_bin, active_tmux_bin)

    if has_recommended_tmux_binding(tmux_conf_text, expected_binding):
        print("- tmux binding: ok (bind-key t -> b tmux save)")
    else:
        target_display = compact_path_for_display(str(tmux_conf_path))
        if has_any_tmux_save_binding(tmux_conf_text):
            print("- tmux binding: found, but not recommended (will replace existing b tmux save bind)")
            question = "update tmux b tmux save binding in ~/.tmux.conf?"
        else:
            print("- tmux binding: missing (will append recommended bind)")
            question = "add tmux b tmux save binding to ~/.tmux.conf?"
        print(f"  file: {target_display}")
        print("  expected:")
        for line in binding_display_lines(expected_binding):
            print(f"    {line}")

        should_apply = apply_tmux_binding
        if should_apply is None:
            should_apply = prompt_yes_no(question, False)

        if should_apply:
            try:
                write_tmux_binding(tmux_conf_path, expected_binding)
                print(f"- tmux binding: written ({target_display})")
                print("  run now: tmux source-file ~/.tmux.conf")
            except (OSError, ValueError) as exc:
                print(f"- tmux binding: failed to write ({exc})", file=sys.stderr)
        else:
            print("- tmux binding: skipped")

    required_ok = bool(uv_bin and git_bin and tmux_bin and warm_rc == 0)
    return 0 if required_ok else 1
