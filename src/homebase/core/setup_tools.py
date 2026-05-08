from __future__ import annotations

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


def tmux_save_binding_lines(tmux_conf_text: str) -> list[str]:
    out: list[str] = []
    for raw in tmux_conf_text.splitlines():
        line = str(raw).strip()
        if not line or line.startswith("#"):
            continue
        if "b tmux save" not in line:
            continue
        if "bind-key" in line or line.startswith("bind "):
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


def _runtime_imports_ok() -> tuple[bool, str]:
    try:
        import textual  # noqa: F401
        import yaml  # noqa: F401
    except ImportError as exc:
        return False, f"missing runtime python deps ({exc})"
    return True, "python runtime deps available"


def _print_check(status: str, name: str, detail: str) -> None:
    print(f"- [{status}] {name}: {detail}")


def _state_text(status: str) -> str:
    if status == "PASS":
        return "already configured"
    if status == "FAIL":
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


def cmd_setup(
    base_dir: Path,
    bin_dir: Path,
    *,
    tmux_bin_candidates: tuple[str, ...],
    prompt_yes_no: Callable[[str, bool], bool],
    completion_script_fn: Callable[[str], str] | None = None,
    dry_run: bool = False,
) -> int:
    print("setup: homebase")
    if dry_run:
        print("mode: dry-run (no files will be modified)")
    print(f"base dir: {base_dir}")
    print("change base dir: --base-folder <path> or BASE_FOLDER=<path>")
    print("")

    homebase_dir = base_dir / HOMEBASE_DIR_NAME
    config_path = homebase_dir / GLOBAL_CONFIG_FILE_NAME
    homebase_gitignore = homebase_dir / ".gitignore"
    target = (bin_dir / "b").resolve()
    dest_dir = Path.home() / ".local/bin"
    dest = dest_dir / "b"

    uv_bin = find_executable("uv", ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"))
    git_bin = find_executable("git")
    tmux_bin = find_executable("tmux", tmux_bin_candidates)
    tmuxp_bin = find_executable("tmuxp")
    runtime_ok, runtime_detail = _runtime_imports_ok()

    print("validation:")
    uv_status = "PASS" if uv_bin else "FAIL"
    git_status = "PASS" if git_bin else "FAIL"
    tmux_status = "PASS" if tmux_bin else "FAIL"
    _print_check(uv_status, "uv", f"{_state_text(uv_status)}: {uv_bin or 'install uv and add to PATH'}")
    _print_check(
        git_status,
        "git",
        f"{_state_text(git_status)}: {git_bin or 'install git and add to PATH'}",
    )
    _print_check(
        tmux_status,
        "tmux",
        f"{_state_text(tmux_status)}: {tmux_bin or 'install tmux and add to PATH'}",
    )
    _print_check(
        "PASS" if tmuxp_bin else "WARN",
        "tmuxp",
        f"{_state_text('PASS' if tmuxp_bin else 'WARN')}: {tmuxp_bin or 'optional; install if using b tmux load'}",
    )
    _print_check(
        "PASS" if runtime_ok else "FAIL",
        "python runtime",
        f"{_state_text('PASS' if runtime_ok else 'FAIL')}: {runtime_detail}" + (" (run: uv sync)" if not runtime_ok else ""),
    )

    path_entries = os.environ.get("PATH", "").split(":")
    in_path = any(Path(p).expanduser().resolve() == dest_dir.resolve() for p in path_entries if p)
    _print_check(
        "PASS" if in_path else "WARN",
        "PATH",
        f"{_state_text('PASS' if in_path else 'WARN')}: {dest_dir if in_path else f'add {dest_dir} to shell profile'}",
    )

    if dest.is_symlink():
        try:
            status = "PASS" if dest.resolve() == target else "WARN"
            detail = f"{dest} -> {dest.resolve()}"
        except OSError:
            status = "WARN"
            detail = f"broken symlink: {dest}"
    elif dest.exists():
        status = "WARN"
        detail = f"exists and is not symlink: {dest}"
    else:
        status = "WARN"
        detail = f"missing symlink: {dest} -> {target}"
    _print_check(status, "b launcher", detail)

    homebase_status = "PASS" if homebase_dir.is_dir() else "WARN"
    _print_check(homebase_status, HOMEBASE_DIR_NAME, f"{_state_text(homebase_status)}: {homebase_dir}")
    writable_status = "PASS" if homebase_dir.is_dir() and os.access(homebase_dir, os.W_OK) else "WARN"
    _print_check(
        writable_status,
        ".homebase writable",
        f"{_state_text(writable_status)}: {homebase_dir}",
    )

    if config_path.is_file():
        try:
            loaded = yaml.safe_load(config_path.read_text())
            valid = loaded is None or isinstance(loaded, dict)
        except (OSError, yaml.YAMLError):
            valid = False
        config_status = "PASS" if valid else "FAIL"
        _print_check(config_status, "config", f"{_state_text(config_status)}: {config_path}")
    else:
        _print_check("WARN", "config", f"needs change: optional; create {config_path} if you need global config")

    gitignore_ok = False
    if homebase_gitignore.is_file():
        try:
            lines = [ln.strip() for ln in homebase_gitignore.read_text().splitlines()]
            gitignore_ok = "cache.sqlite3" in lines
        except OSError:
            gitignore_ok = False
    _print_check(
        "PASS" if gitignore_ok else "WARN",
        ".homebase/.gitignore",
        f"{_state_text('PASS' if gitignore_ok else 'WARN')}: "
        + ("contains cache.sqlite3" if gitignore_ok else "add cache.sqlite3 rule"),
    )

    tmux_conf_path = Path.home() / ".tmux.conf"
    try:
        tmux_conf_text = tmux_conf_path.read_text() if tmux_conf_path.exists() else ""
    except OSError as exc:
        print(f"- tmux binding: failed reading {tmux_conf_path} ({exc})", file=sys.stderr)
        tmux_conf_text = ""

    active_tmux_bin = tmux_bin or "/opt/homebrew/bin/tmux"
    active_uv_bin = uv_bin or "/opt/homebrew/bin/uv"
    expected_binding = recommended_tmux_save_binding(target, active_uv_bin, active_tmux_bin)

    tmux_binding_ok = has_recommended_tmux_binding(tmux_conf_text, expected_binding)
    _print_check(
        "PASS" if tmux_binding_ok else "WARN",
        "tmux binding",
        f"{_state_text('PASS' if tmux_binding_ok else 'WARN')}: "
        + ("recommended binding present" if tmux_binding_ok else "recommended binding missing"),
    )
    existing_tmux_bindings = tmux_save_binding_lines(tmux_conf_text)
    if not tmux_binding_ok and existing_tmux_bindings:
        print("  tmux binding diff:")
        print(f"    current: {existing_tmux_bindings[0]}")
        print(f"    expect : {expected_binding}")

    active_shell = _current_shell_name()
    completion_shell = active_shell if active_shell in {"bash", "zsh", "fish"} else ""
    completion_target = _completion_target_for_shell(completion_shell) if completion_shell else None
    completion_status = "WARN"
    completion_detail = "unsupported shell for auto-check"
    expected_completion = ""
    completion_ok = False
    if completion_shell and completion_script_fn is not None and completion_target is not None:
        expected_completion = completion_script_fn(completion_shell)
        completion_ok = _completion_ok(completion_target, expected_completion)
        completion_status = "PASS" if completion_ok else "WARN"
        completion_detail = (
            f"{_state_text(completion_status)}: {completion_target}"
            if completion_ok
            else f"needs change: write completion to {completion_target}"
        )
    elif completion_shell and completion_target is not None:
        completion_status = "WARN"
        completion_detail = f"needs change: completion checker unavailable for {completion_shell}"
    _print_check(completion_status, "shell completion", completion_detail)

    print("")
    print("fix proposals:")

    if not homebase_dir.is_dir() and prompt_yes_no(f"create {homebase_dir}?", True):
        if dry_run:
            print(f"- would fix: create {homebase_dir}")
        else:
            homebase_dir.mkdir(parents=True, exist_ok=True)
            print(f"- fixed: created {homebase_dir}")

    if not dest_dir.is_dir() and prompt_yes_no(f"create {dest_dir}?", True):
        if dry_run:
            print(f"- would fix: create {dest_dir}")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)

    if (not dest.is_symlink()) or (dest.is_symlink() and dest.resolve() != target):
        if prompt_yes_no(f"ensure launcher symlink {dest} -> {target}?", True):
            if dry_run:
                print(f"- would fix: ensure {dest} -> {target}")
            else:
                if dest.exists() and not dest.is_symlink():
                    ts = datetime.now().strftime("%Y%m%d%H%M%S")
                    backup = dest.with_name(f"{dest.name}.bak-{ts}")
                    dest.rename(backup)
                    print(f"- moved existing file: {backup}")
                elif dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(target)
                print(f"- fixed: {dest} -> {target}")

    if not gitignore_ok and prompt_yes_no(f"ensure {homebase_gitignore} ignores cache.sqlite3?", True):
        if dry_run:
            print(f"- would fix: update {homebase_gitignore}")
        else:
            homebase_gitignore.parent.mkdir(parents=True, exist_ok=True)
            _write_homebase_gitignore(homebase_gitignore)
            print(f"- fixed: updated {homebase_gitignore}")

    if not tmux_binding_ok:
        target_display = compact_path_for_display(str(tmux_conf_path))
        print(f"- tmux config file: {target_display}")
        print("  expected binding:")
        for line in binding_display_lines(expected_binding):
            print(f"    {line}")
        if prompt_yes_no("apply recommended tmux binding?", True):
            if dry_run:
                print(f"- would fix: write tmux binding ({target_display})")
            else:
                try:
                    write_tmux_binding(tmux_conf_path, expected_binding)
                    print(f"- fixed: tmux binding written ({target_display})")
                    print("  run now: tmux source-file ~/.tmux.conf")
                except (OSError, ValueError) as exc:
                    print(f"- tmux binding write failed ({exc})", file=sys.stderr)

    if completion_shell and completion_target is not None and not completion_ok and expected_completion:
        if prompt_yes_no(
            f"install {completion_shell} completion at {completion_target}?",
            True,
        ):
            if dry_run:
                print(f"- would fix: write {completion_target}")
            else:
                try:
                    completion_target.parent.mkdir(parents=True, exist_ok=True)
                    completion_target.write_text(expected_completion)
                    print(f"- fixed: wrote {completion_target}")
                except OSError as exc:
                    print(f"- completion write failed ({exc})", file=sys.stderr)

    print("")
    print("final validation:")
    uv_bin = find_executable("uv", ("/opt/homebrew/bin/uv", "/usr/local/bin/uv"))
    git_bin = find_executable("git")
    tmux_bin = find_executable("tmux", tmux_bin_candidates)
    tmuxp_bin = find_executable("tmuxp")
    runtime_ok, _runtime_detail = _runtime_imports_ok()
    path_entries = os.environ.get("PATH", "").split(":")
    in_path = any(Path(p).expanduser().resolve() == dest_dir.resolve() for p in path_entries if p)
    homebase_exists = homebase_dir.is_dir()
    homebase_writable = homebase_exists and os.access(homebase_dir, os.W_OK)
    launcher_ok = dest.is_symlink() and dest.resolve() == target
    config_valid = True
    if config_path.is_file():
        try:
            loaded = yaml.safe_load(config_path.read_text())
            config_valid = loaded is None or isinstance(loaded, dict)
        except (OSError, yaml.YAMLError):
            config_valid = False
    gitignore_ok = False
    if homebase_gitignore.is_file():
        try:
            lines = [ln.strip() for ln in homebase_gitignore.read_text().splitlines()]
            gitignore_ok = "cache.sqlite3" in lines
        except OSError:
            gitignore_ok = False
    try:
        tmux_conf_text = tmux_conf_path.read_text() if tmux_conf_path.exists() else ""
    except OSError:
        tmux_conf_text = ""
    tmux_binding_ok = has_recommended_tmux_binding(tmux_conf_text, expected_binding)
    completion_ok_final = completion_ok
    if completion_shell and completion_target is not None and completion_script_fn is not None:
        try:
            completion_ok_final = _completion_ok(
                completion_target,
                completion_script_fn(completion_shell),
            )
        except (ValueError, OSError):
            completion_ok_final = False

    hard_fail = False
    fail_checks = [
        not bool(uv_bin),
        not bool(git_bin),
        not bool(tmux_bin),
        not runtime_ok,
        not homebase_exists,
        not homebase_writable,
        not launcher_ok,
        not config_valid,
    ]
    if any(fail_checks):
        hard_fail = True
    warn_checks = [
        not bool(tmuxp_bin),
        not in_path,
        not gitignore_ok,
        not tmux_binding_ok,
        not config_path.is_file(),
        completion_shell in {"bash", "zsh", "fish"} and not completion_ok_final,
    ]
    pass_count = 14 - sum(1 for x in fail_checks if x) - sum(1 for x in warn_checks if x)
    warn_count = sum(1 for x in warn_checks if x)
    fail_count = sum(1 for x in fail_checks if x)
    _print_check(
        "PASS" if not hard_fail else "FAIL",
        "setup",
        "ready" if not hard_fail else "incomplete; resolve FAIL checks",
    )
    print(f"- summary: PASS={pass_count} WARN={warn_count} FAIL={fail_count}")
    print("")
    print("next steps:")
    print(f"- optional config: create/edit {config_path}")
    print("- docs: README.md (Technical State Files + Kitchen Sink Config)")
    print("- run: b status")
    return 0 if not hard_fail else 1
