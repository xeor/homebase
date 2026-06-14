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

## Commands

- `Projects`: fuzzy-searches `b ls`
- `Enter`: `b cd {selection}`
- Secondary action: `echo {selection}`

## Preferences

- `b Path`: full path to `b`
- `Command Timeout`: milliseconds before a `b` command is killed
