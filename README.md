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
uv run b completion bash > ~/.local/share/bash-completion/completions/b
uv run b completion zsh > ~/.zfunc/_b
uv run b completion fish > ~/.config/fish/completions/b.fish
```

Base folder defaults to `~/base`. Override with `--base-folder` or
`BASE_FOLDER=/path uv run b ...`.

`homebase` and `b` are interchangeable; both resolve to
`homebase.cli:entrypoint`.

Shell completion:

- `b completion bash|zsh|fish` prints a completion script for that shell.
- Dynamic completion includes quick-create keys from `create_templates`
  for `b c <key>`.

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

## Custom Action Hotkeys

Custom actions are configured in `~/<base>/.base-conf.yaml` (same file
as other global settings).

Minimal shape:

```yaml
custom_actions:
  - id: vscode
    label: Open in VS Code
    scope: target
    command: code {{ full_path }}

  - id: cursor
    label: Open in Cursor
    scope: target
    command: cursor {{ full_path }}

  - id: zed
    label: Open in Zed
    scope: target
    command: zed {{ full_path }}

  - id: reveal_finder
    label: Reveal in Finder
    scope: target
    command: open -R {{ full_path }}

  - id: open_in_daisydisk
    label: Open in DaisyDisk
    scope: target
    command: open -a DaisyDisk {{ full_path }}
    loop_on_multi: false

  - id: open_iterm
    label: Open iTerm here
    scope: target
    command: open -a iTerm {{ full_path }}

  - id: drawio_pick
    label: Pick drawio file
    scope: target
    list_command: find "{{ full_path }}" -name "*.drawio"
    run_command: drawio {{ selection_q }}

  - id: pick_markdown
    label: Pick markdown file
    scope: target
    list_command: find "{{ full_path }}" -type f -name "*.md"
    run_command: codium {{ selection_q }}

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
- `scope`: `target` | `global`
- `command`: shell command template; context vars from custom actions
  still apply (`{{ full_path }}`, `{{ rel_path }}`, ...)
- `loop_on_multi`: optional (`true`/`false`, default `false`).
  - `false`: one command invocation; `{{ full_path }}` is auto-expanded to
    one or many double-quoted paths (`"/p1"` or `"/p1" "/p2" ...`).
  - `true`: run once per target row (loop behavior).
- `list_command` + `run_command`: optional pair for list-actions.
  `list_command` emits candidates (one per line), user picks one in a fuzzy list,
  then `run_command` executes with `{{ selection }}` / `{{ selection_q }}`.
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
- list-actions run per target row when multiple targets are selected
  (results are merged); with one focused row they run once.
- For non-loop target commands, `b` handles quoting for `{{ full_path }}`;
  do not add extra quotes around `{{ full_path }}` in command templates.

List-action setup and usage:

1. Add a custom action with `list_command` and `run_command` in `.base-conf.yaml`.
2. Reload config (`Settings > Global config > Reload global config`) or restart `b`.
3. Open actions with `ctrl+a` or command palette with `ctrl+p`.
4. Pick your list-action (marked with `(list)`).
5. Type to fuzzy-filter candidates, press `enter` to execute selected item.

Example behavior:

- Focus a project `my-app`
- Run `Pick markdown file`
- App runs `find "<project-path>" -type f -name "*.md"`
- You choose a file from the list
- App executes `codium <selected-file>`

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
