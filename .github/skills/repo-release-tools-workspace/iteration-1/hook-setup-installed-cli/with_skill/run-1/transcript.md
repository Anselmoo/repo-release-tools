## Eval Prompt

rrt is installed locally. Show me how to set up repo-release-tools hooks for both pre-commit and lefthook so branch names, commit subjects, and changelog updates are enforced. Mention when rrt-hooks needs to be on PATH.

## Steps

1. Read the installed-CLI skill at `.github/skills/repo-release-tools/SKILL.md`.
2. Cross-checked hook guidance in `docs/pre-commit.md`, `.pre-commit-hooks.yaml`, `lefthook.yml`, and `README.md`.
3. Selected the incremental workflow examples that enforce branch naming, commit subjects, and changelog updates.
4. Included the changelog-hook caveat that `rrt-update-unreleased` and `rrt-changelog` are alternatives, not a pair to enable together.
5. Explicitly noted that `rrt-hooks` must be on `PATH` for lefthook because lefthook invokes the binary directly.
6. Wrote the final Markdown answer to `outputs/answer.md`.

## Final Output Summary

Saved a user-facing setup guide with valid pre-commit and lefthook examples, install commands, the PATH requirement for `rrt-hooks` under lefthook, and the note not to enable both changelog hooks simultaneously.
