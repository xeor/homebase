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
