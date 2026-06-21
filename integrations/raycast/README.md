# Homebase Raycast

Raycast extension for searching Homebase projects through `b`.

## Prerequisites

- Raycast installed and running.
- `mise` available on `PATH`.
- Homebase installed so `b` works from a normal shell.
- The extension preference `b Path` must point to a working `b`
  executable. Default: `/Users/xeor/.local/bin/b`.

Check Homebase first:

```sh
b ls
/Users/xeor/.local/bin/b ls
```

## First setup

```sh
cd integrations/raycast
mise trust
mise run setup
```

`mise run setup` runs `npm install` in this directory. Dependencies
stay local to this integration.

## Development loop

```sh
cd integrations/raycast
mise run dev
```

This runs `ray develop` from `@raycast/api`.

What it does:

- imports the extension into Raycast as a development extension
- watches source files and rebuilds on change
- prints extension logs/build errors in the terminal
- makes the command available in Raycast as `Projects`

Open Raycast and run `Projects`. If `b` is not found, open the command
preferences and set `b Path` to the full path from:

```sh
which b
```

## Validation

```sh
mise run lint      # ray lint
mise run build     # ray build -e dist
mise run check     # lint + build
mise run ray -- help
```

`ray lint` validates `package.json`, extension icons, ESLint, and
Prettier. Raycast manifest/schema validation may require network access
to `www.raycast.com`.

## Homebase contract

- Enter uses `b open <selection>`, so Homebase owns tmux/window behavior.
- The project list and Cmd-K actions come from
  `b integration raycast projects`.
- The Raycast search box uses native Raycast filtering over the loaded
  project list. It does not run Homebase filter syntax per keystroke.
- Project list ordering is controlled by `<base>/.homebase/config.yaml`:
  `raycast.sort: name` (default) or `raycast.sort: opened`.
- Optional `raycast.secondary_info` templates are shown as the Raycast
  subtitle and indexed as search keywords. They are rendered from cached
  row data.
- `b integration raycast actions` remains available for single-purpose
  action inspection/debugging.
- Cmd-K action execution uses `b integration raycast run <action> <selection>`.

```yaml
raycast:
  sort: opened
  secondary_info:
    - "{{ opened_ago }}"
    - "{{ tags_space }}"
  secondary_separator: " • "
```

Enable secondary Raycast actions in Homebase action config:

```yaml
actions:
  notes_create:
    raycast: true
  notes_open:
    raycast: true

  open_item_in_codium:
    kind: shell
    scope: target
    multi: joined
    command: 'codium {{ paths_q }}'
    raycast:
      enabled: true
      title: Open in Codium
```

Supported Raycast actions are built-ins `open_selected`, `notes_create`,
`notes_open`, plus custom `shell` actions with `target` or `workspace`
scope.

## Commands

- `Projects`: loads Homebase projects once and filters locally in Raycast
- `Enter`: `b open {selection}`
- `Cmd-K`: enabled Homebase Raycast actions

## Preferences

- `b Path`: full path to `b`
- `Command Timeout`: milliseconds before a `b` command is killed
