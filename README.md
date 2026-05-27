# homebase

> AI usage note: This project is heavily AI-assisted with strict review discipline.
> Changes are developed through detailed prompts, small iterative patches, strong
> test coverage, and manual verification. The engineering bar is practical and
> conservative: reproducible tests, lint-clean code, explicit error handling, and
> non-destructive git workflows.

Personal project workspace TUI + CLI. The `b` (or `homebase`) command
opens a textual UI over a directory of projects, with archive,
filtering, tagging, and tmux integration.

## Quickstart

```sh
uv tool install git+https://github.com/xeor/homebase.git
b setup
b
```

Update to latest from GitHub:

```sh
uv tool upgrade homebase
# if needed, force reinstall from git source:
uv tool install --reinstall git+https://github.com/xeor/homebase.git
b setup
```

Base folder defaults to `~/base`. Override with `--base-folder` or
`BASE_FOLDER=/path uv run b ...`.

`b setup` validates environment wiring and can install/fix shell completion
for the active shell (`bash`, `zsh`, `fish`).

`homebase` and `b` are interchangeable; both resolve to
`homebase.cli:entrypoint`.

## Common Commands

```sh
uv run b                   # interactive TUI
uv run b ls                # fast cache-backed project list (names only)
uv run b ls -l             # long format (modified / size / tags)
uv run b ls tag:work       # filter (same syntax as the TUI's QUERY input)
uv run b ls --git          # re-probe git + show BRANCH column (slower)
uv run b ls --archived     # list archived projects
uv run b help              # full subcommand list
uv run b new               # new-project wizard
uv run b archive mv .      # archive current dir
uv run b benchmark run # synthetic perf bench
uv run b example generate --path /tmp/demo  # throwaway demo base
uv run b c tmp         # quick-create from template key
uv run b c tmp --debug # preview actions, no changes
uv run b completion bash > ~/.local/share/bash-completion/completions/b
uv run b completion zsh > ~/.zfunc/_b
uv run b completion fish > ~/.config/fish/completions/b.fish
```

Shell completion:

- `b completion bash|zsh|fish` prints a completion script for that shell.
- Dynamic completion offers source keys (`b new --as <tab>`),
  templates (`b new --template <tab>`), and project names
  (`b cd <tab>`, `b rm <tab>`).

## Demo / example workspace

```sh
b example generate --path /tmp/demo
BASE_FOLDER=/tmp/demo b
```

Generates a throwaway base folder full of random projects, git
repos, worktrees, and an archive — plus a showcase `.homebase/config.yaml`.
For screenshots, trying things out, demos. See [`docs/example.md`](docs/example.md).

## Worktrees

`b` treats every `git worktree` as a first-class project sibling under
`<base>/<parent>-<sanitised-branch>/`. The `worktree:` block in
`.base.yaml` keeps the pointers self-describing, and `git worktree
repair` is called on rename/archive so the parent's admin entry stays
in sync. Filters `:repo=<name>` (umbrella) and `:worktree-of=<name>`
(strict) narrow to a family. If pointers drift (manual moves, packed
archives, relocated base), run `b fix-worktrees [--apply]`.

```sh
uv run b new featx --as worktree --from foo
uv run b new featx                # inside <base>/foo/repo, auto-detects
uv run b deworktree foo-featx     # detach into a standalone clone
uv run b fix-worktrees --apply    # audit + repair pointers
```

The worktree shortcut for `b new <input>` only fires when `<input>` is
a **bare token** (no `/`, no `\`). A trailing slash or any path-shaped
input is the user's explicit "this is a folder" hint and always routes
to a local move instead — see [`b new` input shapes](#b-new-input-shapes).

## Shell integration (parent-shell cd handoff)

Commands like `b cd <name>`, `b new --cd`, and the post-action cleanup
of `b rm` / `b archive` need to land you in a directory once they're
done. A bare binary can't change the parent shell's cwd, so by default
`b` execs a fresh sub-shell at the target — which means when you
eventually `exit` that sub-shell you're back in the (possibly deleted)
original cwd.

Install the small wrapper function once and the binary will instead
hand the cwd off to your existing shell via a temp file (env var
`HOMEBASE_CD_FILE`). Same pattern as `zoxide`, `direnv`, `pyenv`.

Easiest path — let `b setup` detect what's missing and offer to
install both completion and the wrapper interactively:

```sh
b setup
```

Manual install (if you'd rather):

```sh
# bash
b shell-init bash > ~/.local/share/homebase/shell-init.bash
echo '[ -f "$HOME/.local/share/homebase/shell-init.bash" ] && . "$HOME/.local/share/homebase/shell-init.bash"  # homebase shell integration' >> ~/.bashrc

# zsh
b shell-init zsh > ~/.local/share/homebase/shell-init.zsh
echo '[ -f "$HOME/.local/share/homebase/shell-init.zsh" ] && . "$HOME/.local/share/homebase/shell-init.zsh"  # homebase shell integration' >> ~/.zshrc

# fish (conf.d/ is auto-sourced — no rc edit needed)
b shell-init fish > ~/.config/fish/conf.d/b.fish
```

Open a **new** shell after install. After that, `b cd foo`,
`b new myproj`, the post-action cleanup of `b rm` / `b archive`, etc.
all `cd` your existing shell — no sub-shell, no
`getcwd: cannot access parent directories` errors on the next prompt.

If you don't install the wrapper, the previous sub-shell behavior is
still the fallback, plus a one-line stderr hint pointing at
`b shell-init`. Set `HOMEBASE_QUIET_FALLBACK=1` to silence that hint
when you've made an informed decision to keep the sub-shell.

> If you installed `b` via `uv tool install ...`, remember to
> `uv tool install --reinstall --editable .` (or
> `uv tool upgrade homebase`) after pulling new code — the installed
> binary is a snapshot. A stale binary won't know about
> `HOMEBASE_CD_FILE` and will keep opening sub-shells even with the
> wrapper installed.

## Validation

```sh
uv run pytest                # full suite
uv run pytest -x --tb=short  # stop at first failure
uv run pytest tests/test_archive_io.py  # one file
```

### Lint

```sh
uv run ruff check src/homebase/ tests/
uv run ruff check --fix src/homebase/ tests/  # auto-fix imports/order
```

### Local Dev

```sh
uv sync                       # install with dev extras
uv run python -m homebase status
```

## Runtime Files

Homebase runtime state/config files live in `<base>/.homebase/`.

- `config.yaml`: global runtime config (`properties`, `create_templates`, filters, hotkeys, open-mode, etc.)
- `cache.sqlite3`: primary sqlite cache for rows/opened timestamps/reconcile state
- `benchmark.yaml`: benchmark run history written by `b benchmark run`
- `test.yaml`: synthetic test-suite history written by `b test`
- `regression-test.yaml`: regression run reports written by `b test regression`
- `nested-discovery.yaml`: optional nested-marker discovery report written by `b utils opt-in-nested-discovery`

Setup creates the directory:

```sh
b setup
```

## Architecture (Brief)

Source layout (one subpackage per domain):

```
src/homebase/
├── cli/         # argparse parser, dispatcher, main()
├── core/        # constants, models, primitives (no internal deps)
├── config/      # global config, prefs, property defs, open_mode
├── archive/     # tar pack/unpack, move, restore
├── cache/       # sqlite cache, reconcile usage, queue
├── metadata/    # .base.yml read/write, property detection, tag index
├── tmux/        # tmux core / commands / flow
├── filter/      # filter engine + tag index
├── workspace/   # discovery, project rows, benchmark, regression
├── commands/    # CLI command handlers
└── ui/          # textual TUI (app, runtime, widgets, context, …)
    ├── screens/   modal screens (actions, basic, choices, filter_*,
    │              multi, panes, restore, new_project, tag_plan)
    ├── table/     project table + nav + view state
    ├── side/      side panel content + tabs + settings
    ├── sync/      cache refresh, reconcile, git refresh, pane probe
    ├── actions/   action items, bulk ops, tag/wip/project actions
    └── query/     filter input edit + key input + selection events
```

Layering rule (imports go inward only): `core/` ⇽ nothing; `config/`
⇽ `core/`; `cache/`, `metadata/`, `archive/`, `tmux/`, `filter/` ⇽
`core/`, `config/`; `workspace/`, `commands/` ⇽ those; `ui/` ⇽
everything; `cli/` ⇽ everything.

See `AGENTS.md` for the full architecture rules and conventions.

## Configuration

Global config file: `<base>/.homebase/config.yaml`

References:

- `docs/actions.md`
- `docs/hooks.md`
- `docs/kitchen-sink-config.md`
- `docs/example.md`

Most used top-level sections:

- `archive`
- `filters`
- `properties`
- `cache_profile`
- `create_templates`
- `open_mode`
- `notes`
- `reconcile`
- `table_behavior`
- `table_columns`
- `actions`
- `hotbar`
- `keys`
- `new_project`
- `state`

### Property Config

`properties` is a token-keyed map in `.homebase/config.yaml`.

Each property entry must define exactly one detector:

- `file-exists`
- `dir-exists`
- `path-exists`
- `queries`

Example:

```yaml
properties:
  GIT:
    label: Git
    key: git
    dir-exists: [.git]

  ACT:
    label: active tmux pane
    key: act
    cache_ttl_s: 3
    queries:
      - type: tmux_open_panes

  EDT:
    label: editor active for project
    key: edt
    cache_ttl_s: 8
    queries:
      - type: tmux_editor_commands
        commands: [code, code-insiders, codium, cursor, zed, nvim, vim]
      - type: sqlite_recent_paths
        db_path: "~/Library/Application Support/VSCodium/User/globalStorage/state.vscdb"
        table: ItemTable
        value_column: value
        where_like: "%file://%"
```

Query types currently supported:

- `tmux_open_panes`
- `tmux_editor_commands`
- `sqlite_recent_paths`

### Full Config Example

`<base>/.homebase/config.yaml` example with all supported top-level areas:

For a maintained kitchen-sink version you can copy from:

- `docs/kitchen-sink-config.md`

```yaml
# Archive behavior
archive:
  timezone: Europe/Oslo

# Saved/named filters used by query bar
filters:
  saved:
    - "#wip"
    - "tags=0"
  named:
    hot: "#cli OR #api"
    fresh: ":last=@-7d"

# Dynamic property detectors
properties:
  GIT:
    label: Git repo
    key: git
    color: "#87afff"
    dir-exists: [.git]

  ACT:
    label: active pane
    key: act
    color: "#ffb86c"
    cache_ttl_s: 3
    queries:
      - type: tmux_open_panes

  EDT:
    label: editor active
    key: edt
    color: "#7fd1ae"
    queries:
      - type: tmux_editor_commands
        commands: [code, codium, cursor, zed, nvim, vim]

  RECENT:
    label: recent in sqlite
    key: recent
    color: "#c7a8ff"
    queries:
      - type: sqlite_recent_paths
        db_path: "~/Library/Application Support/VSCodium/User/globalStorage/state.vscdb"
        table: ItemTable
        value_column: value
        where_like: "%file://%"

# Per-view cache profile presets + property binding
cache_profile:
  all:
    pri-2:
      update_interval_s: 10
      update_batch_size: 16
      update_priority: 40
      cache_mode: ttl
      cache_ttl_s: 30
  archive:
    pri-2:
      cache_ttl_s: 120

# `b new` defaults + custom child sources. See
# docs/kitchen-sink-config.md for the full option reference.
new:
  sources:
    tmp:
      parent: empty
      timestamp: true       # YYYY-MM-DD_ prefix
      tmp: true             # .tmp suffix
      ts-name: true         # auto-name as YYYYMMDD-HHMMSS
      tags: [scratch]
    py:
      parent: empty
      template: python
      cd: true
      tags: [python]

# Open behavior profile
open_mode:
  profile: shell_cd

# Notes integration
notes:
  path_template: "{{ PROJECT_PATH }}/NOTES.md"
  open_command: "${EDITOR:-vi} {{ NOTE_PATH_Q }}"
  create_command: "mkdir -p \"$(dirname {{ NOTE_PATH_Q }})\" && touch {{ NOTE_PATH_Q }} && ${EDITOR:-vi} {{ NOTE_PATH_Q }}"

# Reconcile tuning
reconcile:
  active:
    update_batch_size: 12
  archive:
    update_batch_size: 8

# UI table behavior/settings
table_behavior:
  pin_wip_top: false
  side_width_pct: 33

table_columns:
  active:
    - id: name
      width: 28
      enabled: true
    - id: branch
      width: 14
      enabled: true
  archive:
    - id: name
      width: 28
      enabled: true
    - id: archived
      width: 14
      enabled: true

# WIP symbol map override
wip_open_symbol_map:
  "©": 1
  "™": 2

# Additional suffixes and file-view excludes
suffixes: [tmp, fork]
file_view_exclude_patterns:
  - "*.min.js"
  - "node_modules/**"

# Actions + bindings
actions:
  open_item_in_codium:
    kind: shell
    scope: target
    multi: joined
    command: 'codium {{ paths_q }}'

  add_log_to_note:
    kind: note
    scope: target
    op: add_log

hotbar:
  - open_selected
  - add_log_to_note

keys:
  'alt+v': open_item_in_codium

# New-project defaults used by wizard
new_project:
  name_options: []
  template: null
  post_commands: []
  tags: []
  after_create: open

# UI state persistence (optional)
state:
  view: active
  sort: last
  side_main: selected
  side_selected: overview
  side_info: events
  side_settings: table
```

## Advanced: `b new` and custom sources

Single entry point for creating projects. CLI:

```sh
b new                                # interactive TUI
b new <input>                        # bare-name / path / URL — auto-detected
b new <input> <name>                 # explicit folder name override
b new --as <child-key>               # use a configured child source
b new --empty | --local | --git | --download | --downloaded
                                     # force a built-in source
```

Built-in sources (auto-detected from `<input>`):

| Source       | Detected from                       | Action                                              |
|--------------|-------------------------------------|-----------------------------------------------------|
| `empty`      | bare token (`myproj`)               | mkdir + marker                                      |
| `local`      | path (`./x`, `/abs`, `~/x`, `x/`)   | move existing dir into base                         |
| `worktree`   | bare token while cwd is inside `<base>/<proj>/repo/` (proj has `.git`) | `git worktree add` of that repo |
| `git`        | URL with `.git` / SSH / forge adapter says clone | `git clone` into `<name>/repo/`           |
| `download`   | URL the forge adapter recognises as a file (github blob, gitlab/gitea raw, …) | fetch file into `<name>/`        |
| `downloaded` | only via `--downloaded` flag        | interactively pick a recent file from `~/Downloads` |

### `b new` input shapes

The trailing slash matters. From inside `<base>/foo/repo/`:

```sh
b new featx       # bare token  -> worktree of foo on branch `featx`
                  #                creates <base>/foo-featx/repo/
b new featx/      # trailing /   -> local move of ./featx into a new
                  #                sibling project <base>/featx/
b new ./featx     # path-shaped  -> same as featx/
b new /abs/dir    # absolute path -> local move of /abs/dir into <base>/dir/
b new https://… # URL         -> git clone or download (see table)
```

Same rules apply when cwd is anywhere else — minus the worktree row,
which only fires when the enclosing base project has a `.git` repo.
The path-shaped routes are unchanged; only the bare-token shape gets
the worktree shortcut.

Override the auto-detect with `--as <source>` or one of the explicit
flags (`--empty`, `--local`, `--git`, `--download`, `--downloaded`,
`--as worktree --from <parent>`).

Full option reference (all of these can be set per-source under
`new.sources.<key>` in the config **and** overridden on the CLI as
`--<key>` / `--no-<key>`): see
[`docs/kitchen-sink-config.md`](docs/kitchen-sink-config.md) — the
`new:` block there documents every option inline with examples for
ts-name, alpha-name, archive, post-commands, child inheritance, etc.

Short option list (one line each):

- `tmp` / `--tmp` — append `.tmp` to folder name.
- `timestamp` / `--timestamp` — prepend `YYYY-MM-DD_` to folder name.
- `ts-name` / `--ts-name` — when no name is given, use `YYYYMMDD-HHMMSS`.
- `alpha-name` / `--alpha-name` — when no name is given, pick the next
  free `a`, `b`, …, `aa`, `ab`, …
- `open` / `--open` (alias: `cd` / `--cd`) — spawn a shell in the new
  project on success. Default: true. Pass `--no-open` to stay where
  you were.
- `confirm` / `--confirm` — print plan + ask before applying.
- `archive` / `--archive` — land under `_archive/<year>/<date>_<name>/`.
- `tags` / `--tag <t>` (repeatable) — initial tags written to `.base.yaml`.
- `template` / `--template <key>` — copier template under
  `<base>/.copier/<key>/`.
- `post` / `--post <cmd>` (repeatable) — shell commands run in the
  project dir after creation.

Examples:

```sh
b new myproj                                  # empty project
b new myproj --tmp --timestamp                # 2026-05-14_myproj.tmp
b new --as tmp                                # ts-name based scratch
b new --as alpha                              # next free a/b/c/…
b new https://github.com/x/repo               # git clone
b new https://github.com/x/repo/blob/main/README.md
                                              # downloads the raw file
b new ./existing                              # move into base
b new existing/                               # same; trailing / = folder
b new featx     # inside <base>/foo/repo     # worktree of foo @ featx
b new --downloaded                            # picker over ~/Downloads
b new myproj --archive                        # lands under _archive/…
```

## Advanced: Actions and Bindings

Actions are configured in `<base>/.homebase/config.yaml` with three sections:

- `actions`: definitions (built-in overrides and custom actions)
- `hotbar`: ordered target actions for Enter-dispatch cycling (`ctrl+@`)
- `keys`: fixed key bindings to action ids

Minimal example:

```yaml
actions:
  archive: { label: Archive now }

  open_item_in_codium:
    kind: shell
    scope: target
    multi: joined
    command: 'codium {{ paths_q }}'

  open_in_daisydisk:
    kind: shell
    scope: target
    multi: per_row
    command: 'open -n -a DaisyDisk {{ path_q }}'

  open_base_in_editor:
    kind: shell
    scope: workspace
    command: '$EDITOR {{ base_dir_q }}'

  pick_markdown:
    kind: filepicker
    scope: target
    list: 'find {{ path_q }} -type f -name "*.md"'
    command: 'codium {{ selection_q }}'

  add_log_to_note:
    kind: note
    scope: target
    op: add_log

hotbar:
  - open_selected
  - notes_create
  - { action: open_item_in_codium, label: codium }

keys:
  'f5': open_item_in_codium
  'ctrl+alt+r': refresh_cache
  'ctrl+l': tab.info.events
```

Behavior notes:

- `scope`: `target` | `workspace` | `tab`
- `multi`: `joined` (one run with list vars like `paths_q`) or `per_row` (one run per selected row with `path_q`)
- `_q` variables are shell-quoted and should be used in `command`/`list`
- `kind: filepicker` collects candidates per selected row, merges, then executes once on selected candidate
- only `scope: target` actions are allowed in `hotbar`
- `per_row` execution order is current selection order (top to bottom)

Technical reference (full schema, variable matrix, dispatch rules):

- `docs/actions.md`
- `docs/kitchen-sink-config.md`

## Packaging

Build sdist + wheel:

```sh
uv build                       # writes dist/homebase-*.tar.gz + .whl
ls dist/
```

Install from a built wheel:

```sh
uv pip install dist/homebase-0.1.0-py3-none-any.whl
b help
```

Install from GitHub:

```sh
uv pip install git+https://github.com/xeor/homebase.git
```

Bump `version` in `pyproject.toml` before each release.

## Repository Layout

```
pyproject.toml      # build config (hatchling), deps, scripts, ruff, pytest
src/homebase/       # package
tests/              # pytest scaffold
docs/               # technical reference docs
TODO.md             # active follow-ups + feature backlog
README.md           # this file
AGENTS.md           # AI agent rules + project conventions
```
