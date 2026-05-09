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
uv run b               # interactive TUI
uv run b status        # plain status table
uv run b help          # full subcommand list
uv run b new           # new-project wizard
uv run b archive mv .  # archive current dir
uv run b benchmark run # synthetic perf bench
uv run b c tmp         # quick-create from template key
uv run b c tmp --debug # preview actions, no changes
uv run b completion bash > ~/.local/share/bash-completion/completions/b
uv run b completion zsh > ~/.zfunc/_b
uv run b completion fish > ~/.config/fish/completions/b.fish
```

Shell completion:

- `b completion bash|zsh|fish` prints a completion script for that shell.
- Dynamic completion includes quick-create keys from `create_templates`
  for `b c <key>`.

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
    fresh: "last=@-7d"

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

# Quick-create templates used by `b c <key>`
create_templates:
  - key: tmp
    name: Quick tmp project
    options: [prefix-datetime, suffix-tmp, generate-ts-name]
    tags: [scratch]
  - key: py
    name: Python starter
    template: python
    options: [prompt-name, changedir]
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

## Advanced: Quick Create Templates

`b c <key>` reads `create_templates` from `.homebase/config.yaml`.

CLI shape:

```sh
b c <key> [--name <folder-name>] [--debug]
```

```yaml
create_templates:
  - key: tmp
    name: Quick tmp project
    options: [prefix-datetime, suffix-tmp, changedir, generate-ts-name]
    tags: [scratch, quick]

  - key: py
    name: Python starter
    template: python
    options: [changedir, prompt-name]
    tags: [python]

  - key: area51
    name: Area51 copier starter
    template: area51
    options: [prompt-name, changedir]
    tags: [experimental]
```

Fields:

- `key`: command key used by `b c <key>`
- `name`: optional human label (for config readability)
- `template`: optional copier/template id under `.copier/<template>`
- `options`: behavior toggles (see below)
- `tags`: optional list of initial tags written to `.base.yaml`

Supported `options`:

- `prefix-datetime` -> prepend date prefix to folder name
- `suffix-tmp` -> append `.tmp` suffix
- `changedir` -> open shell in created directory (interactive only)
- `prompt-name` -> ask for folder name when `--name` is omitted
- `generate-ts-name` -> generate folder name from timestamp when `--name` is omitted
- `generate-next-alpha-name` -> pick next free alpha name (`a`, `b`, ... `z`, `aa`, ...)

Notes:

- name resolution priority:
  1) `--name`
  2) `prompt-name`
  3) `generate-ts-name`
  4) `generate-next-alpha-name`
  5) fallback to template `key`
- `--debug` prints resolution steps and exits without creating files
- `template` uses `.copier/<template>/` under base dir
- if template dir contains `copier.yml`/`copier.yaml`, `copier copy --trust` is used
- otherwise files are copied directly from the template directory

Examples:

```sh
# quick scratch project with generated timestamp name
b c tmp

# explicit name (overrides prompt/generate options)
b c py --name cli-tools

# copier template (interactive prompts are shown by copier)
b c area51

# preview without creating files
b c area51 --name area51-demo --debug
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
