# Skills

This repository bundles two agent skills:

- `/.github/skills/repo-release-tools-uvx/SKILL.md` — zero-install guidance
- `/.github/skills/repo-release-tools/SKILL.md` — guidance for an installed `rrt`

If you need the exact CLI syntax for branch, Git, or skill commands, use the
[RRT CLI reference](rrt-cli.md) first.

## Which skill to use

### `repo-release-tools-uvx`

Use this when `repo-release-tools` is not installed and you want quick
`uvx`-based usage examples for branches, bumps, or one-off release automation.

### `repo-release-tools`

Use this when `rrt` is already available and you want help with:

- `rrt branch ...` naming and branch repair
- `rrt bump ...` release versioning
- `rrt git ...` workflow helpers
- `rrt doctor` / `rrt config`
- `rrt skill install ...`
- hook and CI workflow guidance that points back to the main docs

## Installing the bundled CLI skill

Install into one or more agent skill locations with:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target copilot-global --dry-run
rrt skill install --target codex-global --force
```

Supported targets:

| Target | Directory |
|---|---|
| `copilot-local` | `.copilot/skills` |
| `claude-local` | `.claude/skills` |
| `codex-local` | `.codex/skills` |
| `copilot-global` | `~/.copilot/skills` |
| `claude-global` | `~/.claude/skills` |
| `codex-global` | `~/.codex/skills` |

The installer refuses to overwrite an existing skill unless you pass `--force`.
Use `--dry-run` to preview the destination paths first.

## Related docs

- [RRT CLI](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)
- [Git magic](git.md)

## Skill eval fixtures

Keep the canonical skill eval prompts in `/evals/evals.json`.

Structured workspace artifacts under
`.github/skills/repo-release-tools-workspace/` may be committed as evidence of an
evaluation run. Do **not** commit ad-hoc execution transcripts
(`transcript.md`).
