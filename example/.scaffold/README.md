# scaffold scripts

How this example base was built. Re-run to recreate after wiping.

```sh
cd example
bash .scaffold/_setup.sh
bash .scaffold/_setup_archive.sh
bash .scaffold/_setup_tags.sh
```

The worktree pair (`terraform-aws-baseline` + `-feat-eks`) is wired by
hand — see this directory's git history if you need to redo it.
