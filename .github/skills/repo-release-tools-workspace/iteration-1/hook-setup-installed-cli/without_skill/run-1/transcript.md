## Eval Prompt

rrt is installed locally. Show me how to set up repo-release-tools hooks for both pre-commit and lefthook so branch names, commit subjects, and changelog updates are enforced. Mention when rrt-hooks needs to be on PATH.

## Steps

1. Reviewed repository docs and config, especially `docs/pre-commit.md`, `docs/semantic-branches.md`, `docs/rrt-cli.md`, `README.md`, `.pre-commit-hooks.yaml`, and `lefthook.yml`.
2. Used the documented **incremental** workflow because it enforces branch naming, Conventional Commit subjects, and changelog updates.
3. Prepared a user-facing Markdown answer covering both `pre-commit` and `lefthook` setup.
4. Explicitly noted that `rrt-hooks` must be on `PATH` for `lefthook`, while the standard published `pre-commit` setup does not require that separately.
5. Wrote the final answer to `outputs/answer.md` and kept all file changes inside the run directory.

## Final Output Summary

Created:
- `outputs/answer.md` — final user-facing setup instructions
- `transcript.md` — concise eval transcript

No `outputs/user_notes.md` was needed because the answer could be given directly from repository documentation.
