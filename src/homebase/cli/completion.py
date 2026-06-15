from __future__ import annotations

from pathlib import Path

_TOP_LEVEL_COMMANDS = [
    "help",
    "ls",
    "json",
    "new",
    "n",
    "recent",
    "setup",
    "cache",
    "tags",
    "utils",
    "a",
    "cd",
    "open",
    "rm",
    "fix",
    "archive",
    "tmux",
    "integration",
    "benchmark",
    "test",
    "example",
    "completion",
    "shell-init",
]


def _active_project_names(base_dir: Path) -> list[str]:
    """Names of top-level directories under base that aren't archived,
    hidden, or reserved (``_archive``, ``_tags``, ``.homebase`` …).
    Used by ``b cd <tab>`` to offer only real projects."""
    try:
        entries = list(base_dir.iterdir())
    except OSError:
        return []
    names: list[str] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        names.append(entry.name)
    names.sort()
    return names


def _cd_candidates(
    words: list[str], cword: int, *, base_dir: Path,
) -> list[str]:
    """Project names offered by ``b cd <tab>``. Tokens that appear
    between ``cd`` and the token currently being completed are joined
    and treated as a filter expression (same syntax as ``b ls`` and
    the TUI QUERY input). Examples:

        b cd <tab>               → all active projects
        b cd '#infra' <tab>      → only projects tagged ``infra``
        b cd '#infra' my<tab>    → projects tagged ``infra`` whose name
                                    starts with ``my``

    When no prior tokens exist, we use a cheap filesystem listing (no
    cache I/O). With filter tokens, we read the SQLite cache so that
    tags/properties/etc. are available; a cold or unreadable cache
    falls back to the unfiltered filesystem listing rather than
    showing nothing."""
    prior = [str(t) for t in words[1 : max(1, cword - 1)] if str(t).strip()]
    filter_expr = " ".join(prior).strip()
    if not filter_expr:
        return _active_project_names(base_dir)

    try:
        from ..cache.api import cache_load_rows
        from ..config.prefs import load_saved_filter_queries
        from ..workspace.filter_compile import compile_filter_expr
    except ImportError:
        return _active_project_names(base_dir)

    try:
        active, _archived, _ts = cache_load_rows(base_dir)
    except (OSError, ValueError):
        return _active_project_names(base_dir)
    if not active:
        return _active_project_names(base_dir)

    # ``@name`` tokens resolve through the user's saved-filter prefs.
    # The completion subprocess starts with an empty NAMED_FILTERS
    # dict, so populate it before compiling — otherwise every named
    # token silently turns into "match nothing".
    try:
        load_saved_filter_queries(base_dir)
    except (OSError, ValueError):
        pass

    pred, _hint = compile_filter_expr(filter_expr)
    return sorted({str(row.name) for row in active if pred(row)})


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


def _dir_candidates(token: str, cwd: Path) -> list[str]:
    """Directory completions for a path token, returned with their
    full path prefix and a trailing slash so bash/zsh/fish render
    them as continued completions."""
    raw = Path(token) if token else Path("")
    if token.endswith("/"):
        parent_rel = raw
        prefix = ""
        head = token
    elif "/" in token:
        parent_rel = raw.parent
        prefix = raw.name
        head = token.rsplit("/", 1)[0] + "/"
    else:
        parent_rel = Path("")
        prefix = token
        head = ""
    parent = (cwd / parent_rel) if str(parent_rel) else cwd
    try:
        entries = list(parent.iterdir())
    except OSError:
        return []
    out: list[str] = []
    for entry in entries:
        if not entry.is_dir():
            continue
        if not entry.name.startswith(prefix):
            continue
        out.append(f"{head}{entry.name}/")
    return out


def completion_candidates(
    words: list[str],
    cword: int,
    *,
    base_dir: Path,
    cwd: Path | None = None,
) -> list[str]:
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
        candidates = _subcommand_candidates(
            cmd, tokens, idx, prev, base_dir=base_dir,
            cwd=cwd if cwd is not None else Path.cwd(),
            token=token,
        )
    out = [c for c in candidates if c.startswith(token)]
    return sorted(set(out))


_LS_FLAGS = [
    "-l", "--long", "--git", "--archived", "--created", "--active", "--wip",
    "--worktree-of", "--src", "--path", "--description", "--props",
]
_FIX_FLAGS = [
    "--all", "--yes", "--marker", "--no-marker", "--archive-entry",
    "--no-archive-entry",
]
_SIMPLE_SUB_CANDIDATES = {
    "ls": _LS_FLAGS,
    "json": ["--archived", "--archived-only"],
    "setup": ["--yes", "--no-tmux-binding"],
    "cache": ["warm"],
    "tags": ["sync-_tags", "ls", "--debug"],
    "utils": ["opt-in-nested-discovery"],
    "archive": ["mv", "ls", "undo", "restore", "--yes"],
    "completion": ["bash", "zsh", "fish"],
}
_BARE_VALUE_PREVS = frozenset(
    {
        "--filter", "--name", "--comment", "--output", "--pane-id",
        "--session-id", "--ignore-featureset",
    }
)


def _new_candidates(prev: str, base_dir: Path) -> list[str]:
    if prev == "--as":
        return _new_child_source_keys(base_dir)
    if prev == "--template":
        return _new_template_keys(base_dir)
    return [*_NEW_MODE_FLAGS, *_NEW_COMMON_FLAGS]


def _tmux_candidates(words: list[str], cword: int) -> list[str]:
    if cword == 2:
        return ["load", "save"]
    if len(words) >= 2 and words[1] == "save":
        return ["--output", "--stdout", "--debug", "--pane-id", "--session-id"]
    return []


def _integration_candidates(words: list[str], cword: int) -> list[str]:
    if cword == 2:
        return ["raycast"]
    if len(words) >= 2 and words[1] == "raycast":
        return ["actions", "run"]
    return []


def _benchmark_candidates(words: list[str], cword: int) -> list[str]:
    if cword == 2:
        return ["run", "results"]
    if len(words) >= 2 and words[1] == "run":
        return ["--comment", "--keep-basefolder"]
    if len(words) >= 2 and words[1] == "results":
        return ["--ignore-featureset"]
    return []


def _test_candidates(words: list[str], cword: int, prev: str) -> list[str]:
    if cword == 2:
        return ["regression", "--comment", "--keep-basefolder"]
    if len(words) >= 2 and words[1] == "regression":
        if prev == "--case":
            return _regression_case_names()
        return ["--list", "--case"]
    return ["--comment", "--keep-basefolder"]


def _example_candidates(
    words: list[str], cword: int, prev: str, *, cwd: Path, token: str
) -> list[str]:
    if prev == "--path":
        return _dir_candidates(token, cwd)
    if cword == 2:
        return ["generate"]
    if len(words) >= 2 and words[1] == "generate":
        return ["--path", "--count", "--seed"]
    return []


def _secondary_subcommand_candidates(
    cmd: str,
    words: list[str],
    cword: int,
    prev: str,
    *,
    cwd: Path,
    token: str,
) -> list[str]:
    if cmd == "tmux":
        return _tmux_candidates(words, cword)
    if cmd == "integration":
        return _integration_candidates(words, cword)
    if cmd == "benchmark":
        return _benchmark_candidates(words, cword)
    if cmd == "test":
        return _test_candidates(words, cword, prev)
    if cmd == "example":
        return _example_candidates(words, cword, prev, cwd=cwd, token=token)
    return []


def _subcommand_candidates(
    cmd: str,
    words: list[str],
    cword: int,
    prev: str,
    *,
    base_dir: Path,
    cwd: Path,
    token: str,
) -> list[str]:
    if prev == "--base-folder" or prev in _BARE_VALUE_PREVS:
        return []
    if cmd in {"new", "n"}:
        return _new_candidates(prev, base_dir)
    if cmd in _SIMPLE_SUB_CANDIDATES:
        return list(_SIMPLE_SUB_CANDIDATES[cmd])
    if cmd in {"cd", "open"}:
        return _cd_candidates(words, cword, base_dir=base_dir)
    if cmd == "rm":
        return [*_active_project_names(base_dir), "--force", "--force-outside-base"]
    if cmd == "fix":
        return [*_dir_candidates(token, cwd), *_FIX_FLAGS]
    return _secondary_subcommand_candidates(
        cmd,
        words,
        cword,
        prev,
        cwd=cwd,
        token=token,
    )


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
    # The trailing `--` separates `__complete`'s own positionals from
    # user-typed words. Without it, words that look like options
    # (e.g. `--as`, `--no-tmp`) are parsed at the parent level and
    # crash with "unrecognized arguments".
    return """# homebase completion for bash
_b_completion() {
  local cword="${COMP_CWORD}"
  local words=("${COMP_WORDS[@]:1}")
  COMPREPLY=( $(b __complete bash "$cword" -- "${words[@]}") )
}
complete -F _b_completion b
"""


def _zsh_completion_script() -> str:
    # See _bash_completion_script() for why `--` is required.
    return """#compdef b
_b_completion() {
  local -a words
  words=("${words[@]:2}")
  local cword=$((CURRENT-1))
  local -a out
  out=("${(@f)$(b __complete zsh "$cword" -- "${words[@]}")}")
  compadd -a out
}
compdef _b_completion b
"""


def _fish_completion_script() -> str:
    # `--` separates __complete's own positionals from the user's
    # words. Otherwise option-shaped words (`--as`, `--no-tmp`, ...)
    # get parsed at the parent level and `b` exits with
    # "unrecognized arguments".
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
    b __complete fish $cword -- $args
end

complete -c b -f -a '(__b_complete)'
"""
