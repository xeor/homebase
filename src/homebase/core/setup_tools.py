from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from .constants import GLOBAL_CONFIG_FILE_NAME, HOMEBASE_DIR_NAME
from .setup_model import (
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    FixResult,
    SetupCheck,
    SetupContext,
    SetupFix,
    SetupSummary,
)
from .setup_render import (
    render_checks,
    render_summary,
)


def find_executable(name: str, extra_candidates: tuple[str, ...] = ()) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for raw in extra_candidates:
        path = Path(raw)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def recommended_tmux_save_binding(script_path: Path, tmux_bin: str = "") -> str:
    """Suggested tmux binding to save the current window as ``.tmuxp.yaml``.

    Wraps ``b tmux save`` in a ``sh -c`` failsafe. If the binary
    itself can't start (PATH issue, broken shebang, missing
    interpreter), the popup stays open with a bold red banner naming
    the specific failure and a diagnostic dump that searches common
    install locations — so tmux/tmuxp are not falsely reported as
    MISSING when the tmux server's PATH is stripped.

    The ``--pause`` flag is still passed so the python side prints
    its own diagnostic header and friendly error classifications on
    every run."""
    _ = tmux_bin
    script_q = shlex.quote(str(script_path))
    # Single-quoted body for tmux conf. No single quotes allowed inside.
    inner = (
        # locate a binary even when PATH is stripped (common for tmux
        # servers started before shell rc loaded /opt/homebrew/bin etc.)
        'find_bin() {'
        ' n=$1;'
        ' if command -v "$n" >/dev/null 2>&1; then command -v "$n"; return 0; fi;'
        ' for p in /opt/homebrew/bin /usr/local/bin /opt/local/bin /usr/bin /bin "$HOME/.local/bin" "$HOME/bin"; do'
        '   if [ -x "$p/$n" ]; then echo "$p/$n"; return 0; fi;'
        ' done;'
        ' echo MISSING; return 1;'
        ' };'
        # run b; capture exit code
        '"$1" tmux save --pause --pane-id "$2" --session-id "$3";'
        ' rc=$?;'
        ' [ $rc -eq 0 ] && exit 0;'
        # ── failure path ──
        ' RED=$(printf "\\033[1;41;37m");'
        ' YEL=$(printf "\\033[1;33m");'
        ' DIM=$(printf "\\033[2m");'
        ' RST=$(printf "\\033[0m");'
        ' echo;'
        # specific cause banner
        ' if [ ! -e "$1" ]; then'
        '   printf "%s  the b binary does not exist  %s\\n" "$RED" "$RST";'
        '   printf "%s  path: %s%s\\n" "$YEL" "$1" "$RST";'
        ' elif [ ! -x "$1" ]; then'
        '   printf "%s  the b binary is not executable  %s\\n" "$RED" "$RST";'
        '   printf "%s  path: %s%s\\n" "$YEL" "$1" "$RST";'
        ' elif [ $rc -eq 127 ]; then'
        '   printf "%s  shell could not start the command (rc=127)  %s\\n" "$RED" "$RST";'
        '   printf "%s  usually a missing interpreter in the b shebang (python/uv?)%s\\n" "$YEL" "$RST";'
        ' else'
        '   printf "%s  b tmux save exited rc=%s — see error printed above  %s\\n" "$RED" "$rc" "$RST";'
        ' fi;'
        ' echo;'
        ' printf "%s── diagnostics ──%s\\n" "$DIM" "$RST";'
        ' TMUX_BIN=$(find_bin tmux);'
        ' TMUXP_BIN=$(find_bin tmuxp);'
        ' printf "b binary:    %s\\n" "$1";'
        ' printf "tmux:        %s\\n" "$TMUX_BIN";'
        ' if [ "$TMUX_BIN" != MISSING ]; then'
        '   printf "tmux -V:     %s\\n" "$("$TMUX_BIN" -V 2>&1 || echo unknown)";'
        ' fi;'
        ' printf "tmuxp:       %s\\n" "$TMUXP_BIN";'
        ' if [ "$TMUXP_BIN" != MISSING ]; then'
        '   printf "tmuxp -V:    %s\\n" "$("$TMUXP_BIN" --version 2>&1 || echo unknown)";'
        ' fi;'
        ' printf "TMUX=%s\\n" "${TMUX:-unset}";'
        ' printf "TMUX_PANE=%s\\n" "${TMUX_PANE:-unset}";'
        ' printf "SHELL=%s\\n" "${SHELL:-unset}";'
        ' printf "PWD=%s\\n" "$PWD";'
        ' printf "PATH=%s\\n" "$PATH";'
        ' echo;'
        ' echo "Press ESC to close...";'
        # Park the shell until tmux closes the popup via ESC. Other
        # keys just echo into the popup buffer and do not release
        # this read (display-popup's stdin handling).
        ' head -c 1 >/dev/null 2>&1 || true'
    )
    # NOTE: format strings must be in DOUBLE quotes for tmux to expand
    # them. Single quotes treat `#` as literal, which is why earlier
    # versions of this binding passed the strings `#{pane_id}` /
    # `#{q:session_id}` to the python side instead of real values.
    # ``-E`` closes the popup when the shell exits. The shell only
    # exits after ``read _`` consumes the user's Enter (either from
    # python's pause loop or from the failure block), so a single
    # Enter is enough — without ``-E`` tmux keeps the popup open
    # waiting for another keypress.
    return (
        "bind-key t display-popup -E -w 80% -h 70% "
        f"sh -c '{inner}' tmux-save-popup {script_q} "
        '"#{pane_id}" "#{q:session_id}"'
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


def _is_tmux_bind_line(line: str) -> bool:
    stripped = str(line).strip()
    if not stripped or stripped.startswith("#"):
        return False
    return stripped.startswith("bind-key ") or stripped.startswith("bind ")


def is_acceptable_tmux_save_binding(line: str) -> bool:
    """Returns True if `line` defines a working ``b tmux save`` binding.

    Parser-style: tolerates whitespace, quoting, and path variation;
    only checks that the essential pieces are present. Used so the
    binding doesn't read as "stale" because of a trivial difference."""
    if not _is_tmux_bind_line(line):
        return False
    stripped = str(line).strip()
    if "tmux save" not in stripped:
        return False
    if "#{pane_id}" not in stripped:
        return False
    if "session_id" not in stripped:
        return False
    # The legacy form invoked the entry-point via `uv run --script`,
    # which sometimes failed silently. Treat it as stale so setup can
    # offer the rewrite.
    if "uv run --script" in stripped:
        return False
    return True


def _normalize_binding(line: str) -> str:
    """Strip whitespace and collapse interior runs so trivial spacing
    differences don't mark a binding as stale."""
    return " ".join(str(line).strip().split())


def has_recommended_tmux_binding(tmux_conf_text: str, expected_line: str = "") -> bool:
    """True only when an existing binding line normalizes to the
    *current* recommended binding. A loosely-acceptable binding that
    doesn't match (e.g. missing the new ``--pause`` flag) reads as
    stale — matching the diff the preview pane shows.
    """
    expected_norm = _normalize_binding(expected_line)
    if not expected_norm:
        return False
    return any(
        _normalize_binding(line) == expected_norm
        for line in tmux_conf_text.splitlines()
    )


def has_any_tmux_save_binding(tmux_conf_text: str) -> bool:
    """True if there's ANY `b tmux save` binding (acceptable or
    legacy). Used to detect "present" state for the fix."""
    for raw in tmux_conf_text.splitlines():
        if not _is_tmux_bind_line(raw):
            continue
        line = str(raw).strip()
        if "tmux save" not in line:
            continue
        # The line must actually invoke `b tmux save`; the legacy form
        # has 'tmux save' as a sub-command after a path ending in /b,
        # which still satisfies the loose check.
        if " save" in line:
            return True
    return False


def tmux_save_binding_lines(tmux_conf_text: str) -> list[str]:
    out: list[str] = []
    for raw in tmux_conf_text.splitlines():
        if not _is_tmux_bind_line(raw):
            continue
        line = str(raw).strip()
        if "tmux save" not in line:
            continue
        out.append(line)
    return out


def write_tmux_binding(tmux_conf_path: Path, expected_line: str) -> None:
    current = ""
    if tmux_conf_path.exists():
        current = tmux_conf_path.read_text()
    lines = current.splitlines()
    replaced = False
    out_lines: list[str] = []
    for raw in lines:
        line = str(raw)
        if _is_tmux_bind_line(line) and "tmux save" in line.strip():
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


def _runtime_imports_ok() -> tuple[bool, str]:
    try:
        import textual  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return False, f"missing runtime python deps ({exc})"
    return True, "python runtime deps available"


def _state_text(status: str) -> str:
    if status == STATUS_PASS:
        return "already configured"
    if status == STATUS_FAIL:
        return "missing"
    return "needs change"


def _write_homebase_gitignore(path: Path) -> None:
    entry = "cache.sqlite3"
    if not path.exists():
        path.write_text(f"{entry}\n")
        return
    lines = [ln.rstrip("\n") for ln in path.read_text().splitlines()]
    if entry in lines:
        return
    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.append(entry)
    path.write_text("\n".join(lines).rstrip("\n") + "\n")


def _remove_homebase_gitignore_rule(path: Path) -> None:
    if not path.is_file():
        return
    entry = "cache.sqlite3"
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() != entry]
    if not lines:
        path.unlink()
        return
    path.write_text("\n".join(lines).rstrip("\n") + "\n")


def _remove_tmux_binding(path: Path) -> None:
    if not path.is_file():
        return
    out_lines: list[str] = []
    for raw in path.read_text().splitlines():
        if _is_tmux_bind_line(raw) and "tmux save" in str(raw).strip():
            continue
        out_lines.append(str(raw))
    text = "\n".join(out_lines).rstrip("\n")
    if text:
        text += "\n"
    path.write_text(text)


def _remove_shell_init_source_line(rc_path: Path, source_line: str) -> None:
    if not rc_path.is_file():
        return
    out_lines = [ln for ln in rc_path.read_text().splitlines() if ln.strip() != source_line.strip()]
    text = "\n".join(out_lines).rstrip("\n")
    if text:
        text += "\n"
    rc_path.write_text(text)


def _remove_dir_if_exists(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)


def _remove_file_if_exists(path: Path) -> None:
    if path.is_file() or path.is_symlink():
        path.unlink()


def _current_shell_name() -> str:
    shell = str(os.environ.get("SHELL", "")).strip()
    if not shell:
        return ""
    return Path(shell).name.strip().lower()


def _completion_target_for_shell(shell: str) -> Path | None:
    value = str(shell).strip().lower()
    if value == "bash":
        return Path.home() / ".local/share/bash-completion/completions/b"
    if value == "zsh":
        return Path.home() / ".zfunc/_b"
    if value == "fish":
        return Path.home() / ".config/fish/completions/b.fish"
    return None


def _completion_ok(path: Path, expected_script: str) -> bool:
    try:
        current = path.read_text()
    except OSError:
        return False
    return current == expected_script


def _shell_init_target_for_shell(shell: str) -> Path | None:
    """Where the `b shell-init <shell>` wrapper should be installed.

    fish gets its own auto-sourced file under ``conf.d/``. bash and
    zsh have nowhere as canonical as that, so we use a dedicated
    homebase init file and a separate one-liner the user adds to
    their ``~/.bashrc`` / ``~/.zshrc`` that sources it. The check +
    fix logic in ``cmd_setup`` covers both halves."""
    value = str(shell).strip().lower()
    if value == "bash":
        return Path.home() / ".local/share/homebase/shell-init.bash"
    if value == "zsh":
        return Path.home() / ".local/share/homebase/shell-init.zsh"
    if value == "fish":
        return Path.home() / ".config/fish/conf.d/b.fish"
    return None


def _shell_init_rc_for_shell(shell: str) -> Path | None:
    value = str(shell).strip().lower()
    if value == "bash":
        return Path.home() / ".bashrc"
    if value == "zsh":
        return Path.home() / ".zshrc"
    return None


def _shell_init_source_line(shell: str, target: Path) -> str:
    _ = shell
    home = str(Path.home())
    display = str(target)
    if display.startswith(home + "/"):
        display = "$HOME" + display[len(home) :]
    return f'[ -f "{display}" ] && . "{display}"  # homebase shell integration'


def _shell_init_installed(
    shell: str,
    expected_script: str,
    target: Path | None,
    rc_path: Path | None,
) -> bool:
    if target is None:
        return False
    try:
        if not target.is_file() or target.read_text() != expected_script:
            return False
    except OSError:
        return False
    if rc_path is None:
        return True
    try:
        rc_text = rc_path.read_text() if rc_path.is_file() else ""
    except OSError:
        return False
    return _shell_init_source_line(shell, target) in rc_text


def _detect_self_update(base_dir: Path, launcher_path: Path | None) -> tuple[str, str]:
    repo_root = base_dir
    if (repo_root / "src" / "homebase").is_dir() and (repo_root / "pyproject.toml").is_file():
        cmd = f'uv tool install --editable "{repo_root}"'
        return f"local editable install detected (repo={repo_root})", cmd
    launcher = str(launcher_path or "")
    exe = str(Path(sys.executable).resolve()) if str(sys.executable).strip() else ""
    if "/.local/share/uv/tools/" in exe:
        return f"uv tool runtime detected (python={exe})", "uv tool upgrade homebase"
    if "/.local/share/uv/tools/" in launcher:
        return "uv tool install detected", "uv tool upgrade homebase"
    if "/site-packages/" in exe or "/dist-packages/" in exe:
        return f"python environment install detected (python={exe})", "python -m pip install -U homebase"
    if launcher:
        if exe:
            return f"install mode unclear (launcher={launcher}, python={exe})", ""
        return f"install mode unclear (launcher={launcher})", ""
    if exe:
        return f"launcher path unavailable (python={exe})", ""
    return "launcher path unavailable", ""


# --- context gather --------------------------------------------------


def _gather_context(
    base_dir: Path,
    bin_dir: Path,
    *,
    tmux_bin_candidates: tuple[str, ...],
    completion_script_fn: Callable[[str], str] | None,
    shell_init_script_fn: Callable[[str], str] | None,
) -> SetupContext:
    homebase_dir = base_dir / HOMEBASE_DIR_NAME
    config_path = homebase_dir / GLOBAL_CONFIG_FILE_NAME
    homebase_gitignore = homebase_dir / ".gitignore"
    target = (bin_dir / "b").resolve()
    dest_dir = Path.home() / ".local/bin"
    dest = dest_dir / "b"
    launcher = shutil.which("b")
    launcher_path = Path(launcher).resolve() if launcher else None

    uv_bin = find_executable("uv", ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"))
    git_bin = find_executable("git")
    tmux_bin = find_executable("tmux", tmux_bin_candidates)
    tmuxp_bin = find_executable("tmuxp")
    runtime_ok, runtime_detail = _runtime_imports_ok()

    path_entries = os.environ.get("PATH", "").split(":")
    in_path = any(
        Path(p).expanduser().resolve() == dest_dir.resolve()
        for p in path_entries
        if p
    )

    tmux_conf_path = Path.home() / ".tmux.conf"
    try:
        tmux_conf_text = tmux_conf_path.read_text() if tmux_conf_path.exists() else ""
    except OSError:
        tmux_conf_text = ""
    expected_tmux_binding = recommended_tmux_save_binding(target)
    existing_tmux_binding_lines = tuple(tmux_save_binding_lines(tmux_conf_text))

    active_shell = _current_shell_name()
    completion_shell = active_shell if active_shell in {"bash", "zsh", "fish"} else ""
    completion_target = _completion_target_for_shell(completion_shell) if completion_shell else None
    expected_completion = ""
    completion_ok = False
    if completion_shell and completion_script_fn is not None and completion_target is not None:
        expected_completion = completion_script_fn(completion_shell)
        completion_ok = _completion_ok(completion_target, expected_completion)

    shell_init_target = (
        _shell_init_target_for_shell(completion_shell) if completion_shell else None
    )
    shell_init_rc = (
        _shell_init_rc_for_shell(completion_shell) if completion_shell else None
    )
    expected_shell_init = ""
    shell_init_ok = False
    if completion_shell and shell_init_script_fn is not None and shell_init_target is not None:
        expected_shell_init = shell_init_script_fn(completion_shell)
        shell_init_ok = _shell_init_installed(
            completion_shell,
            expected_shell_init,
            shell_init_target,
            shell_init_rc,
        )

    update_detail, update_cmd = _detect_self_update(base_dir, launcher_path)

    config_exists = config_path.is_file()
    config_valid = True
    if config_exists:
        try:
            loaded = yaml.safe_load(config_path.read_text())
            config_valid = loaded is None or isinstance(loaded, dict)
        except (OSError, yaml.YAMLError):
            config_valid = False

    return SetupContext(
        base_dir=base_dir,
        bin_dir=bin_dir,
        homebase_dir=homebase_dir,
        config_path=config_path,
        homebase_gitignore=homebase_gitignore,
        target=target,
        dest_dir=dest_dir,
        dest=dest,
        launcher_path=launcher_path,
        uv_bin=uv_bin,
        git_bin=git_bin,
        tmux_bin=tmux_bin,
        tmuxp_bin=tmuxp_bin,
        runtime_ok=runtime_ok,
        runtime_detail=runtime_detail,
        in_path=in_path,
        tmux_conf_path=tmux_conf_path,
        tmux_conf_text=tmux_conf_text,
        expected_tmux_binding=expected_tmux_binding,
        existing_tmux_binding_lines=existing_tmux_binding_lines,
        completion_shell=completion_shell,
        completion_target=completion_target,
        expected_completion=expected_completion,
        completion_ok=completion_ok,
        shell_init_target=shell_init_target,
        shell_init_rc=shell_init_rc,
        expected_shell_init=expected_shell_init,
        shell_init_ok=shell_init_ok,
        update_cmd=update_cmd,
        update_detail=update_detail,
        config_exists=config_exists,
        config_valid=config_valid,
    )


# --- check building --------------------------------------------------


def _gitignore_has_cache_rule(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        lines = [ln.strip() for ln in path.read_text().splitlines()]
    except OSError:
        return False
    return "cache.sqlite3" in lines


def _b_launcher_check(dest: Path, target: Path) -> SetupCheck:
    if dest.is_symlink():
        try:
            resolved = dest.resolve()
        except OSError:
            return SetupCheck(
                id="b_launcher",
                name="b launcher",
                status=STATUS_FAIL,
                detail=f"broken symlink: {dest}",
                required=True,
            )
        status = STATUS_PASS if resolved == target else STATUS_FAIL
        return SetupCheck(
            id="b_launcher",
            name="b launcher",
            status=status,
            detail=f"{dest} -> {resolved}",
            required=True,
        )
    if dest.exists():
        return SetupCheck(
            id="b_launcher",
            name="b launcher",
            status=STATUS_FAIL,
            detail=f"exists and is not symlink: {dest}",
            required=True,
        )
    return SetupCheck(
        id="b_launcher",
        name="b launcher",
        status=STATUS_FAIL,
        detail=f"missing symlink: {dest} -> {target}",
        required=True,
    )


def _self_update_check(ctx: SetupContext) -> SetupCheck:
    if ctx.update_cmd:
        return SetupCheck(
            id="self_update",
            name="self-update",
            status=STATUS_PASS,
            detail=f"available: {ctx.update_cmd} ({ctx.update_detail})",
        )
    launcher_text = str(ctx.launcher_path) if ctx.launcher_path is not None else "<not found>"
    python_text = str(Path(sys.executable).resolve()) if str(sys.executable).strip() else "<unknown>"
    extra = (
        "  self-update diagnostics:",
        f"    launcher: {launcher_text}",
        f"    python:   {python_text}",
    )
    return SetupCheck(
        id="self_update",
        name="self-update",
        status=STATUS_WARN,
        detail=f"needs manual action: {ctx.update_detail}",
        extra_lines=extra,
    )


def _tmux_binding_check(ctx: SetupContext) -> SetupCheck:
    ok = has_recommended_tmux_binding(ctx.tmux_conf_text, ctx.expected_tmux_binding)
    extra: tuple[str, ...] = ()
    if not ok and ctx.existing_tmux_binding_lines:
        extra = (
            "  tmux binding diff:",
            f"    current: {ctx.existing_tmux_binding_lines[0]}",
            f"    expect : {ctx.expected_tmux_binding}",
        )
    return SetupCheck(
        id="tmux_binding",
        name="tmux binding",
        status=STATUS_PASS if ok else STATUS_WARN,
        detail="recommended binding present" if ok else "recommended binding missing",
        extra_lines=extra,
    )


def _completion_check(ctx: SetupContext) -> SetupCheck:
    if not ctx.completion_shell:
        return SetupCheck(
            id="shell_completion",
            name="shell completion",
            status=STATUS_SKIP,
            detail="unsupported shell for auto-check",
        )
    if ctx.completion_target is None or not ctx.expected_completion:
        return SetupCheck(
            id="shell_completion",
            name="shell completion",
            status=STATUS_WARN,
            detail=f"needs change: completion checker unavailable for {ctx.completion_shell}",
        )
    if ctx.completion_ok:
        return SetupCheck(
            id="shell_completion",
            name="shell completion",
            status=STATUS_PASS,
            detail=f"already configured: {ctx.completion_target}",
        )
    return SetupCheck(
        id="shell_completion",
        name="shell completion",
        status=STATUS_WARN,
        detail=f"needs change: write completion to {ctx.completion_target}",
    )


def _shell_init_check(ctx: SetupContext) -> SetupCheck:
    if not ctx.completion_shell:
        return SetupCheck(
            id="shell_init",
            name="shell-init wrapper",
            status=STATUS_SKIP,
            detail="unsupported shell for auto-check",
        )
    if ctx.shell_init_target is None or not ctx.expected_shell_init:
        return SetupCheck(
            id="shell_init",
            name="shell-init wrapper",
            status=STATUS_WARN,
            detail=f"needs change: shell-init writer unavailable for {ctx.completion_shell}",
        )
    if ctx.shell_init_ok:
        return SetupCheck(
            id="shell_init",
            name="shell-init wrapper",
            status=STATUS_PASS,
            detail=f"already configured: {ctx.shell_init_target}",
        )
    detail = f"needs change: install wrapper at {ctx.shell_init_target}"
    if ctx.shell_init_rc is not None:
        detail += f" and source it from {ctx.shell_init_rc}"
    return SetupCheck(
        id="shell_init",
        name="shell-init wrapper",
        status=STATUS_WARN,
        detail=detail,
    )


def _build_checks(ctx: SetupContext) -> list[SetupCheck]:
    checks: list[SetupCheck] = []

    uv_status = STATUS_PASS if ctx.uv_bin else STATUS_FAIL
    checks.append(
        SetupCheck(
            id="uv",
            name="uv",
            status=uv_status,
            detail=f"{_state_text(uv_status)}: {ctx.uv_bin or 'install uv and add to PATH'}",
            required=True,
        )
    )
    git_status = STATUS_PASS if ctx.git_bin else STATUS_FAIL
    checks.append(
        SetupCheck(
            id="git",
            name="git",
            status=git_status,
            detail=f"{_state_text(git_status)}: {ctx.git_bin or 'install git and add to PATH'}",
            required=True,
        )
    )
    tmux_status = STATUS_PASS if ctx.tmux_bin else STATUS_FAIL
    checks.append(
        SetupCheck(
            id="tmux",
            name="tmux",
            status=tmux_status,
            detail=f"{_state_text(tmux_status)}: {ctx.tmux_bin or 'install tmux and add to PATH'}",
            required=True,
        )
    )
    tmuxp_status = STATUS_PASS if ctx.tmuxp_bin else STATUS_WARN
    checks.append(
        SetupCheck(
            id="tmuxp",
            name="tmuxp",
            status=tmuxp_status,
            detail=f"{_state_text(tmuxp_status)}: {ctx.tmuxp_bin or 'optional; install if using b tmux load'}",
        )
    )
    runtime_status = STATUS_PASS if ctx.runtime_ok else STATUS_FAIL
    runtime_detail = f"{_state_text(runtime_status)}: {ctx.runtime_detail}"
    if not ctx.runtime_ok:
        runtime_detail += " (run: uv sync)"
    checks.append(
        SetupCheck(
            id="python_runtime",
            name="python runtime",
            status=runtime_status,
            detail=runtime_detail,
            required=True,
        )
    )
    checks.append(_self_update_check(ctx))

    path_status = STATUS_PASS if ctx.in_path else STATUS_WARN
    path_target = ctx.dest_dir if ctx.in_path else f"add {ctx.dest_dir} to shell profile"
    checks.append(
        SetupCheck(
            id="path",
            name="PATH",
            status=path_status,
            detail=f"{_state_text(path_status)}: {path_target}",
        )
    )

    checks.append(_b_launcher_check(ctx.dest, ctx.target))

    homebase_status = STATUS_PASS if ctx.homebase_dir.is_dir() else STATUS_FAIL
    checks.append(
        SetupCheck(
            id="homebase_dir",
            name=HOMEBASE_DIR_NAME,
            status=homebase_status,
            detail=f"{_state_text(homebase_status)}: {ctx.homebase_dir}",
            required=True,
        )
    )
    writable = ctx.homebase_dir.is_dir() and os.access(ctx.homebase_dir, os.W_OK)
    writable_status = STATUS_PASS if writable else STATUS_FAIL
    checks.append(
        SetupCheck(
            id="homebase_writable",
            name=".homebase writable",
            status=writable_status,
            detail=f"{_state_text(writable_status)}: {ctx.homebase_dir}",
            required=True,
        )
    )

    if ctx.config_exists:
        cfg_status = STATUS_PASS if ctx.config_valid else STATUS_FAIL
        checks.append(
            SetupCheck(
                id="config",
                name="config",
                status=cfg_status,
                detail=f"{_state_text(cfg_status)}: {ctx.config_path}",
                required=True,
            )
        )
    else:
        checks.append(
            SetupCheck(
                id="config",
                name="config",
                status=STATUS_WARN,
                detail=f"needs change: optional; create {ctx.config_path} if you need global config",
            )
        )

    gitignore_ok = _gitignore_has_cache_rule(ctx.homebase_gitignore)
    checks.append(
        SetupCheck(
            id="gitignore",
            name=".homebase/.gitignore",
            status=STATUS_PASS if gitignore_ok else STATUS_WARN,
            detail=f"{_state_text(STATUS_PASS if gitignore_ok else STATUS_WARN)}: "
            + ("contains cache.sqlite3" if gitignore_ok else "add cache.sqlite3 rule"),
        )
    )

    checks.append(_tmux_binding_check(ctx))
    checks.append(_completion_check(ctx))
    checks.append(_shell_init_check(ctx))
    return checks


# --- fix building ----------------------------------------------------


def _color_diff_lines(
    current_lines: list[str],
    desired_lines: list[str],
    *,
    header: str = "",
    max_lines: int = 80,
) -> tuple[str, ...]:
    """Return a coloured unified-diff representation as Rich-markup lines.

    - Removed lines are coloured red, added lines green, hunk headers
      cyan, and unchanged context dim.
    - Truncates the body at ``max_lines`` with a trailing summary so
      the preview pane never grows unbounded.
    - When both sides are identical, returns a single dim ``(no
      differences)`` line.
    """
    import difflib

    diff = list(
        difflib.unified_diff(
            current_lines,
            desired_lines,
            fromfile="current",
            tofile="desired",
            lineterm="",
            n=2,
        )
    )
    if not diff:
        return ((f"{header}\n" if header else "") + "[dim](no differences)[/]",)

    out: list[str] = []
    if header:
        out.append(f"[dim]{header}[/]")
    for line in diff:
        if line.startswith("---") or line.startswith("+++"):
            out.append(f"[dim]{line}[/]")
        elif line.startswith("@@"):
            out.append(f"[bright_cyan]{line}[/]")
        elif line.startswith("+"):
            out.append(f"[bright_green]{line}[/]")
        elif line.startswith("-"):
            out.append(f"[bright_red]{line}[/]")
        else:
            out.append(f"[dim]{line}[/]")
    if len(out) > max_lines:
        truncated = len(out) - max_lines
        out = out[:max_lines]
        out.append(f"[dim]… (diff truncated; {truncated} more line(s))[/]")
    return tuple(out)


def _gitignore_preview_create(path: Path) -> tuple[str, ...]:
    current = _read_text_lines(path)
    desired = list(current)
    if "cache.sqlite3" not in [line.strip() for line in desired]:
        if desired and desired[-1].strip() != "":
            desired.append("")
        desired.append("cache.sqlite3")
    return _color_diff_lines(current, desired, header=f"# {path}")


def _gitignore_preview_remove(path: Path) -> tuple[str, ...]:
    current = _read_text_lines(path)
    desired = [line for line in current if line.strip() != "cache.sqlite3"]
    return _color_diff_lines(current, desired, header=f"# {path}")


def _inline_char_diff_pair(old: str, new: str) -> tuple[str, str]:
    """Return (old_markup, new_markup) where character spans that
    differ get Rich markup:

    - chars in ``old`` not in ``new`` → red strikethrough
    - chars in ``new`` not in ``old`` → bold green
    - matching chars are left as-is

    The output is intended for side-by-side display of a single-line
    config change (e.g. a tmux ``bind-key`` line).
    """
    import difflib

    from rich.markup import escape

    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    old_out: list[str] = []
    new_out: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        a, b = old[i1:i2], new[j1:j2]
        if op == "equal":
            old_out.append(escape(a))
            new_out.append(escape(b))
            continue
        if a:
            old_out.append(f"[bold strike bright_red]{escape(a)}[/]")
        if b:
            new_out.append(f"[bold bright_green]{escape(b)}[/]")
    return "".join(old_out), "".join(new_out)


def _tmux_preview_create(
    existing: tuple[str, ...], expected: str
) -> tuple[str, ...]:
    from rich.markup import escape

    if not existing:
        return (
            "[dim]# tmux save binding[/]",
            "[dim](no current binding)[/]",
            f"[bold bright_green]+ {escape(expected)}[/]",
        )
    old_markup, new_markup = _inline_char_diff_pair(existing[0], expected)
    out = [
        "[dim]# tmux save binding[/]",
        f"[bright_red]- {old_markup}[/]",
        f"[bright_green]+ {new_markup}[/]",
    ]
    if len(existing) > 1:
        out.append("")
        out.append(
            f"[dim]({len(existing) - 1} additional existing binding(s) "
            "will be removed)[/]"
        )
    return tuple(out)


def _tmux_preview_remove(existing: tuple[str, ...]) -> tuple[str, ...]:
    from rich.markup import escape

    if not existing:
        return ("[dim](nothing to remove)[/]",)
    out = ["[dim]# tmux save binding (remove)[/]"]
    for line in existing:
        out.append(f"[bold strike bright_red]- {escape(line)}[/]")
    return tuple(out)


def _read_text_lines(path: Path) -> list[str]:
    """Read file as a list of lines (without trailing newlines).
    Returns ``[]`` if the file doesn't exist or can't be read."""
    if not path.is_file():
        return []
    try:
        return path.read_text().splitlines()
    except OSError:
        return []


def _build_fixes(ctx: SetupContext) -> list[SetupFix]:
    """Always emit the full set of setup items.

    Each fix encodes its current state (`currently_present` /
    `currently_correct`) plus optional `apply_create` / `apply_remove`
    transitions. The UI uses the current state to compute default
    selection, and translates the user's selection-vs-current diff
    into create / remove / keep / absent intents at apply time.
    """
    fixes: list[SetupFix] = []

    # --- base folder (the workspace root that holds .homebase) ----
    base_present = ctx.base_dir.is_dir()
    base_dir_local = ctx.base_dir
    fixes.append(
        SetupFix(
            id="base_folder",
            title=f"base workspace folder ({ctx.base_dir})",
            description="Top-level folder that holds homebase state and project subdirs.",
            currently_present=base_present,
            currently_correct=base_present,
            required=True,
            recommended=True,
            apply_create=(lambda p=base_dir_local: p.mkdir(parents=True, exist_ok=True)),
            apply_remove=None,  # NEVER auto-remove the user's workspace
            preview_create=(
                f"current: {ctx.base_dir} (missing)",
                f"desired: mkdir -p {ctx.base_dir}",
            ),
            preview_remove=(
                "uninstall not supported: remove the workspace folder by hand if you really want to.",
            ),
            current_state_text=(
                f"present: {ctx.base_dir}"
                if base_present
                else f"missing: {ctx.base_dir}"
            ),
        )
    )

    # --- .homebase directory --------------------------------------
    hb_present = ctx.homebase_dir.is_dir()
    hb_dir_local = ctx.homebase_dir
    fixes.append(
        SetupFix(
            id="homebase_dir",
            title=f"homebase state directory ({ctx.homebase_dir})",
            description="Holds the cache database, global config, and per-run report.",
            currently_present=hb_present,
            currently_correct=hb_present,
            required=True,
            recommended=True,
            apply_create=(lambda p=hb_dir_local: p.mkdir(parents=True, exist_ok=True)),
            apply_remove=(lambda p=hb_dir_local: _remove_dir_if_exists(p)),
            requires=("base_folder",),
            preview_create=(
                f"current: {ctx.homebase_dir} (missing)",
                f"desired: mkdir -p {ctx.homebase_dir}",
            ),
            preview_remove=(
                f"current: {ctx.homebase_dir} (present)",
                f"removing wipes cache.sqlite3 and {ctx.config_path}",
            ),
            current_state_text=(
                f"present: {ctx.homebase_dir}"
                if hb_present
                else f"missing: {ctx.homebase_dir}"
            ),
        )
    )

    # --- ~/.local/bin (launcher dir) ------------------------------
    bin_present = ctx.dest_dir.is_dir()
    dest_dir_local = ctx.dest_dir
    fixes.append(
        SetupFix(
            id="local_bin",
            title=f"launcher dir on PATH ({ctx.dest_dir})",
            description="Directory in PATH where the `b` launcher symlink lives.",
            currently_present=bin_present,
            currently_correct=bin_present,
            required=True,
            recommended=True,
            apply_create=(lambda p=dest_dir_local: p.mkdir(parents=True, exist_ok=True)),
            apply_remove=None,  # Shared with many tools; never auto-remove.
            preview_create=(
                f"current: {ctx.dest_dir} (missing)",
                f"desired: mkdir -p {ctx.dest_dir}",
            ),
            preview_remove=(
                "uninstall not supported: this directory is shared with other tools.",
            ),
            current_state_text=(
                f"present: {ctx.dest_dir}"
                if bin_present
                else f"missing: {ctx.dest_dir}"
            ),
        )
    )

    # --- b launcher symlink ---------------------------------------
    launcher_dest = ctx.dest
    launcher_target = ctx.target
    launcher_present = ctx.dest.exists() or ctx.dest.is_symlink()
    launcher_correct = False
    if ctx.dest.is_symlink():
        try:
            launcher_correct = ctx.dest.resolve() == ctx.target
        except OSError:
            launcher_correct = False
    if ctx.dest.is_symlink():
        try:
            launcher_state = f"symlink -> {ctx.dest.resolve()}"
        except OSError:
            launcher_state = "broken symlink"
    elif ctx.dest.exists():
        launcher_state = "exists, not a symlink"
    else:
        launcher_state = "missing"

    def _fix_launcher(
        dest: Path = launcher_dest, target: Path = launcher_target
    ) -> None:
        # Refuse to create a symlink pointing at something that
        # doesn't exist or isn't executable — that's the bug that
        # bricked the user's `b` command when bin_dir was wrong.
        if not target.exists():
            raise OSError(
                f"refusing to symlink {dest} → {target}: target does not exist"
            )
        if not target.is_file() or not os.access(target, os.X_OK):
            raise OSError(
                f"refusing to symlink {dest} → {target}: target is not executable"
            )
        if dest.exists() and not dest.is_symlink():
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = dest.with_name(f"{dest.name}.bak-{ts}")
            dest.rename(backup)
            print(f"- moved existing file: {backup}")
        elif dest.is_symlink():
            dest.unlink()
        dest.symlink_to(target)

    def _remove_launcher(dest: Path = launcher_dest) -> None:
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            dest.unlink()

    fixes.append(
        SetupFix(
            id="launcher_symlink",
            title=f"`b` launcher symlink ({ctx.dest})",
            description=f"Symlink that exposes the `b` command on PATH ({ctx.dest} → {ctx.target}).",
            currently_present=launcher_present,
            currently_correct=launcher_correct,
            required=True,
            recommended=True,
            apply_create=_fix_launcher,
            apply_remove=_remove_launcher,
            requires=("local_bin",),
            preview_create=(
                f"current: {ctx.dest} ({launcher_state})",
                f"desired: {ctx.dest} -> {ctx.target}",
            ),
            preview_remove=(
                f"current: {ctx.dest} ({launcher_state})",
                f"unlink: {ctx.dest} (uninstalls `b` from PATH)",
            ),
            current_state_text=f"{ctx.dest}: {launcher_state}",
        )
    )

    # --- .homebase/.gitignore cache rule ---------------------------
    gi_present = ctx.homebase_gitignore.is_file()
    gi_correct = _gitignore_has_cache_rule(ctx.homebase_gitignore)
    gi_path = ctx.homebase_gitignore

    def _fix_gitignore(path: Path = gi_path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_homebase_gitignore(path)

    def _remove_gitignore(path: Path = gi_path) -> None:
        _remove_homebase_gitignore_rule(path)

    fixes.append(
        SetupFix(
            id="gitignore_cache",
            title="`.homebase/.gitignore` ignores cache.sqlite3",
            description="Keeps the cache database out of VCS status.",
            currently_present=gi_present,
            currently_correct=gi_correct,
            required=False,
            recommended=True,
            apply_create=_fix_gitignore,
            apply_remove=_remove_gitignore,
            requires=("homebase_dir",),
            preview_create=_gitignore_preview_create(ctx.homebase_gitignore),
            preview_remove=_gitignore_preview_remove(ctx.homebase_gitignore),
            current_state_text=(
                "rule present" if gi_correct
                else ("file exists but rule missing" if gi_present else "file does not exist")
            ),
        )
    )

    # --- tmux save binding ----------------------------------------
    tmux_present = bool(ctx.existing_tmux_binding_lines)
    tmux_correct = has_recommended_tmux_binding(
        ctx.tmux_conf_text, ctx.expected_tmux_binding
    )
    tmux_path_local = ctx.tmux_conf_path
    tmux_expected = ctx.expected_tmux_binding

    def _fix_tmux(
        path: Path = tmux_path_local, line: str = tmux_expected
    ) -> None:
        write_tmux_binding(path, line)

    def _remove_tmux(path: Path = tmux_path_local) -> None:
        _remove_tmux_binding(path)

    fixes.append(
        SetupFix(
            id="tmux_binding",
            title="tmux `prefix t` save binding",
            description="Hotkey in tmux that saves the current pane layout via `b tmux save`.",
            currently_present=tmux_present,
            currently_correct=tmux_correct,
            required=False,
            recommended=True,
            apply_create=_fix_tmux,
            apply_remove=_remove_tmux,
            preview_create=_tmux_preview_create(ctx.existing_tmux_binding_lines, ctx.expected_tmux_binding),
            preview_remove=_tmux_preview_remove(ctx.existing_tmux_binding_lines),
            current_state_text=(
                "recommended binding present" if tmux_correct
                else (f"stale binding: {ctx.existing_tmux_binding_lines[0]}" if ctx.existing_tmux_binding_lines
                      else "no binding")
            ),
        )
    )

    # --- shell completion file ------------------------------------
    if ctx.completion_shell and ctx.completion_target is not None and ctx.expected_completion:
        comp_path = ctx.completion_target
        comp_body = ctx.expected_completion
        comp_present = comp_path.exists()
        comp_correct = ctx.completion_ok

        def _fix_completion(path: Path = comp_path, body: str = comp_body) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)

        def _remove_completion(path: Path = comp_path) -> None:
            _remove_file_if_exists(path)

        fixes.append(
            SetupFix(
                id="shell_completion",
                title=f"{ctx.completion_shell} tab completion ({ctx.completion_target})",
                description=f"Tab-completion script that drives `b <TAB>` in {ctx.completion_shell}.",
                currently_present=comp_present,
                currently_correct=comp_correct,
                required=False,
                recommended=True,
                apply_create=_fix_completion,
                apply_remove=_remove_completion,
                preview_create=_color_diff_lines(
                    _read_text_lines(comp_path),
                    comp_body.splitlines(),
                    header=f"# {comp_path}",
                ),
                preview_remove=_color_diff_lines(
                    _read_text_lines(comp_path),
                    [],
                    header=f"# delete {comp_path}",
                ),
                current_state_text=(
                    "installed" if comp_correct
                    else ("present but stale" if comp_present else "not installed")
                ),
            )
        )

    # --- shell-init wrapper ---------------------------------------
    if ctx.completion_shell and ctx.shell_init_target is not None and ctx.expected_shell_init:
        init_path = ctx.shell_init_target
        init_body = ctx.expected_shell_init
        init_rc = ctx.shell_init_rc
        init_shell = ctx.completion_shell
        init_present = init_path.is_file()
        init_correct = ctx.shell_init_ok

        def _fix_shell_init(
            path: Path = init_path,
            body: str = init_body,
            rc: Path | None = init_rc,
            shell: str = init_shell,
        ) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
            if rc is None:
                return
            source_line = _shell_init_source_line(shell, path)
            try:
                existing = rc.read_text() if rc.is_file() else ""
            except OSError:
                existing = ""
            if source_line in existing:
                return
            rc.parent.mkdir(parents=True, exist_ok=True)
            with rc.open("a") as fh:
                if existing and not existing.endswith("\n"):
                    fh.write("\n")
                fh.write(source_line + "\n")

        def _remove_shell_init(
            path: Path = init_path,
            rc: Path | None = init_rc,
            shell: str = init_shell,
        ) -> None:
            _remove_file_if_exists(path)
            if rc is None:
                return
            source_line = _shell_init_source_line(shell, path)
            _remove_shell_init_source_line(rc, source_line)

        preview_create_lines = list(
            _color_diff_lines(
                _read_text_lines(init_path),
                init_body.splitlines(),
                header=f"# {init_path}",
                max_lines=40,
            )
        )
        preview_remove_lines = list(
            _color_diff_lines(
                _read_text_lines(init_path),
                [],
                header=f"# delete {init_path}",
                max_lines=40,
            )
        )
        if ctx.shell_init_rc is not None:
            source_line = _shell_init_source_line(init_shell, init_path)
            rc_current = _read_text_lines(ctx.shell_init_rc)
            rc_desired_create = (
                rc_current if source_line in rc_current else rc_current + [source_line]
            )
            rc_desired_remove = [line for line in rc_current if line.strip() != source_line.strip()]
            preview_create_lines.append("")
            preview_create_lines.extend(
                _color_diff_lines(
                    rc_current,
                    rc_desired_create,
                    header=f"# {ctx.shell_init_rc}",
                    max_lines=10,
                )
            )
            preview_remove_lines.append("")
            preview_remove_lines.extend(
                _color_diff_lines(
                    rc_current,
                    rc_desired_remove,
                    header=f"# {ctx.shell_init_rc}",
                    max_lines=10,
                )
            )
        preview_create = preview_create_lines
        preview_remove = preview_remove_lines

        fixes.append(
            SetupFix(
                id="shell_init",
                title=f"{ctx.completion_shell} shell-init wrapper",
                description="Lets `b` request a parent-shell `cd` handoff after running.",
                currently_present=init_present,
                currently_correct=init_correct,
                required=False,
                recommended=True,
                apply_create=_fix_shell_init,
                apply_remove=_remove_shell_init,
                preview_create=tuple(preview_create),
                preview_remove=tuple(preview_remove),
                current_state_text=(
                    "installed" if init_correct
                    else ("file exists but rc source line missing or stale" if init_present else "not installed")
                ),
            )
        )

    return _order_fixes(fixes)


def _order_fixes(fixes: list[SetupFix]) -> list[SetupFix]:
    """Topologically order fixes by `requires`, preserving input order
    among independent fixes."""
    by_id = {fx.id: fx for fx in fixes}
    visited: set[str] = set()
    ordered: list[SetupFix] = []

    def _visit(fid: str, stack: tuple[str, ...]) -> None:
        if fid in visited:
            return
        if fid in stack:
            cycle = " -> ".join((*stack, fid))
            raise ValueError(f"fix dependency cycle: {cycle}")
        fix = by_id.get(fid)
        if fix is None:
            return
        for dep in fix.requires:
            _visit(dep, stack + (fid,))
        visited.add(fid)
        ordered.append(fix)

    for fx in fixes:
        _visit(fx.id, ())
    return ordered


# --- selection + apply ----------------------------------------------


def _select_fix_ids(
    fixes: list[SetupFix],
    *,
    select_fix_ids_fn: Callable[[list[SetupFix]], set[str] | None] | None,
    prompt_yes_no: Callable[[str, bool], bool],
) -> set[str] | None:
    """Decide which fix ids the user wants present.

    - If ``select_fix_ids_fn`` is provided (test injection), it is
      called with the fix list and may return ``None`` to cancel.
    - Otherwise prompts via ``prompt_yes_no(question, default)`` once
      per fix, using ``fix.selected_default`` as the default answer.

    Returns the set of selected ids, or ``None`` when the caller
    signalled cancel. The TTY-interactive Textual app does **not**
    go through this code path — it runs inside ``run_setup_app`` —
    so there is no fallback that could land the user in a stale
    selector with empty defaults."""
    if not fixes:
        return set()
    if select_fix_ids_fn is not None:
        chosen = select_fix_ids_fn(fixes)
        return None if chosen is None else set(chosen)
    selected_ids: set[str] = set()
    for fix in fixes:
        if prompt_yes_no(f"{fix.title}?", fix.selected_default):
            selected_ids.add(fix.id)
    return selected_ids


def _apply_intents(
    fixes: list[SetupFix],
    selected_ids: set[str],
    *,
    dry_run: bool,
    log_fn: Callable[[str, bool], None] | None = None,
) -> list[FixResult]:
    """Run create/remove transitions for the selected fixes.

    ``log_fn(line, is_error)`` receives every progress message; default
    routes to stdout/stderr so the non-interactive prompt loop keeps
    its current output. The Textual modal overrides ``log_fn`` to
    stream the log into its RichLog widget."""
    from .setup_model import (
        INTENT_ABSENT,
        INTENT_CANNOT_CREATE,
        INTENT_CANNOT_REMOVE,
        INTENT_CREATE,
        INTENT_KEEP,
    )

    def _emit(line: str, err: bool = False) -> None:
        if log_fn is not None:
            log_fn(line, err)
            return
        print(line, file=sys.stderr if err else sys.stdout)

    results: list[FixResult] = []
    for fix in fixes:
        intent = fix.intent(selected=fix.id in selected_ids)
        if intent in {INTENT_KEEP, INTENT_ABSENT}:
            results.append(
                FixResult(id=fix.id, title=fix.title, intent=intent, success=True)
            )
            continue
        if intent == INTENT_CANNOT_CREATE:
            err = "no apply_create available; cannot create"
            _emit(f"- skip ({fix.id}): {err}", err=True)
            results.append(
                FixResult(
                    id=fix.id, title=fix.title, intent=intent,
                    success=False, error=err,
                )
            )
            continue
        if intent == INTENT_CANNOT_REMOVE:
            err = "no apply_remove available; cannot uninstall via setup"
            _emit(f"- skip ({fix.id}): {err}", err=True)
            results.append(
                FixResult(
                    id=fix.id, title=fix.title, intent=intent,
                    success=False, error=err,
                )
            )
            continue
        action_label = "create" if intent == INTENT_CREATE else "remove"
        if dry_run:
            _emit(f"- would {action_label}: {fix.title}")
            results.append(
                FixResult(id=fix.id, title=fix.title, intent=intent, success=True)
            )
            continue
        callback = fix.apply_create if intent == INTENT_CREATE else fix.apply_remove
        try:
            assert callback is not None
            callback()
            _emit(f"- {action_label}d: {fix.title}")
            if fix.id == "tmux_binding" and intent == INTENT_CREATE:
                _emit("  run now: tmux source-file ~/.tmux.conf")
            if fix.id == "shell_init" and intent == INTENT_CREATE:
                _emit("- open a NEW shell for the wrapper to take effect")
            results.append(
                FixResult(id=fix.id, title=fix.title, intent=intent, success=True)
            )
        except (OSError, ValueError) as exc:
            _emit(f"- {action_label} failed ({fix.id}): {exc}", err=True)
            results.append(
                FixResult(
                    id=fix.id, title=fix.title, intent=intent,
                    success=False, error=str(exc),
                )
            )
    return results


def _run_fix_loop(
    fixes: list[SetupFix],
    *,
    select_fix_ids_fn: Callable[[list[SetupFix]], set[str] | None] | None,
    prompt_yes_no: Callable[[str, bool], bool],
    dry_run: bool,
    allow_rerun_failed: bool,
) -> list[FixResult]:
    """Non-TTY / test fix loop. The TTY-interactive path is the
    Textual app inside :func:`_run_app_loop`; this function exists
    only for the prompt fallback (``b setup`` piped, CI, or tests
    that inject ``select_fix_ids_fn``)."""
    if not fixes:
        return []
    selected_ids = _select_fix_ids(
        fixes,
        select_fix_ids_fn=select_fix_ids_fn,
        prompt_yes_no=prompt_yes_no,
    )
    if selected_ids is None:
        # Caller cancelled (callback returned None). Don't apply
        # anything — explicitly safe.
        return []
    results = _apply_intents(fixes, selected_ids, dry_run=dry_run)
    if dry_run or not allow_rerun_failed:
        return results
    failed = [r for r in results if not r.success]
    if not failed:
        return results
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return results
    if not prompt_yes_no(
        f"{len(failed)} action(s) failed. Re-run them?", False
    ):
        return results
    failed_ids = {r.id for r in failed}
    rerun = [fx for fx in fixes if fx.id in failed_ids]
    rerun_selected = _select_fix_ids(
        rerun,
        select_fix_ids_fn=select_fix_ids_fn,
        prompt_yes_no=prompt_yes_no,
    )
    if rerun_selected is None:
        return results
    rerun_results = _apply_intents(rerun, rerun_selected, dry_run=dry_run)
    rerun_by_id = {r.id: r for r in rerun_results}
    return [rerun_by_id.get(r.id, r) if not r.success else r for r in results]


# --- summary ---------------------------------------------------------


def _compute_summary(
    checks: list[SetupCheck],
    results: list[FixResult],
    *,
    dry_run: bool,
) -> SetupSummary:
    from .setup_model import INTENT_CREATE, INTENT_KEEP, INTENT_REMOVE

    pass_count = sum(1 for c in checks if c.status == STATUS_PASS)
    warn_count = sum(1 for c in checks if c.status == STATUS_WARN)
    fail_count = sum(1 for c in checks if c.status == STATUS_FAIL)
    required_fail = any(c.required and c.status == STATUS_FAIL for c in checks)
    create_done = sum(1 for r in results if r.success and r.intent == INTENT_CREATE)
    remove_done = sum(1 for r in results if r.success and r.intent == INTENT_REMOVE)
    keep_count = sum(1 for r in results if r.intent == INTENT_KEEP)
    failures = [r for r in results if not r.success]
    failed_count = 0 if dry_run else len(failures)
    hard_fail = required_fail or failed_count > 0
    succeeded_titles = [r.title for r in results if r.success and not r.skipped]
    failed_titles = [r.title for r in failures]
    return SetupSummary(
        pass_count=pass_count,
        warn_count=warn_count,
        fail_count=fail_count,
        hard_fail=hard_fail,
        create_count=create_done,
        remove_count=remove_done,
        keep_count=keep_count,
        failed_count=failed_count,
        succeeded_titles=succeeded_titles,
        failed_titles=failed_titles,
    )


def _print_fix_execution_summary(
    results: list[FixResult],
    *,
    dry_run: bool,
) -> None:
    from .setup_model import INTENT_CREATE, INTENT_KEEP, INTENT_REMOVE

    if not results:
        return
    creates = [r for r in results if r.intent == INTENT_CREATE]
    removes = [r for r in results if r.intent == INTENT_REMOVE]
    keeps = [r for r in results if r.intent == INTENT_KEEP]
    failures = [r for r in results if not r.success]
    print(
        f"- plan: create={len(creates)} remove={len(removes)} keep={len(keeps)}"
    )
    if dry_run:
        return
    print(
        f"- results: succeeded={sum(1 for r in results if r.success and not r.skipped)} "
        f"failed={len(failures)}"
    )
    if creates:
        print("- created:")
        for r in creates:
            print(f"  - {r.title}{' [FAILED]' if not r.success else ''}")
    if removes:
        print("- removed:")
        for r in removes:
            print(f"  - {r.title}{' [FAILED]' if not r.success else ''}")
    if failures:
        print("- failures:")
        for r in failures:
            print(f"  - {r.title}: {r.error}")


# --- persisted report ------------------------------------------------


SETUP_REPORT_FILE_NAME = "setup-report.json"


def _report_payload(
    *,
    ctx: SetupContext,
    initial_checks: list[SetupCheck],
    final_checks: list[SetupCheck],
    fixes: list[SetupFix],
    results: list[FixResult],
    summary: SetupSummary,
    dry_run: bool,
) -> dict:
    def _check_to_dict(c: SetupCheck) -> dict:
        return {
            "id": c.id,
            "name": c.name,
            "status": c.status,
            "detail": c.detail,
            "required": c.required,
            "extra_lines": list(c.extra_lines),
        }

    def _fix_to_dict(fx: SetupFix) -> dict:
        return {
            "id": fx.id,
            "title": fx.title,
            "description": fx.description,
            "required": fx.required,
            "recommended": fx.recommended,
            "currently_present": fx.currently_present,
            "currently_correct": fx.currently_correct,
            "selected_default": fx.selected_default,
            "current_state_text": fx.current_state_text,
            "requires": list(fx.requires),
            "preview_create": list(fx.preview_create),
            "preview_remove": list(fx.preview_remove),
            "supports_create": fx.apply_create is not None,
            "supports_remove": fx.apply_remove is not None,
        }

    def _result_to_dict(r: FixResult) -> dict:
        return {
            "id": r.id,
            "title": r.title,
            "intent": r.intent,
            "success": r.success,
            "error": r.error,
        }

    return {
        "homebase": {
            "base_dir": str(ctx.base_dir),
            "bin_dir": str(ctx.bin_dir),
            "homebase_dir": str(ctx.homebase_dir),
            "dry_run": dry_run,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        },
        "diagnostics": {
            "uv": ctx.uv_bin,
            "git": ctx.git_bin,
            "tmux": ctx.tmux_bin,
            "tmuxp": ctx.tmuxp_bin,
            "python": str(Path(sys.executable).resolve())
            if str(sys.executable).strip()
            else None,
            "launcher": str(ctx.launcher_path) if ctx.launcher_path is not None else None,
            "shell": ctx.completion_shell,
            "update_cmd": ctx.update_cmd,
            "update_detail": ctx.update_detail,
        },
        "checks": [_check_to_dict(c) for c in initial_checks],
        "final_checks": [_check_to_dict(c) for c in final_checks],
        "fixes": {
            "available": [_fix_to_dict(fx) for fx in fixes],
            "results": [_result_to_dict(r) for r in results],
        },
        "summary": {
            "pass": summary.pass_count,
            "warn": summary.warn_count,
            "fail": summary.fail_count,
            "hard_fail": summary.hard_fail,
            "failed": summary.failed_count,
            "create": summary.create_count,
            "remove": summary.remove_count,
            "keep": summary.keep_count,
            "exit_code": summary.exit_code,
        },
    }


def _persist_report(homebase_dir: Path, payload: dict) -> None:
    if not homebase_dir.is_dir():
        return
    target = homebase_dir / SETUP_REPORT_FILE_NAME
    try:
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"- could not persist setup report: {exc}", file=sys.stderr)


def _run_app_loop(
    base_dir: Path,
    bin_dir: Path,
    *,
    tmux_bin_candidates: tuple[str, ...],
    completion_script_fn: Callable[[str], str] | None,
    shell_init_script_fn: Callable[[str], str] | None,
    initial_ctx: SetupContext,
    initial_checks: list[SetupCheck],
    initial_fixes: list[SetupFix],
    dry_run: bool,
    prompt_yes_no: Callable[[str, bool], bool],
    allow_rerun_failed: bool,
) -> list[FixResult]:
    """Run the Textual app in a loop, refreshing state when the user
    chooses "Back to setup" after applying. Returns the accumulated
    list of FixResults from all apply rounds.

    If the Textual app can't start (import fails, no terminal), aborts
    and returns whatever results were already collected — it does
    **not** fall back to anything that could apply changes with an
    empty selection set."""
    _ = prompt_yes_no  # kept in signature for back-compat; unused

    try:
        from .setup_app import run_setup_app
    except ImportError as exc:
        print(
            f"- setup app unavailable: {exc}; aborting without changes.",
            file=sys.stderr,
        )
        return []

    all_results: list[FixResult] = []
    current_ctx = initial_ctx
    current_checks = initial_checks
    current_fixes = initial_fixes

    while True:
        outcome = run_setup_app(
            current_ctx,
            current_checks,
            current_fixes,
            apply_fn=_apply_intents,
            dry_run=dry_run,
        )
        if outcome is None:
            # Either Textual import failed inside run_setup_app, or
            # the user cancelled via Ctrl+Q / window-close. In every
            # case the safe answer is "no further changes" — never
            # fall through to a legacy selector with empty defaults
            # (that's how user data was wiped previously).
            print(
                "- setup app cancelled; "
                f"{len(all_results)} action(s) already applied.",
                file=sys.stderr,
            )
            return all_results
        all_results.extend(outcome.results)
        if outcome.action in {"exit", "cancel"}:
            return all_results
        # action == "continue" → refresh state and re-launch
        current_ctx = _gather_context(
            base_dir,
            bin_dir,
            tmux_bin_candidates=tmux_bin_candidates,
            completion_script_fn=completion_script_fn,
            shell_init_script_fn=shell_init_script_fn,
        )
        current_checks = _build_checks(current_ctx)
        current_fixes = _build_fixes(current_ctx)


# --- entry point -----------------------------------------------------


def cmd_setup(
    base_dir: Path,
    bin_dir: Path,
    *,
    tmux_bin_candidates: tuple[str, ...],
    prompt_yes_no: Callable[[str, bool], bool],
    completion_script_fn: Callable[[str], str] | None = None,
    shell_init_script_fn: Callable[[str], str] | None = None,
    select_fix_ids_fn: Callable[[list[SetupFix]], set[str] | None] | None = None,
    dry_run: bool = False,
    json_output: bool = False,
    allow_rerun_failed: bool = True,
) -> int:
    ctx = _gather_context(
        base_dir,
        bin_dir,
        tmux_bin_candidates=tmux_bin_candidates,
        completion_script_fn=completion_script_fn,
        shell_init_script_fn=shell_init_script_fn,
    )
    initial_checks = _build_checks(ctx)
    fixes = _build_fixes(ctx)

    if not json_output:
        print("setup: homebase")
        if dry_run:
            print("mode: dry-run (no files will be modified)")
        print(f"base dir: {base_dir}")
        print("change base dir: --base-folder <path> or BASE_FOLDER=<path>")
        print("")
        print("validation:")
        render_checks(initial_checks)
        print("")

    results: list[FixResult]
    if json_output:
        # JSON mode is informational only. Skip fix prompts entirely so
        # stdout stays valid JSON; users invoke setup without --json to
        # actually apply fixes. "Keep what's there" is the safe no-op.
        from .setup_model import INTENT_KEEP

        results = [
            FixResult(id=fx.id, title=fx.title, intent=INTENT_KEEP, success=True)
            for fx in fixes
        ]
    elif select_fix_ids_fn is None and (
        sys.stdin.isatty() and sys.stdout.isatty()
    ):
        results = _run_app_loop(
            base_dir,
            bin_dir,
            tmux_bin_candidates=tmux_bin_candidates,
            completion_script_fn=completion_script_fn,
            shell_init_script_fn=shell_init_script_fn,
            initial_ctx=ctx,
            initial_checks=initial_checks,
            initial_fixes=fixes,
            dry_run=dry_run,
            prompt_yes_no=prompt_yes_no,
            allow_rerun_failed=allow_rerun_failed,
        )
    else:
        results = _run_fix_loop(
            fixes,
            select_fix_ids_fn=select_fix_ids_fn,
            prompt_yes_no=prompt_yes_no,
            dry_run=dry_run,
            allow_rerun_failed=allow_rerun_failed,
        )

    if not json_output:
        _print_fix_execution_summary(results, dry_run=dry_run)

    final_ctx = _gather_context(
        base_dir,
        bin_dir,
        tmux_bin_candidates=tmux_bin_candidates,
        completion_script_fn=completion_script_fn,
        shell_init_script_fn=shell_init_script_fn,
    )
    final_checks = _build_checks(final_ctx)
    summary = _compute_summary(final_checks, results, dry_run=dry_run)

    payload = _report_payload(
        ctx=final_ctx,
        initial_checks=initial_checks,
        final_checks=final_checks,
        fixes=fixes,
        results=results,
        summary=summary,
        dry_run=dry_run,
    )

    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("")
        print("final validation:")
        render_summary(summary)
        print("")
        print("next steps:")
        print(f"- optional config: create/edit {ctx.config_path}")
        print("- docs: README.md (Technical State Files + Kitchen Sink Config)")
        print("- run: b ls")

    _persist_report(final_ctx.homebase_dir, payload)
    return summary.exit_code
