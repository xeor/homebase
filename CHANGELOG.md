# Changelog

## 0.5.2 - 2026-06-25

- Improved version resolution logic


## 0.5.1 - 2026-06-25

- Worktree support: detect, create (`b new --as worktree`, TUI "New worktree"), rename/archive/delete/deworktree via worktree repair, `b fix-worktrees` audit+repair, pack/unpack preflight warnings, `:repo`/`:worktree-of` filter keys, GIT column `↪parent` marker, sticky worktree-health banner (ctrl+x to dismiss), side panel repo path + worktree lineage
- Hooks: full hook feature (config, runtime, snapshots)
- `b new`: reworked new-project dialog - source-at-top, worktree-aware plan + validation, prefill/layout fixes, confirm-destructive guard, `.git` prompt on local import
- `b fix`: `--repo-dir` autodetector, `repo_dir` in `.base.yaml`, `fix --all` fixes, better archive auto-date parsing
- Config: reworked config system (phases 1-8)
- Cache: persist `worktree_of` + `repo_dir` per row, race fix, cache rework
- Filter: unified query input
- `b example generate` for demo base folders; shared `workspace/seed/` primitives
- Hotbar functionality and per-context hotbar styles
- Range-color on datetime columns
- Notes: markdown log append functionality
- tmux: fast window switch, `b` works outside tmux, better tmux errors
- Discovery: one bad project no longer aborts the whole scan
- Action picker: hide actions that don't fit the current target
- Moved browser tab sync (bts) and raycast into `integrations/`

## 0.5.0 - 2026-06-24

First version with a version number. Homebase had no semver/release tracking before this.

- Added version tracking: `b version`, info > global panel, `mise run deploy` release flow.
- `b setup` now shows a version diff + changelog excerpt when the installed version changed since the last run.
