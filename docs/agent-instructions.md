# repo-release-tools — Hook & Action Reference

<!-- Static context for agents: read this before using any prompt block below. -->

## Agent context

**Repo:** <https://github.com/Anselmoo/repo-release-tools> · Python ≥ 3.12 · `uv_build`

**Entry points** (from `pyproject.toml`):
- `rrt-hooks` → `repo_release_tools.hooks:main` — git hook runner (installed binary, NOT a uvx shortcut)
- `rrt` → `repo_release_tools.cli:app` — developer CLI

**Key files:**
| File | Role |
|---|---|
| `src/repo_release_tools/hooks.py` | All `rrt-hooks` subcommand logic |
| `src/repo_release_tools/changelog.py` | Changelog parsing, `[Unreleased]` management |
| `.pre-commit-hooks.yaml` | Hook definitions consumed by pre-commit |
| `lefthook.yml` | Lefthook configuration (repo root) |
| `action.yml` | Composite GitHub Action |

**Verification commands:**
```bash
uv run pytest tests/test_hooks.py -x -q   # fast unit tests
uvx pre-commit run --all-files             # lint (ruff, line-length 100)
```

**Assumptions:** `pre-commit`, `lefthook`, and `uv` are already installed. Do not recommend `brew install`, `pip install pre-commit`, or `apt install` for these tools.

---

## pre-commit / lefthook

### Activate pre-commit hooks

> Use the following prompt to activate pre-commit hooks for repo-release-tools.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume pre-commit is already installed.
</context>

Activate the pre-commit hooks for this repository. A `.pre-commit-config.yaml` must exist (see prompt below). Then run:

```bash
pre-commit install --install-hooks
```

This installs hooks for every stage declared in `default_install_hook_types`. Commit-msg-stage hooks require `commit-msg` in that list — omitting it silently skips `rrt-update-unreleased` and `rrt-commit-subject`.
````

### Activate lefthook hooks

> Use the following prompt to activate lefthook hooks for repo-release-tools.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume lefthook and uv are already installed.
</context>

Activate lefthook hooks. A `lefthook.yml` must exist at the repo root (see prompt below). Then run:

```bash
uv tool install repo-release-tools   # installs rrt-hooks binary
lefthook install                      # registers git hooks
```

DO NOT use `uvx --from repo-release-tools rrt-hooks …` in `lefthook.yml` — `rrt-hooks` is an installed binary, not a uvx shortcut.
````

### .pre-commit-config.yaml — minimal (auto-write changelog)

> Use the following prompt to configure pre-commit with auto-write changelog.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume pre-commit is already installed.
</context>

Create `.pre-commit-config.yaml` at the repo root with this content:

```yaml
default_install_hook_types: [pre-commit, commit-msg]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.9
    hooks:
      - id: rrt-branch-name
      - id: rrt-update-unreleased
      - id: rrt-commit-subject
```

Hook reference:
- `rrt-branch-name`       pre-commit stage  — validates `<type>/<slug>` branch name
- `rrt-update-unreleased` commit-msg stage  — auto-writes `[Unreleased]` section (like ruff --fix)
- `rrt-commit-subject`    commit-msg stage  — validates Conventional Commits subject

Constraints:
- `rrt-changelog` and `rrt-update-unreleased` are mutually exclusive — use one or the other, never both
- `default_install_hook_types` must include `commit-msg` for `rrt-update-unreleased` and `rrt-commit-subject` to run
````

### .pre-commit-config.yaml — full (all hooks)

> Use the following prompt to configure pre-commit with all available hooks.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume pre-commit is already installed.
</context>

Create `.pre-commit-config.yaml` at the repo root with this content:

```yaml
default_install_hook_types: [pre-commit, commit-msg, pre-push, manual]

repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v0.1.9
    hooks:
      - id: rrt-branch-name        # pre-commit:       validate <type>/<slug> branch name
      - id: rrt-update-unreleased  # commit-msg:       auto-write [Unreleased] section
      - id: rrt-commit-subject     # commit-msg:       validate Conventional Commits subject
      # - id: rrt-changelog        # pre-commit:       require-staged strategy (mutually exclusive with rrt-update-unreleased)
      # - id: rrt-dirty-tree       # pre-push/manual:  fail on dirty working tree
```

Constraints:
- `rrt-changelog` and `rrt-update-unreleased` are mutually exclusive — enable only one
- Do NOT add `default_install_hook_types: [pre-push]` in isolation — include `pre-commit` and `commit-msg` too
````

### lefthook.yml

> Use the following prompt to configure lefthook with repo-release-tools.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build | Conventional Commits | Keep-a-Changelog
Assume lefthook and uv are already installed. rrt-hooks is available on PATH after `uv tool install repo-release-tools`.
</context>

Create `lefthook.yml` at the repo root with this content:

```yaml
commit-msg:
  commands:
    rrt-update-unreleased:
      run: rrt-hooks update-unreleased --message-file {1}
    rrt-commit-subject:
      run: rrt-hooks commit-msg {1}

pre-commit:
  commands:
    rrt-branch-name:
      run: rrt-hooks pre-commit

pre-push:
  commands:
    rrt-changelog:
      run: rrt-hooks check-changelog --subject "$(git log -1 --format=%s)" --strategy unreleased
```

Notes:
- `{1}` is lefthook's template variable for the commit-msg file path (commit-msg stage only)
- `rrt-hooks commit-msg {1}` — positional arg (message_file in argparse)
- `rrt-hooks update-unreleased --message-file {1}` — named flag, takes priority over --subject and .git/COMMIT_EDITMSG

Constraints:
- DO NOT use `uvx --from repo-release-tools rrt-hooks …` — `rrt-hooks` is an installed binary, not a uvx shortcut
- `rrt-changelog` and `rrt-update-unreleased` are mutually exclusive — use one per project
````

### update-unreleased — subject resolution and commit type mapping

> Use the following prompt to understand how rrt-hooks update-unreleased resolves the commit subject.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks update-unreleased (src/repo_release_tools/hooks.py)
Changelog format: Keep-a-Changelog with [Unreleased] section
</context>

`rrt-hooks update-unreleased` resolves the commit subject with this priority:

1. `--message-file PATH`  (lefthook: --message-file {1})
2. `--subject TEXT`       (explicit override)
3. `.git/COMMIT_EDITMSG`  (default fallback — used by pre-commit automatically)

Commit type → CHANGELOG.md section mapping:
- `feat`                           → Added
- `fix`                            → Fixed
- `refactor` / `perf`              → Changed
- `chore`, `ci`, `build`, `test`, `deps`, `docs` → silent no-op (no entry written)

When no mapping exists for the commit type, the hook exits 0 silently — it is not an error.
````

### Manual invocation / smoke test

> Use the following prompt to manually invoke rrt-hooks subcommands for testing.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
Python ≥ 3.12 | uv_build
Assume rrt-hooks is on PATH (installed via `uv tool install repo-release-tools`).
</context>

Manually invoke rrt-hooks subcommands to verify the setup:

```bash
rrt-hooks pre-commit
rrt-hooks check-commit-subject --subject "feat: add widget"
rrt-hooks update-unreleased --subject "feat: add widget"
echo "feat: add widget" > /tmp/msg && rrt-hooks update-unreleased --message-file /tmp/msg
rrt-hooks check-changelog --subject "feat: add widget" --strategy unreleased
rrt-hooks check-dirty-tree
```

Run the test suite:

```bash
uv run pytest tests/test_hooks.py -x -q
uvx pre-commit run --all-files
```
````

---

## actions

### Minimal GitHub Actions workflow

> Use the following prompt to add the minimal repo-release-tools policy check to a workflow.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Action: Anselmoo/repo-release-tools@v0.1.9 (composite action, defined in action.yml)
Wraps rrt-hooks subcommands; runs on ubuntu-latest; requires fetch-depth: 0 for git log access.
</context>

Add this job to `.github/workflows/policy.yml`:

```yaml
name: policy
on: [push, pull_request]

jobs:
  policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # required — rrt-hooks uses git log; shallow clone breaks it
      - uses: Anselmoo/repo-release-tools@v0.1.9
```
````

### Full GitHub Actions workflow — all inputs

> Use the following prompt to configure the action with all available inputs.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Action: Anselmoo/repo-release-tools@v0.1.9 (composite action, defined in action.yml)
Wraps rrt-hooks subcommands; requires fetch-depth: 0.
</context>

Add this job to `.github/workflows/policy.yml`:

```yaml
name: policy
on: [push, pull_request]

jobs:
  policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0        # required — rrt-hooks uses git log; shallow clone breaks it
      - uses: Anselmoo/repo-release-tools@v0.1.9
        with:
          check-branch-name: "true"
          check-commit-subject: "true"
          check-changelog: "true"
          changelog-strategy: "per-commit"  # per-commit | unreleased | release-only
          changelog-file: "CHANGELOG.md"
          check-dirty-tree: "false"
```

All available inputs (action.yml):
- `python-version`:      `"3.12"`        — Python version for the runner
- `working-directory`:   `"."`           — repo path to install and run from
- `check-branch-name`:   `"true"`        — validate `<type>/<slug>` branch name; auto-skips on tag refs
- `branch-ref-type`:     `""`            — override: `"branch"` | `"tag"`
- `branch-name`:         `""`            — override branch name
- `check-commit-subject`: `"true"`       — validate Conventional Commits subject
- `commit-subject`:      `""`            — override commit subject
- `check-changelog`:     `"true"`        — validate changelog updates
- `changelog-file`:      `"CHANGELOG.md"`
- `changelog-strategy`:  `"per-commit"`  — `per-commit` | `unreleased` | `release-only`
- `check-dirty-tree`:    `"false"`       — fail on dirty working tree
````

### changelog-strategy decision guide

> Use the following prompt to choose and configure the right changelog strategy for the action.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Action: Anselmoo/repo-release-tools@v0.1.9
changelog-strategy input controls how the action validates CHANGELOG.md.
</context>

Choose the right changelog strategy based on your workflow:

| Strategy | When to use | Requirement |
|---|---|---|
| `per-commit` | CHANGELOG.md must be in the commit's changed-file list | Commit author must manually update changelog before each commit |
| `unreleased` | `[Unreleased]` section must be non-empty | Pair with `rrt-update-unreleased` (pre-commit or lefthook) to auto-write entries |
| `release-only` | Skip changelog check on PRs/pushes; enforce only at release | Changelog is validated only on tagged releases |

**per-commit** (default):
```yaml
- uses: Anselmoo/repo-release-tools@v0.1.9
  with:
    check-changelog: "true"
    changelog-strategy: "per-commit"
```

**unreleased** (pair with auto-write hooks):
```yaml
- uses: Anselmoo/repo-release-tools@v0.1.9
  with:
    check-changelog: "true"
    changelog-strategy: "unreleased"
```

**Dynamic — unreleased on branches, release-only on tags:**
(`check-branch-name` auto-skips on tag refs — no extra condition needed)
```yaml
- uses: Anselmoo/repo-release-tools@v0.1.9
  with:
    check-branch-name: "true"
    changelog-strategy: ${{ startsWith(github.ref, 'refs/tags/') && 'release-only' || 'unreleased' }}
```

Constraints:
- `per-commit` fails on squash-merge workflows — prefer `unreleased` for PR-based flows
- `fetch-depth: 0` is always required; without it, `git log` returns nothing and checks may silently pass or fail unexpectedly
````

### rrt-hooks equivalents — what the action runs internally

> Use the following prompt to replicate action behaviour locally.

````prompt
<context>
Repo: https://github.com/Anselmoo/repo-release-tools
Action: Anselmoo/repo-release-tools@v0.1.9 (composite action, defined in action.yml)
Entry point: rrt-hooks (installed binary — repo_release_tools.hooks:main)
</context>

The GitHub Action runs these rrt-hooks commands internally:

```bash
# check-branch-name
rrt-hooks check-branch-name --branch "$BRANCH_NAME"

# check-commit-subject
rrt-hooks check-commit-subject --subject "$(git log -1 --pretty=%s)"

# check-changelog
rrt-hooks check-changelog \
  --subject "$(git log -1 --pretty=%s)" \
  --changelog-file CHANGELOG.md \
  --strategy per-commit \
  --branch "$BRANCH_NAME" \
  --ref HEAD

# check-dirty-tree
rrt-hooks check-dirty-tree
```

Use these commands to reproduce a CI failure locally before pushing. All subcommands accept `--dry-run` for safe inspection.
````

## pin_targets — auto-sync version pins in docs and CI

`pin_targets` keeps action refs and pre-commit `rev:` tags in sync with your project version automatically during `rrt bump`.

### When to add pin_targets

Add entries whenever your docs or CI reference the tool's own version as a pin that drifts (e.g. `uses: org/repo@v1.2.3` or `rev: v1.2.3`).

### Config placement

```toml
# pyproject.toml — global (applies to all version groups)
[[tool.rrt.pin_targets]]
path = "docs/github-action.md"
pattern = '(Anselmoo/repo-release-tools@v)(\d+\.\d+\.\d+)()'

[[tool.rrt.pin_targets]]
path = "docs/pre-commit.md"
pattern = '(rev: v)(\d+\.\d+\.\d+)()'
```

Pattern convention: exactly 3 capture groups — `(prefix)(semver)(suffix)`.
The suffix can be empty: use `()` as the third group.

### Bump behavior

1. `rrt bump <kind>` updates version targets as usual.
2. Then for each pin entry (global + group-level, deduplicated), runs `replace_pin_in_file`.
3. Pin files are staged alongside version files before the git commit.
4. `--no-pin-sync` skips this step entirely for a one-off run.

### Validation

```bash
rrt bump minor --dry-run   # preview — shows "Would update" for each pin file
```
