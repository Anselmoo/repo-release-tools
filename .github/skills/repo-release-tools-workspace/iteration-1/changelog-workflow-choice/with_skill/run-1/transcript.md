## Eval Prompt

Help me choose between incremental and squash changelog workflows for repo-release-tools. I want to understand which hooks stay active in each mode, how GitHub Action changelog-strategy auto behaves, and what minimal config I should add.

## Steps

1. Read the installed skill file at `.github/skills/repo-release-tools/SKILL.md`.
2. Read repository docs and source relevant to changelog workflow behavior:
   - `docs/pre-commit.md`
   - `docs/github-action.md`
   - `action.yml`
   - `src/repo_release_tools/hooks.py`
3. Checked current repo configuration in `pyproject.toml` and current local hook setup in `lefthook.yml`.
4. Determined:
   - `incremental` keeps changelog enforcement active
   - `squash` disables changelog-writing/check hooks
   - GitHub Action `changelog-strategy: auto` resolves to `per-commit` for `incremental` and `release-only` for `squash`
   - this repo currently defaults to `incremental` because `changelog_workflow` is not explicitly set
5. Wrote the final user-facing answer to `outputs/answer.md`.

## Final Output Summary

Created:

- `outputs/answer.md` — final recommendation and workflow comparison
- `transcript.md` — concise eval transcript

Did not create `outputs/user_notes.md` because no unresolved uncertainties remained.
