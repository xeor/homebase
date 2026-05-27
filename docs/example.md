# `b example generate`

Throwaway base folder full of random projects. For screenshots,
trying out homebase without touching `~/base`, or seeding a fresh
demo per release.

## Quick start

```sh
b example generate --path /tmp/demo
BASE_FOLDER=/tmp/demo b
```

## Flags

| Flag           | Default  | Notes                                  |
|----------------|----------|----------------------------------------|
| `--path <dir>` | required | Target directory; must not exist.      |
| `--count N`    | 30       | Number of active projects.             |
| `--seed N`     | random   | Deterministic RNG seed.                |

## What you get

- `N` active projects with random names, weighted tags, lorem-ipsum descriptions on ~20%
- ~60% are git repos in `<name>/repo/` with a few dated commits
- 2-3 of those git repos have a sibling worktree (`<name>-<branch>/`)
- Up to 5 projects flagged `wip`
- 10 archive entries spread over the last decade; 2 packed as `.tgz`
- Date spread reaches back ~15 years (driven via `os.utime` + `GIT_*_DATE`)
- A showcase `.homebase/config.yaml` exercising `properties`, `tag_rules`
  (regex + multi-parent + `group_only`), saved/named filters, hotbar
  styling, date-gradient columns, bundled hooks
- Pre-warmed sqlite cache, so `b ls` returns rows on first run

## Try it

```sh
BASE_FOLDER=/tmp/demo b                       # TUI
BASE_FOLDER=/tmp/demo b ls -l
BASE_FOLDER=/tmp/demo b ls --archived
BASE_FOLDER=/tmp/demo b tags ls
BASE_FOLDER=/tmp/demo b ls "#wip"
BASE_FOLDER=/tmp/demo b ls "##programming"
BASE_FOLDER=/tmp/demo b ls "##compiled"
```

## Reproducible runs

```sh
b example generate --path /tmp/demo --count 50 --seed 42
```

Same `--count` + `--seed` produces the same project names, tag
mix, wip set, and worktree pairing (commit timestamps and dir
mtimes are still "now-relative").

## Cleanup

```sh
rm -rf /tmp/demo
```
