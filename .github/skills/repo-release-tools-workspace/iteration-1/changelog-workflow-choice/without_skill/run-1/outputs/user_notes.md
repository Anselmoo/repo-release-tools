# Caveats

- In `incremental`, GitHub Action `changelog-strategy: "auto"` resolves to `per-commit`, not `unreleased`.
- In this repository today, omitting `changelog_workflow` still behaves like `incremental`, because that is the default.
- For local incremental workflows, `rrt-update-unreleased` and `rrt-changelog` are alternatives; you usually want one or the other, not both.
