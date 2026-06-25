# Changelog

Entry format: `## <version> (<commit>) - <date>`. `<commit>` is the
short hash the release was cut from. Every entry must have all three
— enforced by `scripts/deploy.py`, never hand-write a heading without
them.

## 0.5.0 (c824259) - 2026-06-24

First version with a version number — homebase had no semver/release
tracking before this.

- Added version tracking: `b version`, info > global panel, `mise run deploy` release flow.
- `b setup` now shows a version diff + changelog excerpt when the installed version changed since the last run.
