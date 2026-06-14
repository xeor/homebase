# Raycast Integration — Agent Instructions

Parent `../AGENTS.md` and repo-root rules apply.

Standalone Raycast extension for Homebase project search/opening. It
shells out to `b`; it is not a dependency of the main `homebase`
package.

## Commands

```
mise run setup
mise run dev
mise run lint
mise run build
mise run check
mise run ray -- help
mise tasks ls
```

Underlying commands:

```
npm install
npm run dev
npm run lint
npm run build
npm run check
```

Keep dependencies in this directory's `package.json` and
`package-lock.json`.
