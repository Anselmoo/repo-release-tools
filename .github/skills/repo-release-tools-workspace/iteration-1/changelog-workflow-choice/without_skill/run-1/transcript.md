## Eval Prompt
Help me choose between incremental and squash changelog workflows for repo-release-tools. I want to understand which hooks stay active in each mode, how GitHub Action changelog-strategy auto behaves, and what minimal config I should add.

## Steps
1. Reviewed `README.md` for the workflow comparison table and minimal config guidance.
2. Reviewed `docs/pre-commit.md` for which hooks are recommended in `incremental` vs `squash` workflows.
3. Reviewed `docs/github-action.md` and `action.yml` for `changelog-strategy: auto` behavior.
4. Verified implementation details in `src/repo_release_tools/hooks.py`, `src/repo_release_tools/commands/bump.py`, and `src/repo_release_tools/config.py`.
5. Checked `pyproject.toml` and confirmed this repo already has `[tool.rrt]` and `version_targets`, but no explicit `changelog_workflow` yet.
6. Wrote `outputs/answer.md`, `outputs/user_notes.md`, and this transcript. No repository source files outside the run directory were modified.

## Final Output Summary
Created a user-facing Markdown answer that explains:
- when to choose `incremental` vs `squash`
- which hooks remain active in each workflow
- how GitHub Action `changelog-strategy: auto` resolves
- the minimal config needed for this repository

Also added a short caveats file covering the main `auto`/`unreleased` nuance and the current default behavior.
