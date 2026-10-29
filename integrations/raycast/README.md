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

- The project list is read from `<base>/.homebase/runtime/raycast.json`,
  which `b daemon` keeps current (rebuilt when the cache or config
  changes, at least once a minute). No `b` process runs when Raycast
  opens. Without a running daemon (file older than 3 minutes) the list
  shows at once and `b integration raycast snapshot` refreshes it.
- Enter with `Open With: herdr space` (default): goes to the herdr space
  that already has the project open, else creates a space named after
  the project in its folder. Then the herdr terminal gets focus (`Focus
  Command`, default Hammerspoon `pair.focusTerminal()`, falling back to
  activating `Terminal App`), and `b integration raycast opened` records
  the open for `raycast.sort: opened`. Cmd-Enter opens a new space even
  when one exists. Without herdr, or with `Open With: b open`, Enter runs
  `b open <selection>` and Homebase owns tmux/window behavior.
- herdr is driven through its CLI (`herdr pane list`, `tab focus`,
  `workspace create`): its socket stalls ~100 ms for Node clients.
- Status is shown as small colored icons, not text: agent icon in the
  most urgent agent's color (blocked red, working yellow, done green,
  count when more than one), blue for general status (current space dot,
  terminal icon with the pane count). Tooltips have the details.
- Sections, herdr state refreshed every 2 s while open:
  - `Agents`: one row per coding agent pane, titled by its project,
    blocked/working first. Enter focuses its tab.
  - `Open`: every herdr space in order, with the project it holds (named
    like the space, else the one with most panes there): its subtitle,
    tags and Cmd-K actions. Enter focuses the space.
  - `Projects`: the new-space items and all projects. Under `All`,
    projects already listed in `Open` are left out.
- The search bar dropdown (⌘P, remembered) picks the section: `All`,
  `Agents`, `Open` or `Projects`. `⌥1`-`⌥4` pick one, `⌥←`/`⌥→` step
  through them, plain `←`/`→` too while the search box is empty. The search text is kept when switching;
  words and `#tag` filter every section (agents carry their project's
  tags).
- Code: `src/components/HomebaseList.tsx` is the list; a command is
  `<HomebaseList />` or `<HomebaseList scope="agents" />` (fixed, no
  dropdown). Preferences are extension-wide, shared by all commands.
- Two top items open a new herdr space in the base folder and focus the
  terminal: `Find Space with b` runs `New Space Command`
  (`b --open-mode shell_cd`, same as Cmd-N in herdr), `New Project with b`
  runs `New Project Command` (`b new`, b's new-project popup, then cd into
  the new project).
- Cmd-K actions come from the same snapshot; they run through
  `b integration raycast run <action> <selection>`.
- The search box filters locally (no `b` per keystroke), with a subset of
  b's QUERY syntax: `#tag` (exact), `#ta*` (glob), `-#tag` (exclude);
  other words must all match the name, subtitle or tags (name matches
  rank first). While typing `#…` the list narrows by prefix and a Tags
  section suggests completions; Enter on one completes it.
- Project list ordering is controlled by `<base>/.homebase/config.yaml`:
  `raycast.sort: name` (default) or `raycast.sort: opened`.
- Optional `raycast.secondary_info` templates are shown as the Raycast
  subtitle and indexed as search keywords. They are rendered from cached
  row data.
- `b integration raycast projects` and `actions` remain available for
  inspection/debugging.

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

- `Projects`: Homebase projects from the daemon snapshot, filtered locally
  (`#tag`, `-#tag`, words)
- `Enter`: go to / open the project's herdr space (or `b open`)
- `Cmd-Enter`: new herdr space even if the project is open
- `Cmd-K`: enabled Homebase Raycast actions

## Preferences

- `b Path`: full path to `b`
- `Base Folder`: Homebase base folder (default `~/base`)
- `Open With`: `herdr space` or `b open`
- `New Space Command`: typed into the space `Find Space with b` creates
- `New Project Command`: typed into the space `New Project with b` creates
- `Focus Command`: brings the herdr terminal to the front; printing
  `false` or failing falls back to activating `Terminal App`
- `Terminal App`: bundle id of the terminal running herdr
- `Command Timeout`: milliseconds before a `b` command is killed
