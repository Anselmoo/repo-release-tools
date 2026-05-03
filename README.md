# repo-release-tools

`repo-release-tools` keeps release policy boring in the best possible way.

Use it from **GitHub Marketplace** when you want CI to validate branch names,
commit subjects, and changelog policy. Install it from **PyPI** when you want a
local CLI, hook integration, version bumps, and release-branch automation.

- GitHub Marketplace action: <https://github.com/marketplace/actions/repo-release-tools-policy-checks>
- PyPI package: <https://pypi.org/project/repo-release-tools/>

## Choose your entry point

### Use the GitHub Action for CI policy checks

Choose the action if you want pull requests and pushes to fail fast when a repo
drifts from your release policy.

- validates branch names such as `feat/add-parser`
- validates Conventional Commit subjects
- validates changelog policy in CI
- optionally checks that the working tree stays clean
- can run `rrt doctor` as a pre-release health gate

```yaml
- uses: actions/checkout@v6
  with:
    fetch-depth: 0

- uses: Anselmoo/repo-release-tools@v1.1.0
  with:
    check-branch-name: "true"
    check-commit-subject: "true"
    check-changelog: "true"
```

See the full action guide:
<https://github.com/Anselmoo/repo-release-tools/blob/main/docs/action.md>

### Use the Python package for local workflow automation

Choose the package if you want the developer-side tools: branch helpers,
version bumps, config inspection, pre-commit hooks, and release automation.

```bash
pip install repo-release-tools
rrt init
rrt branch new feat "add parser"
rrt git commit "add parser"
rrt git doctor
rrt bump patch
```

Or run the CLI without installing it permanently:

```bash
uvx repo-release-tools branch new feat "add parser"
```

If `rrt` is already installed and you want the bundled agent skill for Copilot,
Claude, or Codex, install it with:

```bash
rrt skill install --target copilot-local
rrt skill install --target claude-local --target codex-local
rrt skill install --target codex-global --dry-run
```

For basic versioning, `bump` and `ci-version` can run without `[tool.rrt]` by
auto-detecting root-level `pyproject.toml`, `package.json`, and `Cargo.toml`.
If multiple version files are found, they are updated together. Explicit config
is for the nice extras: grouped releases, changelog paths, release branches,
lock commands, generated files, and custom patterns.

## Changelog workflows

The same project can be used in two release styles. Pick the one that matches
how your repository actually lands changes.

| Workflow | Best for | Hook behavior | Action `changelog-strategy: auto` | `rrt bump` default |
|---|---|---|---|---|
| `incremental` *(default)* | teams that maintain changelog entries during development | `rrt-update-unreleased` and `rrt-changelog` stay active | resolves to `per-commit` | `auto` |
| `squash` | repositories that squash many commits into one PR merge | changelog write/check hooks skip changelog enforcement | resolves to `release-only` | `generate` |

Minimal config:

```toml
[tool.rrt]
release_branch = "release/v{version}"
changelog_file = "CHANGELOG.md"
changelog_workflow = "incremental"  # or "squash"

[[tool.rrt.version_targets]]
path = "pyproject.toml"
kind = "pep621"
```

Native config is also supported in `package.json` (`"rrt": { ... }`) and
`Cargo.toml` (`[package.metadata.rrt]` / `[workspace.metadata.rrt]`). Go repos
should use `.rrt.toml` or `.config/rrt.toml`.

## What the project includes

- `rrt` CLI for branches, bumps, config inspection, and Git helpers
- `rrt-hooks` for `pre-commit`, `lefthook`, and CI validation
- a reusable GitHub Action in `action.yml`
- bundled agent skills for `uvx` and installed-CLI workflows
- docs for branch policy, hook setup, and release workflows

## Start with the doc that matches your task

- Docs index: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md>
- GitHub Action: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/action.md>
- CLI reference: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/rrt-cli.md>
- Hook setup: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/hooks.md>
- Conventional branches: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/branch.md>
- Git workflow helpers: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/git.md>
- Agent skills: <https://github.com/Anselmoo/repo-release-tools/blob/main/docs/skill.md>

## License

`repo-release-tools` is released under the MIT License.

Some workflow ideas were initially inspired by
[`joseluisq/gitnow`](https://github.com/joseluisq/gitnow), but the `rrt git`
surface is intentionally narrower and reshaped around conventional branching,
safe commits, and release automation.

Built with ❤️ for safe, simple release automation.

## Project layout

The tree below is kept in sync automatically. To update it after structural
changes, run:

```bash
rrt tree --format rich --inject README.md --anchor project-tree
```

The command rewrites the content between the `<!-- rrt:auto:start:project-tree -->`
├── docs/
│   ├── _config.yml
│   ├── action.md
│   ├── agent-instructions.md
│   ├── branch.md
│   ├── doctor.md
│   ├── eol.md
│   ├── git.md
│   ├── hooks.md
│   ├── index.md
│   ├── rrt-cli.md
│   ├── skill.md
│   └── tree.md
├── evals/
│   ├── evals-1.json
│   ├── evals-2.json
│   └── evals.json
├── scripts/
│   ├── check_no_raw_prints.py
│   └── generate_cli_docs.py
├── src/
│   └── repo_release_tools/
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── branch.py
│       │   ├── bump.py
│       │   ├── ci_version.py
│       │   ├── config_cmd.py
│       │   ├── doctor.py
│       │   ├── env_cmd.py
│       │   ├── eol_check.py
│       │   ├── git_cmd.py
│       │   ├── init.py
│       │   ├── skill.py
│       │   └── tree.py
│       ├── tools/
│       │   ├── __init__.py
│       │   └── inject.py
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── color.py
│       │   ├── context.py
│       │   ├── font.py
│       │   ├── glyphs.py
│       │   ├── layout.py
│       │   ├── messaging.py
│       │   ├── progress.py
│       │   ├── prompt.py
│       │   └── syntax.py
│       ├── __init__.py
│       ├── __main__.py
│       ├── action.py
│       ├── changelog.py
│       ├── cli.py
│       ├── config.py
│       ├── eol.py
│       ├── git.py
│       ├── hooks.py
│       ├── skill_assets.py
│       ├── version_targets.py
│       └── versioning.py
├── tests/
│   ├── conftest.py
│   ├── test_branch.py
│   ├── test_bump.py
│   ├── test_changelog.py
│   ├── test_ci_version.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_config_cmd.py
│   ├── test_doctor.py
│   ├── test_env_cmd.py
│   ├── test_eol.py
│   ├── test_eol_check.py
│   ├── test_generate_cli_docs.py
│   ├── test_git_cmd.py
│   ├── test_git_helpers.py
│   ├── test_glyphs.py
│   ├── test_hooks.py
│   ├── test_init.py
│   ├── test_output.py
│   ├── test_runtime_hybrid.py
│   ├── test_skill.py
│   ├── test_syntax_extra.py
│   ├── test_tree.py
│   ├── test_ui_color.py
│   ├── test_ui_font.py
│   ├── test_ui_init.py
│   ├── test_ui_layout.py
│   ├── test_ui_messaging.py
│   ├── test_ui_progress.py
│   ├── test_ui_prompt.py
│   ├── test_ui_syntax.py
│   ├── test_user_experience_simulator.py
│   ├── test_version_targets.py
│   └── test_versioning.py
├── action.yml
├── CHANGELOG.md
├── CLAUDE.md
├── cpm.lock
├── cpm.toml
├── Dockerfile
├── lefthook.yml
├── LICENSE
├── pyproject.toml
├── README.md
└── uv.lock
and `<!-- rrt:auto:end:project-tree -->` HTML anchors without touching anything
else in the file. Pass `--dry-run` to preview the result first.

<!-- rrt:auto:start:project-tree -->
├── docs/
│   ├── _config.yml
│   ├── action.md
│   ├── agent-instructions.md
│   ├── branch.md
│   ├── doctor.md
│   ├── eol.md
│   ├── git.md
│   ├── hooks.md
│   ├── index.md
│   ├── rrt-cli.md
│   ├── skill.md
│   └── tree.md
├── evals/
│   ├── evals-1.json
│   ├── evals-2.json
│   └── evals.json
├── scripts/
│   ├── check_no_raw_prints.py
│   └── generate_cli_docs.py
├── src/
│   └── repo_release_tools/
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── branch.py
│       │   ├── bump.py
│       │   ├── ci_version.py
│       │   ├── config_cmd.py
│       │   ├── doctor.py
│       │   ├── env_cmd.py
│       │   ├── eol_check.py
│       │   ├── git_cmd.py
│       │   ├── init.py
│       │   ├── skill.py
│       │   └── tree.py
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── color.py
│       │   ├── context.py
│       │   ├── font.py
│       │   ├── glyphs.py
│       │   ├── layout.py
│       │   ├── messaging.py
│       │   ├── progress.py
│       │   ├── prompt.py
│       │   └── syntax.py
│       ├── __init__.py
│       ├── __main__.py
│       ├── action.py
│       ├── changelog.py
│       ├── cli.py
│       ├── config.py
│       ├── eol.py
│       ├── git.py
│       ├── hooks.py
│       ├── inject.py
│       ├── skill_assets.py
│       ├── version_targets.py
│       └── versioning.py
├── tests/
│   ├── conftest.py
│   ├── test_branch.py
│   ├── test_bump.py
│   ├── test_changelog.py
│   ├── test_ci_version.py
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_config_cmd.py
│   ├── test_doctor.py
│   ├── test_env_cmd.py
│   ├── test_eol.py
│   ├── test_eol_check.py
│   ├── test_generate_cli_docs.py
│   ├── test_git_cmd.py
│   ├── test_git_helpers.py
│   ├── test_glyphs.py
│   ├── test_hooks.py
│   ├── test_init.py
│   ├── test_output.py
│   ├── test_runtime_hybrid.py
│   ├── test_skill.py
│   ├── test_syntax_extra.py
│   ├── test_tree.py
│   ├── test_ui_color.py
│   ├── test_ui_font.py
│   ├── test_ui_init.py
│   ├── test_ui_layout.py
│   ├── test_ui_messaging.py
│   ├── test_ui_progress.py
│   ├── test_ui_prompt.py
│   ├── test_ui_syntax.py
│   ├── test_user_experience_simulator.py
│   ├── test_version_targets.py
│   └── test_versioning.py
├── action.yml
├── CHANGELOG.md
├── CLAUDE.md
├── cpm.lock
├── cpm.toml
├── Dockerfile
├── lefthook.yml
├── LICENSE
├── pyproject.toml
├── README.md
└── uv.lock
<!-- rrt:auto:end:project-tree -->
