# homebase

Personal project workspace TUI + CLI. The `b` (or `homebase`) command
opens a textual UI over a directory of projects, with archive,
filtering, tagging, and tmux integration.

## Run

```sh
uv run b               # interactive TUI
uv run b status        # plain status table
uv run b help          # full subcommand list
uv run b new           # new-project wizard
uv run b archive mv .  # archive current dir
uv run b benchmark run # synthetic perf bench
uv run b c tmp         # quick-create from template key
uv run b c tmp --debug # preview actions, no changes
```

Base folder defaults to `~/base`. Override with `--base-folder` or
`BASE_FOLDER=/path uv run b ...`.

`homebase` and `b` are interchangeable; both resolve to
`homebase.cli:entrypoint`.

## Test

```sh
uv run pytest                # full suite
uv run pytest -x --tb=short  # stop at first failure
uv run pytest tests/test_archive_io.py  # one file
```

## Lint

```sh
uv run ruff check src/homebase/ tests/
uv run ruff check --fix src/homebase/ tests/  # auto-fix imports/order
```

## Develop

```sh
uv sync                       # install with dev extras
uv run python -m homebase status
```

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

## Property Config

`properties` is a token-keyed map in `.base-conf.yaml`.

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

## Quick Create Templates

`b c <key>` reads `create_templates` from `.base-conf.yaml`.

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
```

Supported `options`:

- `prefix-datetime` -> prepend date prefix to folder name
- `suffix-tmp` -> append `.tmp` suffix
- `changedir` -> open shell in created directory (interactive only)
- `prompt-name` -> ask for folder name when `--name` is omitted
- `generate-ts-name` -> generate folder name from timestamp when `--name` is omitted
- `generate-next-alpha-name` -> pick next free alpha name (`a`, `b`, ... `z`, `aa`, ...)

Notes:

- `--name` overrides `prompt-name` / `generate-ts-name` / `generate-next-alpha-name`
- `--debug` prints resolution steps and exits without creating files
- `template` uses `.copier/<template>/` under base dir
- if template dir contains `copier.yml`/`copier.yaml`, `copier copy --trust` is used
- otherwise files are copied directly from the template directory

## Custom Action Hotkeys

Custom actions are configured in `~/<base>/.base-conf.yaml` (same file
as other global settings).

Minimal shape:

```yaml
custom_actions:
  - id: vscode
    label: Open in VS Code
    scope: item
    command: code "{{ full_path }}"

  - id: cursor
    label: Open in Cursor
    scope: item
    command: cursor "{{ full_path }}"

  - id: zed
    label: Open in Zed
    scope: item
    command: zed "{{ full_path }}"

  - id: reveal_finder
    label: Reveal in Finder
    scope: item
    command: open -R "{{ full_path }}"

  - id: open_iterm
    label: Open iTerm here
    scope: item
    command: open -a iTerm "{{ full_path }}"

custom_hotkeys:
  - id: hk_vscode
    hotkey: f5
    target: action:custom:vscode
  - id: hk_cursor
    hotkey: f6
    target: action:custom:cursor
  - id: hk_reveal
    hotkey: alt+f6
    target: action:custom:reveal_finder
  - id: hk_archive
    hotkey: ctrl+f7
    target: action:archive
  - id: hk_tab_notes
    hotkey: ctrl+f8
    target: tab:selected/notes
```

- `id`: unique action id
- `label`: shown in action picker
- `scope`: `item` | `selection` | `global`
- `command`: shell command template; context vars from custom actions
  still apply (`{{ full_path }}`, `{{ rel_path }}`, ...)
- `custom_hotkeys[].hotkey`: key name from Textual key syntax (for
  example `f1`..`f12`, `ctrl+f5`, `alt+v`, `ç`, `†` on macOS option keys)
- `custom_hotkeys[].target`: command-palette id to trigger. Supported:
  `action:<action_id>` and `tab:<top_key>` / `tab:<top_key>/<child_key>`.
  Example action ids: `action:archive`, `action:refresh_cache`,
  `action:custom:<custom_action_id>`.

Notes:

- Hotkeys are matched case-insensitively.
- Startup fails if two `custom_hotkeys` entries use the same hotkey.
- Startup fails if a custom hotkey collides with an existing app
  hotkey.
- Hotkeys trigger when the main projects table has focus and no modal
  is open.

## Package

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

Install from a git checkout:

```sh
uv pip install git+https://github.com/<user>/homebase.git
```

Bump `version` in `pyproject.toml` before each release.

## Project files

```
pyproject.toml      # build config (hatchling), deps, scripts, ruff, pytest
src/homebase/       # package
tests/              # pytest scaffold
TODO.md             # active follow-ups + feature backlog
README.md           # this file
AGENTS.md           # AI agent rules + project conventions
```
