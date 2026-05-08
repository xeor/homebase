# AI Agent Instructions — `homebase`

Single-user personal workspace TUI/CLI. No external audience. All
agents working in this tree must follow these rules.

---

## 1. Communication

- English only, regardless of prompt language.
- Direct and technical; the user is an experienced engineer.
- Do not over-explain.
- Ask before guessing on ambiguous tasks.

## 2. Documentation style

- One reader. Skip filler, marketing, and verbose paragraphs.
- Prefer code over prose:
  ```
  # bad:  "to run the tests, execute the following command in your terminal"
  # good: `uv run pytest`
  ```
- Don't document what's self-evident from the code.
- No README/AGENTS-style docs added without explicit request.
- No emojis.

## 3. General behavior

- Use the latest stable version of tools/languages/frameworks unless
  told otherwise.
- Edit existing files; create new ones only when strictly necessary.
- Don't add backwards-compatibility shims, deprecation comments, or
  "removed in vX" notes. Just change the code.
- Don't add comments that describe past state ("previously…",
  "formerly…", "Phase D2 will…"). They rot the moment the past is no
  longer relevant.

---

## 4. Project layout (must follow)

```
src/homebase/
├── cli/         # argparse parser, dispatch, main()
├── core/        # constants, models, primitives (depends on nothing)
├── config/      # store, prefs, property_defs, open_mode, workspace
├── archive/     # io, ops, service
├── cache/       # store, api, queue (sqlite)
├── metadata/    # store, utils, api (.base.yml), property
├── tmux/        # core, commands, flow
├── filter/      # engine, tag_index
├── notes/       # markdown note-edit primitives (log_md)
├── workspace/   # discovery, projects, project_info, rows,
│                # benchmark, benchmark_report, regression
├── commands/    # basic, workspace, interactive_flow, archive
└── ui/          # textual TUI
    ├── app.py        # BApp class + run_textual_ui
    ├── runtime.py    # thin re-export of run_textual_ui
    ├── context.py    # UIContext dataclass
    ├── widgets.py
    ├── runtime_feedback.py
    ├── screens/      # modal screens
    ├── table/        # project table + nav + view state
    ├── side/         # side panel content + tabs + settings
    ├── sync/         # cache refresh, reconcile, git, pane probe
    ├── actions/      # action items, bulk ops, tag/wip/project
    └── query/        # filter input edit, key input, selection
```

Top-level package contains only `__init__.py` and `__main__.py`.
Everything else lives in a domain subpackage.

## 5. Layering (must follow)

```
core/        ← imports nothing else from the package
config/      ← core/
cache/       ← core/, config/
metadata/    ← core/, config/
archive/     ← core/, config/
tmux/        ← core/, config/
filter/      ← core/, config/
notes/       ← core/
workspace/   ← core/, config/, cache/, metadata/, archive/, filter/
commands/    ← workspace/, archive/, cache/, metadata/, tmux/, core/, config/
ui/          ← everything except cli/
cli/         ← everything
```

Imports must always go inward. If `core/` ever imports from anywhere
else in the package, that's a layering violation — fix the design,
not the import.

## 6. Where things go

- **Constants** with meaning shared by more than one module →
  `core/constants.py`. This includes:
  - All `COLOR_*_HEX` style values, all `UI_TICK_*_S` periodic
    intervals, schema versions, default file names, action keys, side
    tab keys.
  - Don't reinvent inline. Search `core/constants.py` first.
- **Exception aliases** that name a recurring catch tuple →
  `core/utils.py` (e.g. `WIDGET_API_ERRORS`).
- **Pure data transforms** (no I/O, no globals) → `*_utils.py` /
  `*_engine.py` (e.g. `metadata/utils.py`, `filter/engine.py`).
- **I/O wrappers** (read/write yaml, sqlite) → `*_store.py` (e.g.
  `metadata/store.py`, `cache/store.py`).
- **Public APIs** for a domain → `<domain>/api.py` (e.g.
  `metadata/api.py`).
- **CLI command handlers** → `commands/<topic>.py`.
- **TUI helper functions** that operate on a BApp instance → the
  matching `ui/<sub>/<topic>.py` file. BApp methods should be thin
  delegations to these.

## 7. Code style

- Readability over cleverness.
- Follow the surrounding file's naming and structure.
- Functions stay small and focused. A module reaching ~500 lines
  should be examined for a topical split. Big files are OK only when
  the contents are domain-coherent (e.g. `workspace/benchmark.py`).
- No `from X import *`. Imports are explicit.
- No re-export shim modules at the top level.

## 8. Error handling

- Never use bare `except:` or `except Exception:` unless the user
  asks for a specific boundary explicitly.
- Catch only the concrete exception types expected at that call site.
- Keep `try` blocks narrow.
- Don't silently swallow failures. Log/propagate with technical
  context.
- For UI failures, surface them via `_show_runtime_error` /
  `_log` so the user sees what broke.
- Fail fast on unexpected states. Don't mask programming errors.
- Recurring catch tuples: alias them in `core/utils.py` and import the
  alias.

## 9. Tests

- One test module per source module: `tests/test_<topic>.py`.
- Tests run via `uv run pytest`. Must stay green at every commit.
- Pure-data helpers in `*_utils.py` / `*_engine.py` should always
  have unit tests.
- For every bug fix, add or update regression tests during the same
  change. Prefer coverage that exercises the full affected path, not
  only the narrow helper.
- Don't mock the filesystem or sqlite — use `tmp_path`. The benchmark
  / regression suites already exercise the real I/O paths.
- Add a layering check (see TODO) when touching the import graph.

## 10. Lint / build

- `uv run ruff check src/homebase/ tests/` must be clean.
- `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` must remain
  empty. If ruff complains, fix the code, not the config.
- `uv build` must produce a wheel + sdist.

## 11. Shell / environment

- Primary shell: nushell. Scripts must work in bash and zsh
  (POSIX `sh` where possible).
- direnv is used for per-directory env (`.envrc`).
- tmuxp is used for tmux session/window management.

## 12. Git

- Never commit unless asked. Never push unless asked. Never
  force-push to `main`/`master`.
- Follow existing commit-message style.

## 13. Security

- Never expose or log secrets, tokens, API keys, passwords.
- Don't create or modify `.env` files without explicit instruction.
- Avoid destructive commands (`rm -rf`, `DROP TABLE`, …) without
  confirmation.

## 14. File and directory conventions

- This repo is part of a larger workspace. Subdirectories may have
  their own `AGENTS.md` with more specific rules — those take
  precedence over this file.
- Don't modify files outside the current scope without permission.
- Respect `.gitignore` patterns.
- Never commit secrets, credentials, or `.env` files.
