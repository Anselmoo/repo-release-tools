# Skills

This repository includes two bundled agent skills:

- `/.github/skills/repo-release-tools-uvx/SKILL.md`
- `/.github/skills/repo-release-tools/SKILL.md`

## Which one to use

### `repo-release-tools-uvx`

Use the existing `uvx` skill when you want zero-install guidance such as:

- `uvx repo-release-tools branch new ...`
- `uvx repo-release-tools bump ...`
- ephemeral CI or one-off release automation

### `repo-release-tools`

Use the installed-CLI skill when `rrt` is already available on the machine and
you want guidance for:

- branch naming with `rrt branch ...`
- release bumps with `rrt bump ...`
- hook setup with `rrt-hooks ...`
- `rrt doctor` / `rrt config`
- GitHub Action and changelog workflow configuration

## Installing the bundled CLI skill

The `repo-release-tools` package includes a bundled installer command:

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

The installer refuses to overwrite an existing installed skill unless you pass
`--force`. Use `--dry-run` to preview the copy targets first.

## Skill eval fixtures

Keep the canonical skill eval prompts in:

- `/evals/evals.json`

That file is part of the repo and should be tracked so future skill iterations
can reuse the same prompts and expectations.

Do **not** treat ad-hoc execution transcripts such as a root-level
`transcript.md` as repository documentation. Those are local review artifacts
from a specific eval run and should stay out of git.
