# repo-release-tools docs

`repo-release-tools` provides one release workflow across local CLI usage, CI,
pre-commit, and Copilot skill entrypoints.

## Start here

- [RRT CLI](rrt-cli.md) — branch helpers, version bumps, and config-driven targets
- [GitHub Action](github-action.md) — CI enforcement for branch, changelog, and commit policy
- [pre-commit](pre-commit.md) — local hooks for branch, changelog, and commit checks
- [Skill](skill.md) — Copilot CLI skill usage via `uvx`
- [Semantic branches](semantic-branches.md) — branch naming model for trunk-based development

## Minimal interface

If you publish `docs/` with GitHub Pages later, this page can stay the landing
page:

- one-line product summary
- five entry links
- no deep prose on the front page
- detailed explanations pushed into leaf documents

That keeps the interface small and product-oriented.

## GitHub Pages

This docs tree is designed to publish directly from GitHub Pages with the
repository Pages workflow. Keep the homepage short and move detailed guidance
into the linked leaf pages.
