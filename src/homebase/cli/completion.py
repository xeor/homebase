from __future__ import annotations

from pathlib import Path

_TOP_LEVEL_COMMANDS = [
    "help",
    "status",
    "new",
    "n",
    "recent",
    "setup",
    "cache",
    "tags",
    "utils",
    "a",
    "rm",
    "fix",
    "archive",
    "tmux",
    "benchmark",
    "test",
    "completion",
]


def _new_child_source_keys(base_dir: Path) -> list[str]:
    from ..workspace.new.config_loader import NewConfigError, load_new_sources
    from ..workspace.new.registry import builtin_keys

    try:
        cfg = load_new_sources(base_dir)
    except NewConfigError:
        return []
    builtins = set(builtin_keys())
    return sorted({key for key in cfg.keys() if key not in builtins})


def _new_template_keys(base_dir: Path) -> list[str]:
    from ..workspace.projects import discover_copier_templates

    return discover_copier_templates(base_dir)


_NEW_MODE_FLAGS = ("--empty", "--local", "--git", "--download", "--downloaded")
_NEW_COMMON_FLAGS = (
    "--archive",
    "--tag",
    "--template",
    "--tmp",
    "--no-tmp",
    "--timestamp",
    "--no-timestamp",
    "--open",
    "--no-open",
    "--cd",
    "--no-cd",
    "--confirm",
    "--no-confirm",
    "--ts-name",
    "--alpha-name",
    "--ask-name",
    "--ask-source",
    "--post",
    "--yes",
    "--dry-run",
    "--multi",
    "--as",
)


def _regression_case_names() -> list[str]:
    from ..workspace.regression import _regression_cases

    return sorted({str(name).strip() for name, _fn in _regression_cases() if str(name).strip()})


def _named_filter_keys(base_dir: Path) -> list[str]:
    from ..config.prefs import load_saved_filter_queries

    named, _saved = load_saved_filter_queries(base_dir)
    return sorted({str(key).strip() for key in named if str(key).strip()})


def _normalize_completion_input(words: list[str], cword: int) -> tuple[list[str], int]:
    tokens = [str(w) for w in words]
    idx = int(cword)
    if tokens and tokens[0] in {"b", "homebase"}:
        tokens = tokens[1:]
        idx -= 1
    if idx < 1:
        idx = 1
    if idx > len(tokens):
        tokens = [*tokens, ""]
    return tokens, idx


def completion_candidates(words: list[str], cword: int, *, base_dir: Path) -> list[str]:
    tokens, idx = _normalize_completion_input(words, cword)
    token = ""
    if 0 <= idx - 1 < len(tokens):
        token = str(tokens[idx - 1])
    prev = ""
    if 0 <= idx - 2 < len(tokens):
        prev = str(tokens[idx - 2])

    if idx <= 1:
        candidates = [
            *_TOP_LEVEL_COMMANDS,
            "--base-folder",
            "--filter",
            "--help",
        ]
    elif prev == "--filter":
        candidates = _named_filter_keys(base_dir)
    else:
        cmd = str(tokens[0]) if tokens else ""
        candidates = _subcommand_candidates(cmd, tokens, idx, prev, base_dir=base_dir)
    out = [c for c in candidates if c.startswith(token)]
    return sorted(set(out))


def _subcommand_candidates(
    cmd: str,
    words: list[str],
    cword: int,
    prev: str,
    *,
    base_dir: Path,
) -> list[str]:
    if prev in {"--base-folder"}:
        return []
    if prev in {"--filter", "--name", "--comment", "--output", "--pane-id", "--session-id", "--ignore-featureset"}:
        return []
    if cmd in {"new", "n"}:
        if prev == "--as":
            return _new_child_source_keys(base_dir)
        if prev == "--template":
            return _new_template_keys(base_dir)
        return [*_NEW_MODE_FLAGS, *_NEW_COMMON_FLAGS]
    if cmd == "setup":
        return ["--yes", "--no-tmux-binding"]
    if cmd == "cache":
        return ["warm"]
    if cmd == "tags":
        return ["sync-_tags", "--debug"]
    if cmd == "utils":
        return ["opt-in-nested-discovery"]
    if cmd == "archive":
        return ["mv", "ls", "undo", "restore"]
    if cmd == "tmux":
        if cword == 2:
            return ["load", "save"]
        if len(words) >= 2 and words[1] == "save":
            return ["--output", "--stdout", "--debug", "--pane-id", "--session-id"]
        return []
    if cmd == "benchmark":
        if cword == 2:
            return ["run", "results"]
        if len(words) >= 2 and words[1] == "run":
            return ["--comment", "--keep-basefolder"]
        if len(words) >= 2 and words[1] == "results":
            return ["--ignore-featureset"]
        return []
    if cmd == "test":
        if cword == 2:
            return ["regression", "--comment", "--keep-basefolder"]
        if len(words) >= 2 and words[1] == "regression":
            if prev == "--case":
                return _regression_case_names()
            return ["--list", "--case"]
        return ["--comment", "--keep-basefolder"]
    if cmd == "completion":
        return ["bash", "zsh", "fish"]
    return []


def completion_script(shell: str) -> str:
    value = str(shell).strip().lower()
    if value == "bash":
        return _bash_completion_script()
    if value == "zsh":
        return _zsh_completion_script()
    if value == "fish":
        return _fish_completion_script()
    raise ValueError(f"unsupported shell: {shell}")


def _bash_completion_script() -> str:
    return """# homebase completion for bash
_b_completion() {
  local cword="${COMP_CWORD}"
  local words=("${COMP_WORDS[@]:1}")
  COMPREPLY=( $(b __complete bash "$cword" "${words[@]}") )
}
complete -F _b_completion b
"""


def _zsh_completion_script() -> str:
    return """#compdef b
_b_completion() {
  local -a words
  words=("${words[@]:2}")
  local cword=$((CURRENT-1))
  local -a out
  out=("${(@f)$(b __complete zsh "$cword" "${words[@]}")}")
  compadd -a out
}
compdef _b_completion b
"""


def _fish_completion_script() -> str:
    return """# homebase completion for fish
function __b_complete
    set -l tokens (commandline -opc)
    set -l args
    set -l i 2
    while test $i -le (count $tokens)
        set args $args $tokens[$i]
        set i (math $i + 1)
    end
    set -l cword (math (count $args) + 1)
    b __complete fish $cword $args
end

complete -c b -f -a '(__b_complete)'
"""
