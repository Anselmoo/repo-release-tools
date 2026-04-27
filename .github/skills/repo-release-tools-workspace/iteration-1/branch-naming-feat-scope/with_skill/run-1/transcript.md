## Eval Prompt

I already have rrt installed. I need to start work on adding parser caching for the CLI. Suggest the correct branch name, show the exact rrt command to create it, and explain how to rename it later if I realize the scope should be config instead of cli.

## Steps

1. Read the installed-CLI skill at `.github/skills/repo-release-tools/SKILL.md`.
2. Checked branch naming guidance and `rrt branch rename` behavior in `docs/semantic-branches.md`, `docs/rrt-cli.md`, and `src/repo_release_tools/commands/branch.py`.
3. Determined that `--scope cli` produces `feat/cli-add-parser-caching`.
4. Noted the rename caveat: `rrt branch rename --scope config` alone would prepend `config-` to the existing slug, so a full rebuild with the description is required.
5. Wrote the final answer to `outputs/answer.md` and the caveat to `outputs/user_notes.md`.

## Final Output Summary

Provided the recommended branch name, the exact `rrt branch new` command, the correct `rrt branch rename` command for changing scope from `cli` to `config`, and the remote-update follow-up if the branch has already been pushed.
