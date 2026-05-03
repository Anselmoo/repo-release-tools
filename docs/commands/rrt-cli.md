# RRT CLI

<!-- Auto-generated from repo_release_tools.cli.build_parser(); run `poe docs-generate` to refresh. -->

This reference is generated from the live `argparse` configuration in
`repo_release_tools.cli` and `src/repo_release_tools/commands/*.py`.

Use `poe docs-generate` to rewrite this file or `poe docs-check` to
verify it is current.

## Global help

```text
Usage:  rrt [OPTIONS] <command>

repo-release-tools: branch, commit, and version helpers for Git repositories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --version        Show version and exit.
  --format FORMAT  Output format. Defaults to text.
  --no-color       Disable all ANSI color output.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Version & Release
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  bump        Bump project version using [tool.rrt] config.
  ci-version  Compute and apply CI pre-release versions (PEP 440 / SemVer).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Repository Health
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  doctor  Validate the resolved rrt configuration for the current repository.
  config  Inspect the resolved rrt configuration after discovery and auto-detection.
  env     Show environment variables and interpreter details that affect rrt behavior.
  eol     Check detected host runtimes and project minimum versions against end-of-life dates.
  toc     Read a Markdown file and print a nested bullet-list TOC to stdout.
  tree    Render a directory tree from the selected root while respecting gitignore rules.
  docs    Scan source files and extract inline documentation blocks

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Git Workflow
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  branch  Branch management helpers for conventional branch naming.
  git     Git workflow helpers for repository status, commit, sync, and history operations.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Setup & Tooling
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  init   Generate a starter rrt configuration for the current repository or manifest.
  skill  Install the bundled repo-release-tools agent skill.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch rename --type fix --scope api "repair config loader"
  $ rrt bump patch --dry-run
  $ rrt git status
  $ rrt doctor
  $ rrt skill install --target copilot-local
  $ rrt @args.txt
```

## `rrt bump`

Bump a release version and prepare the associated release branch.

### Overview

This command reads the active ``[tool.rrt]`` configuration, computes a new
version, updates configured files, and creates the release branch named by the
selected version group.

The bump value may be one of:

* ``major``, ``minor``, or ``patch`` to increment the current version
* an explicit version string such as ``2.1.0``

### What the command updates

Depending on the selected version group, the command can update:

* version targets defined in ``[[tool.rrt.version_targets]]``
* dependency or documentation pins configured for the group
* the changelog file
* lockfiles, when the group defines a lock command

### Release workflow

1. Load the repository config from ``[tool.rrt]``.
2. Resolve the selected version group.
3. Compute the new version from the current group version or the explicit
   ``<bump>`` value.
4. Update version targets and optional pin targets.
5. Update the changelog unless ``--no-changelog`` is set.
6. Run the configured lock command unless ``--no-update`` is set.
7. Create the release branch and stage or commit the resulting changes.

### Changelog behavior

The changelog update logic supports three modes:

* ``auto`` - promote ``[Unreleased]`` when it has entries, otherwise generate a
  new section from git history
* ``promote`` - require a non-empty ``[Unreleased]`` section and rename it to
  the new version heading
* ``generate`` - always generate a fresh section from the commit log

When an empty ``[Unreleased]`` placeholder exists, generated content is kept
below it so the placeholder stays at the top of the file.

### Safety notes

* The working tree must be clean unless ``--dry-run`` is used.
* Existing release branches are refused unless ``--force`` is set.
* ``--no-commit`` leaves the branch created with staged changes only.
* ``--dry-run`` previews the planned file edits and git actions without writing
  to disk.

### Examples

* ``rrt bump patch``
* ``rrt bump minor --dry-run``
* ``rrt bump 2.1.0 --no-changelog --no-commit``
* ``rrt bump major --base-branch develop``

```text
Usage:  rrt bump [OPTIONS] <bump>

Bump project version using [tool.rrt] config.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <bump>                 major | minor | patch | <semver>  — bump kind or explicit version

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help             Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Release control
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --dry-run              Preview changes without writing to disk.
  --force                Reset the release branch if it already exists.
  --no-commit            Skip the git commit step.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Content
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --no-changelog         Do not update the changelog file.
  --no-pin-sync          Skip dependency pin synchronisation.
  --no-update            Skip the lockfile update step.
  --include-maintenance  Include maintenance commits in changelog.
  --changelog-mode MODE  How to write changelog entries (auto | promote | generate).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Git
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --base-branch BRANCH   Branch to base the release on.
  --group GROUP          Version group to bump when multiple groups are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt bump patch
  $ rrt bump minor --dry-run
  $ rrt bump 2.1.0 --no-changelog --no-commit
  $ rrt bump major --base-branch develop
```

## `rrt ci-version`

Compute and apply CI release versions from ``[tool.rrt]`` config.

### Overview

This command mirrors the behavior of the repository's CI version helper, but
uses the active ``[tool.rrt]`` configuration to discover version targets and
group defaults.

It is organized into three subcommands:

* ``compute`` - print the published version for the current GitHub Actions run
* ``apply`` - write an explicit version string to all configured CI targets
* ``sync`` - compute the published version and immediately apply it

### Version rules

The computed CI version depends on the Git ref:

* ``refs/tags/v*`` - return the tag name with the leading ``v`` removed
* ``refs/heads/main`` - build a PEP 440 dev release using
  ``{base}.dev{GITHUB_RUN_ID}{GITHUB_RUN_ATTEMPT:02d}``
* any other ref - return the base version unchanged

CLI flags such as ``--ref``, ``--ref-name``, ``--run-id``, ``--run-attempt``,
``--base``, and ``--group`` override the corresponding environment variables
and config defaults when present.

### Output formats

When applying a version, each target uses its configured ``ci_format``:

* ``pep440`` - write the version string unchanged
* ``semver_pre`` - convert a PEP 440 dev release into a Cargo-compatible
  prerelease string via ``to_semver()``

Only targets with a valid ``ci_format`` are updated.

### Safety notes

* ``compute`` writes a single machine-readable version line to stdout.
* ``apply`` and ``sync`` validate the selected config and fail fast on missing
  or incompatible targets.
* ``sync`` is equivalent to ``compute`` followed by ``apply`` using the result.
* ``--dry-run`` previews file updates without modifying the repository.

### Examples

* ``rrt ci-version compute``
* ``rrt ci-version apply 1.2.3.dev4``
* ``rrt ci-version sync``

```text
Usage:  rrt ci-version [OPTIONS] <ci_version_cmd>

Compute and apply CI pre-release versions (PEP 440 / SemVer).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  compute     Print the published version for the current GitHub Actions run.
  apply       Apply a concrete version string to all ci_format-configured targets.
  sync        Compute the published version from GitHub Actions env and apply it.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt ci-version compute
  $ rrt ci-version apply 1.2.3.dev4
  $ rrt ci-version sync
```

### `rrt ci-version compute`

```text
Usage:  rrt ci-version compute [OPTIONS]

Print the CI/published version for the current GitHub Actions context, using --base and --group overrides when provided.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --group GROUP    Version group to read/apply when multiple release groups are configured.
  --base VERSION   Base version to compute from (default: read from first configured version target).
  --ref REF        Git ref override (default: $GITHUB_REF).
  --ref-name NAME  Git ref-name override (default: $GITHUB_REF_NAME).
  --run-id ID      GitHub Actions run ID override (default: $GITHUB_RUN_ID).
  --run-attempt N  GitHub Actions run-attempt override (default: $GITHUB_RUN_ATTEMPT).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt ci-version compute
  $ rrt ci-version compute --base 1.2.3 --ref refs/heads/main --run-id 42 --run-attempt 3
```

### `rrt ci-version apply`

```text
Usage:  rrt ci-version apply [OPTIONS] <version>

Apply one explicit CI version string to every configured ci_format target in the selected version group.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <version>      Version string to apply (e.g. 0.2.0.dev12345601).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --dry-run      Preview without writing changes.
  --group GROUP  Version group to update when multiple release groups are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt ci-version apply 1.2.3.dev4201
  $ rrt ci-version apply 1.2.3.dev4201 --group backend --dry-run
```

### `rrt ci-version sync`

```text
Usage:  rrt ci-version sync [OPTIONS]

Compute the current GitHub Actions CI version and apply it to every configured ci_format target.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --group GROUP    Version group to read/apply when multiple release groups are configured.
  --base VERSION   Base version to compute from (default: read from first configured version target).
  --ref REF        Git ref override (default: $GITHUB_REF).
  --ref-name NAME  Git ref-name override (default: $GITHUB_REF_NAME).
  --run-id ID      GitHub Actions run ID override (default: $GITHUB_RUN_ID).
  --run-attempt N  GitHub Actions run-attempt override (default: $GITHUB_RUN_ATTEMPT).
  --dry-run        Preview without writing changes.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt ci-version sync --dry-run
  $ rrt ci-version sync --group backend --ref refs/heads/main --run-id 42 --run-attempt 1
```

## `rrt doctor`

Validate the health of the resolved rrt configuration for the current repository.

### Overview

`rrt doctor` is a repository health check for release automation. It inspects
the active configuration and looks for the kinds of issues that usually cause
release jobs to fail late: missing files, broken patterns, unreadable version
targets, and optional runtime EOL policy problems.

### What it checks

For each resolved version group, the command checks:

- version target files exist
- version target values can be read
- pin target patterns compile as regular expressions
- pin target files contain at least one match
- the group changelog file exists

It also checks any global pin targets, deduplicating repeated path/pattern
pairs so the same target is not reported twice.

If `[tool.rrt.eol]` is configured, the command adds a runtime EOL section that
checks the configured languages against the repository's host runtime and
project minimum versions.

If `[tool.rrt.docs]` is configured, the command adds a docs lockfile section
that verifies the `.rrt/docs.lock.toml` is consistent with the current source
tree. It detects three lifecycle events that cause drift:

- **file added** — a source file exists on disk but has no entry in the lockfile
- **file deleted** — the lockfile references a source file that no longer exists
- **content modified** — a source file exists but its hash does not match the
  lockfile entry

All three events are reported as errors so they fail the command. Run
`rrt docs generate --format toml` to regenerate the lockfile after any of
these changes.

### Output and severity

The command prints a grouped report for each version group and an overall
status at the end.

- missing targets and missing changelog files are errors
- unreadable version content is reported as a warning
- pin patterns that compile but do not match are reported as a warning
- valid matches and readable targets are reported as OK

For EOL checks, the command uses the configured thresholds from `[tool.rrt.eol]`
and reports the host runtime and project minimum for each configured language.

### Config discovery behavior

If no config file can be found, the command prints repository guidance and
exits with an error.

If a config is auto-detected, the command emits a notice on stderr before the
main report so you can tell that rrt did not use an explicitly selected file.

### Examples

```bash
rrt doctor
```

### Caveats

- The command reports health for the resolved configuration, not just the
  visible file in the current directory.
- EOL checks are only shown when EOL policy is configured.
- Docs lockfile checks are only shown when `[tool.rrt.docs]` is configured.
- A missing or stale lockfile is an error, not a warning — it fails the command.
- A warning does not fail the command; only error-level findings do.

### Related docs

- [Runtime EOL tracking](eol.md)
- [rrt eol (CLI)](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)

```text
Usage:  rrt doctor [OPTIONS]

Validate the resolved rrt configuration for the current repository.

Checks configured version targets, pin patterns, changelog files, and optional runtime EOL policy so you can catch broken release automation before a bump or release run.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt doctor
```

## `rrt config`

Inspect the resolved rrt configuration for the current repository.

### Overview

This command shows the configuration that rrt will actually use after
repository discovery and any automatic config-file detection. It is the
fastest way to answer:

- Which config file did rrt pick?
- Which version groups were resolved?
- Which files and targets belong to each group?

Use this command when you want to verify release metadata before running a
bump, changelog update, or release workflow.

### What the command reports

The default view renders a tree-style summary with:

- the config file source, or an "auto-detected" notice when no explicit file
  was selected
- the number of version groups in the resolved configuration
- each version group name
- per-group details for:
  - `release_branch`
  - `changelog`
  - `lock_command`, when configured
  - `generated_files`, when configured
  - `version_targets`

Each version target is rendered using the same internal description that rrt
uses elsewhere, so the output is intended to be directly useful in generated
CLI documentation.

### Raw mode

`--raw` prints the underlying config file instead of the rendered tree. The
file is syntax-highlighted when possible and written directly to standard
output.

This is useful when you want to inspect the exact TOML/text content that rrt
loaded, rather than the resolved structure.

### Failure behavior

The command exits with a non-zero status when:

- no config file can be found
- the config file cannot be loaded
- the resolved config is invalid
- the raw file cannot be read in `--raw` mode

In these cases, the command writes the error or discovery guidance to stderr.

### Examples

```bash
rrt config
rrt config --raw
```

### Caveats

- Paths in the tree are shown relative to the current repository root.
- The resolved output reflects discovery and auto-detection, not just the
  contents of one file.

```text
Usage:  rrt config [OPTIONS]

Inspect the resolved rrt configuration after discovery and auto-detection.

Shows which config file rrt will use, the version groups it resolved, and the targets each group manages. Use --raw to print the underlying config file instead of the rendered tree view.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
  --raw       Show the raw config file with syntax highlighting instead of the tree view.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt config
  $ rrt config --raw
```

## `rrt env`

Inspect the process environment and runtime context used by rrt.

### Overview

This command is a compact diagnostics tool for answering "what environment am
I running in?" It does not read repository configuration. Instead, it reports
the interpreter and terminal-related values that can affect rrt output.

### What it reports

The standard text view prints:

- platform
- Python version
- Python executable path
- `TERM`
- `COLORTERM`
- whether `NO_COLOR` is enabled
- `RRT_COLOR`

The `NO_COLOR` field is normalized to a friendly enabled/disabled value rather
than echoing the raw environment variable.

### JSON mode

Use `--json` to emit the same fields as a JSON object. This is useful for
automation, debugging, and documentation tooling that prefers structured
output.

### Examples

```bash
rrt env
rrt env --json
```

### Caveats

- This command reports only a small set of environment values that are most
  relevant to rrt behavior.
- It is a snapshot of the current process, not a probe of the wider shell or
  login environment.

```text
Usage:  rrt env [OPTIONS]

Show environment variables and interpreter details that affect rrt behavior.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
  --json      Output the environment as JSON.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt env
  $ rrt env --json
```

## `rrt eol`

Check detected runtimes and project minimum versions against end-of-life policy.

### Overview

`rrt eol` helps you answer two questions for one or more languages:

- Is the current host runtime still supported?
- Is the repository's declared minimum version still supported?

It is designed for release pipelines and maintenance workflows where runtime
support windows matter.

### What the command checks

For each requested language, the command checks:

- the host runtime detected on the current machine
- the project minimum version detected from the repository

Each version is compared against EOL records and classified as:

- supported
- expiring soon
- end-of-life
- unknown

When the runtime cannot be detected, the command prints `not detected` instead
of failing that check.

### Data sources

By default, rrt uses bundled EOL data. With `--fetch-live`, it refreshes the
records from endoflife.date for the current run.

Language selection comes from the resolved configuration when available. If no
EOL config is present, the command defaults to Python.

### Policy behavior

The effective thresholds come from `[tool.rrt.eol]` when configured, with CLI
flags applied on top for the current invocation.

Important policy switches:

- `--warn-days` sets the warning window
- `--error-days` sets the failure window
- `--allow-eol` downgrades EOL failures to warnings
- `--language` limits the check to one language

### Output

The command prints a small summary first, then one section per language with
host runtime and project minimum results. If all checks pass it ends with a
success line; otherwise it prints a failure line and returns a non-zero exit
code.

### Examples

```bash
rrt eol
rrt eol --language node --fetch-live
rrt eol --warn-days 90 --error-days 30
```

### Caveats

- Supported languages are limited to the values exposed by rrt's EOL helpers.
- Configured EOL overrides apply per language and version cycle.
- `--allow-eol` changes exit-code behavior, not the underlying status labels.

```text
Usage:  rrt eol [OPTIONS]

Check detected host runtimes and project minimum versions against end-of-life dates.

Uses bundled EOL data by default and can refresh from endoflife.date on demand. When [tool.rrt.eol] is configured, CLI flags override the configured thresholds for this invocation.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --language LANG  Check one language only (go, node, nodejs, python, rust). Default: from config or python.
  --fetch-live     Fetch fresh EOL data from endoflife.date instead of using bundled snapshot.
  --warn-days N    Warn when EOL is within N days (default: 180 or from config).
  --error-days N   Error when EOL is within N days (default: 0 or from config = only on actual EOL).
  --allow-eol      Downgrade errors to warnings (useful during migration grace periods).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt eol
  $ rrt eol --language node --fetch-live
  $ rrt eol --warn-days 90 --error-days 30
```

## `rrt toc`

``rrt toc`` — generate and inject a Markdown table of contents.

### Overview

``rrt toc FILE`` reads a Markdown file and prints a nested bullet list of its
headings to stdout.  With ``--inject`` and ``--anchor``, the generated TOC is
written in-place inside a marked anchor block in a target file.

### Usage

```
rrt toc FILE [--min-level N] [--max-level N]
rrt toc FILE --inject TARGET --anchor ID [--min-level N] [--max-level N] [--dry-run]
```

### Anchors

Place a pair of HTML comments in the target file to mark where the TOC
should live:

```markdown
<!-- rrt:auto:start:toc -->
<!-- rrt:auto:end:toc -->
```

The content between the markers is replaced on every ``rrt toc --inject`` run.
Everything outside the markers is preserved unchanged.

### Options

| Flag | Default | Description |
|---|---|---|
| ``FILE`` | — | Markdown file to parse for headings |
| ``--inject FILE`` | — | Target file to update in-place |
| ``--anchor ID`` | — | Anchor ID inside the inject target |
| ``--min-level N`` | 1 | Shallowest heading level to include (1 = ``#``) |
| ``--max-level N`` | 6 | Deepest heading level to include (6 = ``######``) |
| ``--dry-run`` | — | Print result instead of writing (requires ``--inject``) |

``--inject`` and ``--anchor`` must always be used together.

```text
Usage:  rrt toc [OPTIONS] FILE

Read a Markdown file and print a nested bullet-list TOC to stdout.

With --inject and --anchor the generated TOC is written in-place inside
an anchor block in a target file.  Markers delimit the block:

  <!-- rrt:auto:start:ID -->
  <!-- rrt:auto:end:ID -->

Everything outside the markers is preserved unchanged.
--inject and --anchor must always be used together.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  FILE           Markdown file to parse for headings.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --inject FILE  Markdown file to update in-place. Requires --anchor. The anchored block is replaced; all other content is preserved.
  --anchor ID    Anchor ID to replace inside the --inject file. Place <!-- rrt:auto:start:<ID> --> and <!-- rrt:auto:end:<ID> --> markers in the target file.
  --min-level N  Shallowest heading level to include (default: 1 = #).
  --max-level N  Deepest heading level to include (default: 6 = ######).
  --dry-run      Print the result instead of writing (only effective with --inject).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt toc README.md
  $ rrt toc README.md --min-level 2 --max-level 3
  $ rrt toc README.md --inject README.md --anchor toc
  $ rrt toc README.md --inject README.md --anchor toc --dry-run
```

## `rrt tree`

### Project tree

`rrt tree` renders a deterministic project tree with Git-aware filtering and
multiple output modes for terminal use, docs, and copy/paste workflows.

#### Formats

- `classic` — platform-aware tree connectors
- `ascii` — forced ASCII connectors
- `markdown` — nested markdown bullets
- `rich` — Rich rendering with fallback to classic

#### Typical usage

```text
rrt tree
rrt tree --format markdown --max-depth 3
rrt tree --dirs-only --root src/repo_release_tools
```

#### Embedding a tree into a Markdown file

Use `--inject` and `--anchor` to automatically update a block inside any
Markdown document without touching the surrounding prose.

**Step 1 — add anchor markers once** (HTML comments, invisible when rendered):

```markdown
## Project layout

Some intro text above — preserved on every run.

<!-- rrt:auto:start:project-tree -->
<!-- rrt:auto:end:project-tree -->

Some text below — also preserved.
```

**Step 2 — run `rrt tree` with `--inject`**:

```bash
rrt tree --format markdown --inject README.md --anchor project-tree
```

Only the content between the markers is replaced; everything else in the file
stays untouched.

**Preview without writing (dry-run)**:

```bash
rrt tree --format markdown --inject README.md --anchor project-tree --dry-run
```

##### Anchor ID rules

An anchor ID must start with an ASCII letter or digit followed by any
combination of ASCII letters, digits, dots, underscores, or hyphens.

Valid examples: `project-tree`, `src.layout`, `tree_v2`

#### Notes

- In Git repos, ignore behavior follows Git via `git check-ignore`.
- Outside Git repos, fallback ignore filtering skips common transient dirs.
- Hidden files are excluded unless `--show-hidden` is provided.
- `--inject` and `--anchor` must always be used together.

```text
Usage:  rrt tree [OPTIONS]

Render a directory tree from the selected root while respecting gitignore rules.

Formats: classic, ascii, markdown, rich. Rich output falls back to classic if the optional rich package is unavailable.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --format       Output format. Defaults to classic.
  --max-depth N  Maximum recursion depth (default: unlimited).
  --dirs-only    Show directories only.
  --show-hidden  Include dotfiles and dot-directories.
  --root PATH    Root directory to render (default: current directory).
  --inject FILE  Markdown file to update in-place. Requires --anchor. The anchored block is replaced; all other content is preserved.
  --anchor ID    Anchor ID to replace inside the --inject file. Place <!-- rrt:auto:start:<ID> --> and <!-- rrt:auto:end:<ID> --> markers in the target file.
  --dry-run      Print the result instead of writing (only effective with --inject).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt tree
  $ rrt tree --format ascii
  $ rrt tree --format markdown --max-depth 3
  $ rrt tree --root src/repo_release_tools --dirs-only
  $ rrt tree --format markdown --inject README.md --anchor project-tree
```

## `rrt docs`

```text
Usage:  rrt docs [OPTIONS] <docs_action>

Scan source files and extract inline documentation blocks
across Python, TypeScript/JavaScript, Go, and Rust.

Sub-actions: generate (default), check

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  generate     Extract docs and emit in the selected format.
  check        Exit 1 if the docs lockfile is stale.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help   Show this message and exit.
  --root PATH  Project root directory (default: current directory).
  --dry-run    Print what would be done without writing files.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples:
  rrt docs generate                         # explicit mode, md output to stdout
  rrt docs generate --format toml           # write .rrt/docs.lock.toml
  rrt docs generate --format rich           # colourised terminal preview
  rrt docs check                            # exits 1 if lockfile is stale
  rrt docs generate --lang python,go        # multi-language extraction
```

### `rrt docs generate`

```text
Usage:  rrt docs generate [OPTIONS]

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help    Show this message and exit.
  --format      Output format (default: first format in config, usually md).
  --lang LANGS  Comma-separated language filter, e.g. python,go (overrides config).
  --root PATH   Project root directory (default: current directory).
  --dry-run     Print what would be done without writing files.
```

### `rrt docs check`

```text
Usage:  rrt docs check [OPTIONS]

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help        Show this message and exit.
  --lock-file PATH  Path to the lock file (default: from config or .rrt/docs.lock.toml).
  --root PATH       Project root directory (default: current directory).
```

## `rrt branch`

### Conventional branches for trunk-based publishing

`repo-release-tools` uses conventional branches to keep trunk-based publishing
predictable for humans, hooks, and automation.

This page is generated from `repo_release_tools.commands.branch.SEMANTIC_BRANCHES_DOC`.
The canonical command reference is [docs/commands/rrt-cli.md](rrt-cli.md). This page
summarizes the naming rules that the CLI and hooks enforce.

#### Standard format

```text
<type>/<kebab-case-description>
```

Examples:

- `feat/add-config-discovery`
- `fix/handle-tag-workflows`
- `docs/split-readme-into-docs`

#### Built-in branch types

Conventional branch types are accepted out of the box:

- `feat`
- `fix`
- `chore`
- `docs`
- `refactor`
- `test`
- `ci`
- `perf`
- `style`
- `build`

#### Special names

These branch names are also valid:

- `main`
- `master`
- `develop`
- `release/v<semver>`

`release/v<semver>` is validated as a semver-aware special case, not as a free
form `type/slug` branch.

#### AI helper branches

Branches created by assistant-driven workflows are accepted with these prefixes:

- `claude/...`
- `codex/...`
- `copilot/...`

They still use normal slug validation, so the suffix should stay lowercase and
kebab-cased.

#### Bot and custom branches

Branches created by dependency bots are accepted too:

- `dependabot/...`
- `renovate/...`

Custom prefixes can be added through configuration:

```toml
[tool.rrt]
extra_branch_types = ["greenkeeper", "snyk"]
```

Bot and custom prefixes are treated as passthrough types. Their suffixes are
only required to be non-empty, because upstream tools often generate slugs with
slashes or underscores.

#### Why the rules matter

- branch names stay readable in review queues
- commit subjects and branch types stay aligned
- release automation can distinguish ordinary work from release branches
- hooks and CI can apply one consistent policy across local and remote checks

#### Related commands

- `rrt branch new`
- `rrt branch rescue`
- `rrt branch rename`
- `rrt git commit`
- `rrt git doctor`

```text
Usage:  rrt branch [OPTIONS] <branch_command>

Branch management helpers for conventional branch naming.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  new         Create a new conventionally named branch.
  rescue      Move commits to a new branch and reset the current branch.
  rename      Rename the current branch: change type, scope, description, or any combination.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch new fix "repair config loader" --scope api
  $ rrt branch rename --type fix --scope api "fix config loader"
  $ rrt branch rescue feat "rescue work in progress"
```

### `rrt branch new`

```text
Usage:  rrt branch new [OPTIONS] TYPE <description>

Create a new conventionally named branch from a commit type, optional scope, and description.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  TYPE
  <description>  Short branch description.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --scope SCOPE  Optional scope.
  --dry-run      Preview without touching git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch new fix "repair config loader" --scope api
  $ rrt branch rename --type fix --scope api "fix config loader"
  $ rrt branch rescue feat "rescue work in progress"
```

### `rrt branch rescue`

```text
Usage:  rrt branch rescue [OPTIONS] TYPE <description>

Rescue commits onto a new branch and reset the current branch to a safe point.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  TYPE
  <description>  Short branch description.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --scope SCOPE  Optional scope.
  --dry-run      Preview without touching git.
  --since SHA    Rescue commits since this SHA instead of origin/<branch>.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch new fix "repair config loader" --scope api
  $ rrt branch rename --type fix --scope api "fix config loader"
  $ rrt branch rescue feat "rescue work in progress"
```

### `rrt branch rename`

```text
Usage:  rrt branch rename [OPTIONS] <description>

Rename the current branch using conventional branch naming rules.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <description>  New branch description words (replaces the current description).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --type TYPE    New conventional commit type (e.g. feat, fix, build).
  --scope SCOPE  New scope to prefix the slug with.
  --no-scope     Remove the scope from the new branch name (requires description words).
  --dry-run      Preview the rename without touching git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch new fix "repair config loader" --scope api
  $ rrt branch rename --type fix --scope api "fix config loader"
  $ rrt branch rescue feat "rescue work in progress"
```

## `rrt git`

### Git magic

`repo-release-tools` ships a small set of opinionated Git workflows for branch
health, commit drafting, sync, and history repair.

This page is generated from `repo_release_tools.git.GIT_MAGIC_DOC`.
This page stays workflow-oriented. For the full command surface and option
details, see [docs/commands/rrt-cli.md](rrt-cli.md).

#### Workflow map

- **Inspect** — `rrt git status`, `diff`, `log`, `doctor`, `sync-status`,
  `check-dirty-tree`
- **Draft commits** — `rrt git commit`, `commit-all`, `squash-local`
- **Move and sync** — `rrt git sync`, `move`, `undo-safe`, `rebootstrap`
- **Branch workflows** — `rrt branch new`, `rescue`, `rename`

#### What the Git helpers optimize for

- compact, human-readable summaries first
- explicit safety checks before destructive actions
- conventional commit subjects and conventional branch names when possible
- reuse across local CLI, hooks, and CI

#### Notable behavior

- `rrt git commit` infers the commit type from the current branch only when the
  branch is a conventional `type/slug` branch.
- Branches named `main`, `master`, `develop`, `release/v<semver>`, AI helper
  branches, bot branches, and custom branch prefixes are treated as special
  cases and may require `--type` for commit drafting.
- `sync` and `move` auto-stash local changes when needed.
- `undo-safe` and `rebootstrap` can rewrite history; `rebootstrap` also
  requires explicit confirmation before it destroys the current repository
  history.
- Commands that support `--dry-run` preview git operations without changing the
  worktree.

#### Current command surface

```text
rrt git status
rrt git diff
rrt git log
rrt git doctor
rrt git sync-status
rrt git check-dirty-tree
rrt git commit "handle empty config"
rrt git commit-all "snapshot parser cleanup"
rrt git sync
rrt git move feat/new-parser
rrt git squash-local "ship parser cleanup"
rrt git undo-safe --keep-staged
rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
```

#### See also

- [Conventional branches](branch.md)
- [Generated CLI reference](rrt-cli.md)

```text
Usage:  rrt git [OPTIONS] <git_command>

Git workflow helpers for repository status, commit, sync, and history operations.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  status            Show a compact branch and worktree status view.
  diff              Show a compact diff using rrt glyph formatting.
  log               Show a compact commit history view.
  doctor            Run a compact repository health report for rrt workflows.
  sync-status       Analyze unresolved conflicts and whether sync/rebase work is needed.
  check-dirty-tree  Exit non-zero when the working tree is dirty. Useful in hooks and CI.
  commit            Create a conventional commit, inferring type from the current branch.
  commit-all        Stage all files and create a conventional commit from the branch context.
  sync              Fetch, stash if needed, and pull the current branch safely.
  move              Switch branches safely by stashing and restoring local changes.
  squash-local      Squash local commits since upstream or a base ref into one commit.
  undo-safe         Undo a commit while keeping work staged or in the working tree.
  rebootstrap       Destroy current git history and create a fresh repository history.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help        Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git status
  $ rrt git diff --against HEAD~1
  $ rrt git commit --type fix "make output clearer"
  $ rrt git sync
  $ rrt git undo-safe
```

### `rrt git status`

```text
Usage:  rrt git status [OPTIONS]

Show the current branch, upstream, and compact typed worktree changes for the repository.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git status
```

### `rrt git diff`

```text
Usage:  rrt git diff [OPTIONS]

Render a compact tracked-file diff with rrt glyphs for working-tree, staged, or ref-based changes.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --staged       Show staged changes instead of working-tree changes.
  --against REF  Diff against a specific commit or ref.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git diff
  $ rrt git diff --staged
  $ rrt git diff --against HEAD~1
```

### `rrt git log`

```text
Usage:  rrt git log [OPTIONS]

Show recent commits in a compact rrt log view with short SHAs, subjects, and refs.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help   Show this message and exit.
  -n, --limit  Number of commits to show.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git log
  $ rrt git log --limit 20
```

### `rrt git doctor`

```text
Usage:  rrt git doctor [OPTIONS]

Run branch, upstream, worktree, conflict, commit-subject, and changelog checks for an rrt workflow.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help        Show this message and exit.
  --changelog-file  Changelog path used for doctor checks.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git doctor
  $ rrt git doctor --changelog-file docs/CHANGELOG.md
```

### `rrt git sync-status`

```text
Usage:  rrt git sync-status [OPTIONS]

Report merge or rebase blockers plus ahead/behind drift against the upstream branch or --base-ref.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help      Show this message and exit.
  --base-ref REF  Ref to analyze against. Defaults to the current upstream branch.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git sync-status
  $ rrt git sync-status --base-ref origin/main
```

### `rrt git check-dirty-tree`

```text
Usage:  rrt git check-dirty-tree [OPTIONS]

Exit non-zero when the working tree is dirty and print a compact status summary for hooks or CI.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git check-dirty-tree
```

### `rrt git commit`

```text
Usage:  rrt git commit [OPTIONS] <description>

Create one conventional commit from the provided description, inferring the type from the current branch when possible.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <description>  Commit description words.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --type TYPE    Explicit conventional commit type. Defaults to the current branch type.
  --scope SCOPE  Optional commit scope.
  --breaking     Mark the commit as breaking.
  --dry-run      Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git commit "refresh help examples"
  $ rrt git commit --type fix --scope cli "handle empty config"
  $ rrt git commit --breaking "ship parser v2"
```

### `rrt git commit-all`

```text
Usage:  rrt git commit-all [OPTIONS] <description>

Stage all tracked and untracked changes, then create one conventional commit from the current branch context.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <description>  Commit description words.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --type TYPE    Explicit conventional commit type. Defaults to the current branch type.
  --scope SCOPE  Optional commit scope.
  --breaking     Mark the commit as breaking.
  --dry-run      Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git commit-all "refresh release metadata"
  $ rrt git commit-all --type chore --scope deps "update lockfiles"
```

### `rrt git sync`

```text
Usage:  rrt git sync [OPTIONS]

Fetch, auto-stash when needed, and pull the current branch from its upstream using rebase by default.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
  --merge     Use plain git pull instead of git pull --rebase.
  --dry-run   Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git sync
  $ rrt git sync --merge
  $ rrt git sync --dry-run
```

### `rrt git move`

```text
Usage:  rrt git move [OPTIONS] <target>

Switch to another branch, optionally creating it, while auto-stashing and restoring local changes when needed.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <target>      Target branch name.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help    Show this message and exit.
  -b, --create  Create the target branch before switching to it.
  --dry-run     Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git move release/v1.2.0
  $ rrt git move -b feat/help-copy --dry-run
```

### `rrt git squash-local`

```text
Usage:  rrt git squash-local [OPTIONS] <description>

Squash commits ahead of the upstream branch or --base-ref into one conventional commit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <description>   Commit description words.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help      Show this message and exit.
  --type TYPE     Explicit conventional commit type. Defaults to the current branch type.
  --scope SCOPE   Optional commit scope.
  --breaking      Mark the commit as breaking.
  --dry-run       Preview without changing git.
  --base-ref REF  Base ref to squash against. Defaults to the current upstream branch.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git squash-local "ship parser"
  $ rrt git squash-local --base-ref origin/main --type fix "repair sync handling"
```

### `rrt git undo-safe`

```text
Usage:  rrt git undo-safe [OPTIONS]

Reset to HEAD~1 or another target while keeping changes staged (--keep-staged) or in the working tree.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --target REF   Ref to reset to. Defaults to HEAD~1.
  --keep-staged  Use git reset --soft so changes stay staged.
  --dry-run      Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git undo-safe
  $ rrt git undo-safe --keep-staged
  $ rrt git undo-safe --target HEAD~2 --dry-run
```

### `rrt git rebootstrap`

```text
Usage:  rrt git rebootstrap [OPTIONS]

Back up the current .git directory, reinitialize the repository, and create a fresh history snapshot or empty bootstrap commit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help                          Show this message and exit.
  --yes-i-know-this-destroys-history  Required confirmation for the destructive history reset.
  --allow-remote                      Allow rebootstrap even when remotes are configured.
  --hard-init                         Recreate .git and make only one empty initial commit, leaving files untracked.
  --branch BRANCH                     Initial branch name for the new repository. Defaults to the current branch.
  --message                           Commit message for the new initial commit.
  --empty-first                       Create an empty bootstrap commit before adding files.
  --empty-message                     Commit message for the optional empty bootstrap commit.
  --dry-run                           Preview without changing git.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt git rebootstrap --yes-i-know-this-destroys-history --dry-run
  $ rrt git rebootstrap --yes-i-know-this-destroys-history --empty-first
  $ rrt git rebootstrap --yes-i-know-this-destroys-history --hard-init --branch main
```

## `rrt init`

Initialize repo-release-tools configuration for a repository.

### Overview

`rrt init` writes a starter configuration for the current repository. It can
either create a standalone `.rrt.toml` file or merge an rrt section into an
existing project manifest.

The command is designed to be safe by default: it refuses to overwrite
existing config unless `--force` is used, and `--dry-run` shows the exact
output without touching files.

### Target surfaces

- `.rrt.toml` (default)
- `pyproject.toml` -> `[tool.rrt]`
- `Cargo.toml` -> `[package.metadata.rrt]`
- `package.json` -> `"rrt"` key
- `.rrt.toml` with Go-oriented recommendations (`--target go`)

### Behavior

- Detects an existing explicit config discovered by repo-release-tools and
  warns when a new `.rrt.toml` would lose precedence.
- Refuses to append duplicate rrt sections to TOML manifests.
- Validates that `package.json` contains a top-level object before merging.
- Prints a rendered preview in dry-run mode.

### Examples

- `rrt init`
- `rrt init --dry-run`
- `rrt init --target pyproject`
- `rrt init --target node --force`
- `rrt init --target go`

### Caveats

- `--target pyproject` and `--target cargo` append to an existing file only;
  they do not create missing manifests.
- `--target node` replaces the top-level `"rrt"` key in `package.json`.
- `--target go` keeps the `.rrt.toml` filename but uses Go-oriented
  recommendations.

```text
Usage:  rrt init [OPTIONS]

Generate a starter rrt configuration for the current repository or manifest.

By default this writes .rrt.toml. Use --target to append or merge equivalent configuration into pyproject.toml, Cargo.toml, package.json, or a Go-oriented .rrt.toml template.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --dry-run        Preview without writing files.
  --force          Overwrite an existing .rrt.toml or package.json "rrt" key when writing those targets.
  --target FORMAT  Where to write the rrt configuration. rrt-toml (default): write .rrt.toml; pyproject: append [tool.rrt] to pyproject.toml; cargo: append [package.metadata.rrt] to Cargo.toml; node: merge or replace the "rrt" key in package.json; go: write .rrt.toml with the recommended Go template.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt init --dry-run
  $ rrt init --target pyproject
  $ rrt init --target node --force
  $ rrt init --target go
```

## `rrt skill`

Install the bundled repo-release-tools agent skill.

### Overview

`rrt skill` manages installation of the packaged `repo-release-tools` skill
into tool-specific skill directories. The only implemented subcommand is
`install`.

### Target surfaces

The install command can write to local or global skill roots for:

- Claude: `.claude/skills`
- Codex: `.codex/skills`
- Copilot: `.copilot/skills`

Each target receives a directory named after the bundled skill, containing
`SKILL.md`.

### Behavior

- Accepts one or more `--target` values; duplicates are ignored after first use.
- Resolves local targets relative to the current working directory and global
  targets relative to the home directory.
- Refuses to overwrite an existing installation unless `--force` is provided.
- Supports `--dry-run` previews that show the resolved destination paths
  without writing files.

### Examples

- `rrt skill install --target copilot-local`
- `rrt skill install --target claude-local --target codex-local`
- `rrt skill install --target copilot-global --force --dry-run`

### Caveats

- `rrt skill` requires a subcommand; use `rrt skill install ...`.
- Without `--target`, the command prints available destinations in dry-run
  mode and otherwise fails.
- Existing symlinks, files, or directories at the destination are replaced
  only when `--force` is used.

```text
Usage:  rrt skill [OPTIONS] <skill_command>

Install the bundled repo-release-tools agent skill.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  install     Install the bundled repo-release-tools skill into agent skill directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt skill install --target copilot-local
  $ rrt skill install --target claude-local --target codex-local
```

### `rrt skill install`

```text
Usage:  rrt skill install [OPTIONS]

Install the bundled repo-release-tools skill into one or more local or global agent skill directories.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help     Show this message and exit.
  --target DEST  Install target. Repeat to install into multiple locations: copilot-local, claude-local, codex-local, copilot-global, claude-global, codex-global.
  --dry-run      Preview without writing files.
  --force        Overwrite an existing installed repo-release-tools skill.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt skill install --target copilot-local
  $ rrt skill install --target claude-local --target codex-local
  $ rrt skill install --target copilot-global --force --dry-run
```
