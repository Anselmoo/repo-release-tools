# repo-release-tools docs

`repo-release-tools` provides one release workflow across local CLI usage, CI,
pre-commit, and Copilot skill entrypoints.

## Start here

- [RRT CLI](rrt-cli.md) — branch helpers, version bumps, and config-driven targets
- [GitHub Action](github-action.md) — CI enforcement for branch, changelog, and commit policy
- [pre-commit](pre-commit.md) — local hooks for branch, changelog, and commit checks
- [Skill](skill.md) — Copilot CLI skill usage via `uvx`
- [Conventional branches](semantic-branches.md) — branch naming model for trunk-based publishing
- [Git magic](git-magic.md) — opinionated commit workflows and reusable Git safety checks

## What This Docs Set Covers

The docs are intentionally split so the landing page stays short:

- the CLI and config model live in `rrt-cli.md`
- branch policy and release naming live in `semantic-branches.md`
- workflow design and Git safety checks live in `git-magic.md`
- CI and local enforcement live in `github-action.md` and `pre-commit.md`
- zero-install guidance lives in `skill.md`

That keeps the homepage readable while still giving each workflow a complete
leaf page.
