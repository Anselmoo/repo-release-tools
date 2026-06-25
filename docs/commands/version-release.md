---
title: "rrt Version & Release"
permalink: "/commands/version-release/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt Version & Release

<!-- Auto-generated from repo_release_tools.cli.build_parser(); run `rrt docs publish` to refresh. -->

<!-- rrt:auto:start:toc -->
- [`rrt bump`](#rrt-bump)
  - [Overview](#overview)
  - [What the command updates](#what-the-command-updates)
  - [Release workflow](#release-workflow)
  - [Changelog behavior](#changelog-behavior)
  - [Safety notes](#safety-notes)
  - [Examples](#examples)
- [`rrt changelog`](#rrt-changelog)
  - [Overview](#overview-1)
  - [Responsibilities](#responsibilities)
  - [Subcommands](#subcommands)
  - [Behavior](#behavior)
  - [Examples](#examples-1)
  - [Related Docs](#related-docs)
  - [`rrt changelog compare`](#rrt-changelog-compare)
  - [`rrt changelog lint`](#rrt-changelog-lint)
- [`rrt ci-version`](#rrt-ci-version)
  - [file: ci_version.py](#file-civersionpy)
  - [`rrt ci-version compute`](#rrt-ci-version-compute)
  - [`rrt ci-version apply`](#rrt-ci-version-apply)
  - [`rrt ci-version sync`](#rrt-ci-version-sync)
- [`rrt release`](#rrt-release)
  - [Overview](#overview-2)
  - [What it checks](#what-it-checks)
  - [Output and severity](#output-and-severity)
  - [Config discovery behavior](#config-discovery-behavior)
  - [Examples](#examples-2)
  - [Related docs](#related-docs-1)
  - [`rrt release check`](#rrt-release-check)
  - [`rrt release notes`](#rrt-release-notes)
  - [`rrt release repair`](#rrt-release-repair)
- [`rrt workspace`](#rrt-workspace)
  - [Overview](#overview-3)
  - [When to use this](#when-to-use-this)
  - [What it does](#what-it-does)
  - [Safety notes](#safety-notes-1)
  - [Examples](#examples-3)
  - [`rrt workspace bump`](#rrt-workspace-bump)
- [`rrt tag`](#rrt-tag)
  - [Overview](#overview-4)
  - [Responsibilities](#responsibilities-1)
  - [Tag Format](#tag-format)
  - [Behavior](#behavior-1)
  - [Examples](#examples-4)
  - [Caveats](#caveats)
  - [`rrt tag create`](#rrt-tag-create)
  - [`rrt tag check`](#rrt-tag-check)
<!-- rrt:auto:end:toc -->

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
6. Run the configured lock and generated-asset commands unless
   ``--no-update`` is set.
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
  <bump>                  major | minor | patch | alpha | beta | rc | pre-release | calver | <version>  — bump kind or explicit version

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help              Show this message and exit.
  --calver-scheme SCHEME  CalVer scheme to use when bump=calver (YYYY.MM | YYYY.MM.DD | YYYY.M.D).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Release control
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --dry-run               Preview changes without writing to disk.
  --force                 Reset the release branch if it already exists.
  --no-commit             Skip the git commit step.
  --no-verify             Pass --no-verify to git commit (bypass pre-commit hooks).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Content
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --no-changelog          Do not update the changelog file.
  --no-pin-sync           Skip dependency pin synchronisation.
  --no-update             Skip lockfile and generated-asset refresh steps.
  --include-maintenance   Include maintenance commits in changelog.
  --changelog-mode MODE   How to write changelog entries (auto | promote | generate).

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Git
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  --base-branch BRANCH    Branch to base the release on.
  --group GROUP           Version group to bump when multiple groups are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt bump patch
  $ rrt bump minor --dry-run
  $ rrt bump 2.1.0 --no-changelog --no-commit
  $ rrt bump major --base-branch develop
```

## `rrt changelog`

Changelog management command group (compare, lint).

### Overview

`rrt changelog` provides a unified entrypoint for auditing and validating the
project's changelog file. It centralizes utilities for diffing release sections
and enforcing stylistic consistency across entries, ensuring that the
human-readable history remains accurate and professional.

This module acts as a dispatcher for specialized subcommands that handle the
parsing, comparison, and linting of changelog data.

### Responsibilities

- coordinate changelog-related subcommands
- provide a consistent interface for changelog auditing and quality control
- dispatch execution to specialized `compare` and `lint` handlers

### Subcommands

- **compare**: Performs a structured diff between two named release sections.
  It classifies entries as unique to the starting version, common to both, or
  unique to the target version. Useful for PR reviews and release auditing.
- **lint**: Validates the style and structure of changelog entries. It checks
  for sentence casing, trailing punctuation, line length limits, and duplicate
  entries.

### Behavior

- Automatically detects the changelog format (Markdown or RST) based on the
  file extension.
- Discovers the changelog file location from the active `[tool.rrt]`
  configuration.
- Supports both machine-readable (JSON) and human-friendly (colored terminal)
  outputs for auditing subcommands.

### Examples

- `rrt changelog compare v1.2.0 v1.3.0`
- `rrt changelog lint`
- `rrt changelog lint --release v1.5.0 --no-fail`
- `rrt changelog compare v1.0.0 v2.0.0 --format json`

### Related Docs

- [Changelog Comparison](changelog_compare.py)
- [Changelog Linting](changelog_lint.py)
- [rrt bump](bump.py)

```text
Usage:  rrt changelog [OPTIONS] <changelog_command>

Commands for working with the project changelog.

Subcommands:
  compare  Diff two named release sections.
  lint     Lint entries for style consistency.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  compare     Compare two release sections in the changelog.
  lint        Lint changelog entries for style consistency.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
```

### `rrt changelog compare`

```text
Usage:  rrt changelog compare [OPTIONS] <from> <to>

Parse and diff two named release sections from the configured changelog file.

Each entry is classified as only-in-FROM, common, or only-in-TO.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <from>        Release label to compare from.
  <to>          Release label to compare to.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help    Show this message and exit.
  --format      Output format (default: text).
  --group NAME  Version group name.
```

### `rrt changelog lint`

```text
Usage:  rrt changelog lint [OPTIONS]

Validate entries in [Unreleased] (or a named release) for style rules:
sentence case, no trailing period, max length, and no duplicates.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help         Show this message and exit.
  --release VERSION  Lint a specific named release section instead of [Unreleased].
  --no-fail          Report violations without exiting non-zero.
  --group NAME       Version group name.
```

## `rrt ci-version`

Compute and apply CI release versions from ``[tool.rrt]`` config.

### file: ci_version.py

#### Overview

The ``rrt ci-version`` command family centralizes deterministic version
computation and safe application for CI and release automation. It reads the
repository's ``[tool.rrt]`` configuration, discovers version targets and group
defaults, and uses the current CI environment (or explicit CLI overrides) to
produce machine-friendly version identifiers suitable for downstream CI
targets and release workflows.

Subcommands:

- ``compute`` — deterministically compute the version for this run and emit a
    single raw line for scripting and capture.
- ``apply`` — update configured targets that declare a ``ci_format``,
    transforming values when needed (for example converting PEP 440 dev
    releases into Cargo-compatible prerelease identifiers).
- ``sync`` — compute then apply the published version in one operation; both
    ``apply`` and ``sync`` support ``--dry-run`` for safe previews.

Version rules (summary):

- Tag builds (``refs/tags/v*``) yield the tag name with the leading ``v``
    removed.
- Mainline (`refs/heads/main`) builds produce a PEP 440 dev release using
    ``{base}.dev{GITHUB_RUN_ID}{GITHUB_RUN_ATTEMPT:02d}``.
- Other refs return the configured base version unchanged. CLI flags such as
    ``--ref``, ``--run-id``, or ``--base`` override environment-derived values.

Output formats & safety:

- Supported target formats: ``pep440`` and ``semver_pre`` (the latter maps
    PEP 440 dev suffixes to SemVer prerelease tokens).
- The command validates conversions and fails fast on incompatible inputs to
    avoid writing invalid CI data.
- ``compute`` is machine-friendly (single-line stdout); ``apply``/``sync`` are
    human-friendly with progress, dry-run previews, and explicit error messages.

Examples::

        rrt ci-version compute
        rrt ci-version apply 1.2.3.dev42 --group backend --dry-run

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

## `rrt release`

Validate release-oriented rrt configuration targets for the current repository.

### Overview

`rrt release check` is the feature-specific health gate for release automation.
It focuses on the config targets that drive version bumps and changelog updates,
without mixing in broader repository automation checks.

### What it checks

For each resolved version group, the command checks:

- version target files exist
- version target values can be read
- pin target patterns compile as regular expressions
- pin target files contain at least one match
- the group changelog file exists

It also checks any global pin targets, deduplicating repeated path/pattern
pairs so the same target is not reported twice.

### Output and severity

The command prints one grouped report per version group and an overall status at
the end.

- missing targets and missing changelog files are errors
- unreadable version content is reported as a warning
- pin patterns that compile but do not match are reported as a warning
- valid matches and readable targets are reported as OK

### Config discovery behavior

If no config file can be found in the current directory or any ancestor, the
command prints repository guidance and exits with an error. The supported
config roots are `pyproject.toml`, `package.json`, `Cargo.toml`, `.rrt.toml`,
and `.config/rrt.toml`.

If a config is auto-detected, the command emits a notice on stderr before the
main report so you can tell that rrt did not use an explicitly selected file.

### Examples

```bash
rrt release check
```

The command can be run from a nested subdirectory inside the repository; rrt
walks upward until it finds the repo root and then checks the resolved config
from there.

Version targets may also point at Go, Rust, or .NET-style version files when
you need to keep multiple language surfaces aligned.

### Related docs

- [rrt doctor](doctor.md)
- [rrt eol (CLI)](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)
- [GitHub Action](action.md)

```text
Usage:  rrt release [OPTIONS] <release_command>

Release-specific workflows and checks.

Use `rrt release check` to validate version targets, pin targets, and changelog files without mixing in broader repository automation checks.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  check       Validate version targets, pin targets, and changelog files.
  notes       Emit a changelog release section as a formatted release body.
  repair      Fix drift or recreate a release branch cleanly.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
```

### `rrt release check`

```text
Usage:  rrt release check [OPTIONS]

Validate the release-oriented parts of the resolved rrt configuration for the current repository, starting from the nearest repo root above the current working directory.

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
  $ rrt release check
```

### `rrt release notes`

```text
Usage:  rrt release notes [OPTIONS]

Extract a section from the configured changelog and emit it as a formatted release body ready for GitHub, GitLab, or any markdown editor. Defaults to [Unreleased]; use --version or --latest-released to target a published section.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help         Show this message and exit.
  --format FORMAT    Output format: md (default) or gh-release.
  --group GROUP      Version group to read from when multiple groups are configured.
  --version VERSION  Extract notes for a specific released section (e.g. 1.2.3 or v1.2.3). Matching is case- and v-prefix-insensitive.
  --latest-released  Extract notes for the topmost released section (the one just below [Unreleased]). Useful in tag-triggered CI release jobs.
  --output PATH      Write the release body to PATH instead of stdout.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt release notes
  $ rrt release notes --format gh-release
  $ rrt release notes --format md > RELEASE_BODY.md
  $ rrt release notes --latest-released --output RELEASE_CHANGELOG.md
  $ rrt release notes --version 1.2.3
```

### `rrt release repair`

```text
Usage:  rrt release repair [OPTIONS]

Verify (and optionally fix) version target / pin target / changelog drift on the current branch, or recreate the branch cleanly from a base ref while preserving the declared version and its [VERSION] changelog body.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help             Show this message and exit.
  --from BASE            Recreate mode: rewind the current branch to BASE (commit, branch, or tag) and replay the version bump. Without this flag the command runs in verify-and-fix mode.
  --yes, -y              Required to apply changes; otherwise the command only previews.
  --hotfix               Implies --yes and tags the commit as `chore(release): repair v{ver}` so hotfix recoveries are distinguishable from regular bumps.
  --changelog-from PATH  Read the [VERSION] body from PATH instead of the current branch's CHANGELOG.md. Useful when the polluted HEAD has lost the section.
  --force-allow-pushed   Allow recreate when the branch is ahead of origin/<branch>. The new history must then be force-pushed with `git push --force-with-lease`.
  --no-backup            Skip the `repair/backup/<branch>-<ts>` ref that is otherwise written before any destructive operation.
  --group GROUP          Pick the version group when multiple are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt release repair
  $ rrt release repair --yes
  $ rrt release repair --from main --yes
  $ rrt release repair --from main --hotfix
```

## `rrt workspace`

Coordinate version bumps across multiple packages in a monorepo.

### Overview

`rrt workspace bump` applies the same version bump to every listed package in
one pass.  It reads each package's own ``[tool.rrt]`` configuration, verifies
that all packages are loadable, then updates version targets and changelogs in
a single coordinated sweep.

### When to use this

Use ``rrt workspace bump`` when your repository contains multiple
independently-versioned packages (e.g. a Python backend, a TypeScript SDK, and
a Go CLI tool) that are always released together at the same version.

### What it does

1. Resolve each package path from ``--packages``.
2. Load each package's rrt config and read its current version.
3. Compute the new version using the same bump logic as ``rrt bump``.
4. For each package: update version targets and, unless ``--no-changelog``,
   the changelog.
5. Report every file write to stdout (or preview them with ``--dry-run``).

### Safety notes

* All package configs must exist and be valid before any file is written.
* ``--dry-run`` previews all planned writes without touching any file.

### Examples

```bash
rrt workspace bump minor --packages api,sdk,docs
rrt workspace bump 2.0.0 --packages ./packages/api,./packages/sdk
rrt workspace bump patch --dry-run --packages api,sdk
```

```text
Usage:  rrt workspace [OPTIONS] <workspace_command>

Apply a unified version bump to every listed package.

Each package must have its own [tool.rrt] configuration. All configs are validated before any file is written.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  bump        Bump versions across all listed packages.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
```

### `rrt workspace bump`

```text
Usage:  rrt workspace bump [OPTIONS] <bump>

Apply the same version bump to every package listed in --packages.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  <bump>            major | minor | patch | pre-release | calver | <version>

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help        Show this message and exit.
  --packages PATHS  Comma-separated list of package directories to bump.
  --dry-run         Preview changes without writing to disk.
  --no-changelog    Skip changelog updates.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt workspace bump minor --packages api,sdk,docs
  $ rrt workspace bump 2.0.0 --packages ./packages/api,./packages/sdk
  $ rrt workspace bump patch --dry-run --packages api,sdk
```

## `rrt tag`

Create and validate release tags for the current repository.

### Overview

`rrt tag` centralizes the management of Git release tags, ensuring that the
repository's version history remains consistent with its configuration. It
automates the creation of annotated tags and provides validation tools to
verify that existing tags align with the project's versioning policy.

The command supports both manual release tagging and automated verification in
CI pipelines, helping to maintain a clean and reliable release record.

### Responsibilities

- create annotated Git tags matching the current configured version
- support custom tag prefixes and annotation messages
- validate that existing tags follow the expected naming convention
- verify that the expected tag for the current version is present
- optionally push newly created tags to the remote repository

### Tag Format

By default, tags are created with a `v` prefix (e.g., `v1.2.3`) as is standard
for many version control and release automation tools.

- The prefix can be customized using `--prefix <string>`.
- The prefix can be removed entirely using `--prefix ""`.
- Tag names are derived directly from the current version read from the
  active `[tool.rrt]` configuration group.

### Behavior

- **create**: Reads the current version from config, builds the tag name and
  message, and executes `git tag -a`. Refuses to overwrite existing tags
  unless `--force` is used.
- **check**: Scans all repository tags, identifies those that don't match the
  requested prefix, and verifies the presence of the tag corresponding to the
  current version.
- **push**: When `--push` is used with `create`, the command executes
  `git push origin <tag>` after a successful local tag creation.
- **dry-run**: Previews the `git` commands that would be executed without
  modifying the repository.

### Examples

- `rrt tag create`
- `rrt tag create --push --message "Production release v1.5.0"`
- `rrt tag create --prefix "" --force`
- `rrt tag check`
- `rrt tag check --strict --prefix "rel-"`

### Caveats

- Requires a valid Git repository and `repo-release-tools` configuration.
- Annotated tags are used to ensure that metadata (author, date, message) is
  correctly captured in the Git history.
- The `check --strict` mode is recommended for CI pipelines to ensure that a
  tag was correctly created before a release proceeds.

```text
Usage:  rrt tag [OPTIONS] <tag_command>

Create annotated git tags from the current configured version, or check that existing tags follow the naming convention.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  create      Create an annotated git tag for the current version.
  check       Validate existing tags against the configured version.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
```

### `rrt tag create`

```text
Usage:  rrt tag create [OPTIONS]

Create an annotated git tag matching the current configured version.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --prefix PREFIX  Tag prefix (default: 'v'). Pass empty string for no prefix.
  --message MSG    Annotation message. Defaults to 'Release <tag>'.
  --push           Push the tag to origin after creating it.
  --force          Delete and recreate the tag if it already exists.
  --dry-run        Preview what would happen without making changes.
  --group GROUP    Version group to read when multiple groups are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt tag create
  $ rrt tag create --push
  $ rrt tag create --prefix '' --message 'Release 1.2.3'
  $ rrt tag check
  $ rrt tag check --strict
```

### `rrt tag check`

```text
Usage:  rrt tag check [OPTIONS]

Check that existing git tags follow the naming convention.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help       Show this message and exit.
  --prefix PREFIX  Expected tag prefix (default: 'v').
  --strict         Fail if the expected tag for the current version is missing.
  --group GROUP    Version group to read when multiple groups are configured.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt tag create
  $ rrt tag create --push
  $ rrt tag create --prefix '' --message 'Release 1.2.3'
  $ rrt tag check
  $ rrt tag check --strict
```

## Version target configuration reference

### `kind='pattern'` targets

When a version string lives outside a well-known format (`pep621`,
`cargo_toml`, `package_json`, etc.), use `kind='pattern'` with a
single-capture-group regex. The captured group is **exactly the version
string** — no prefix or suffix groups needed.

```toml
[[tool.rrt.version_targets]]
path = "src/myapp/__init__.py"
kind = "pattern"
pattern = '^VERSION = "([^"]+)"$'
```

Rules:

- `pattern` must compile as a valid Python regex.
- The regex must contain **exactly 1 capture group** whose match is the
  version string itself.
- `kind='pattern'` is mutually exclusive with `section`, `field`, and
  all other `kind` values.
- The pattern is applied with `re.MULTILINE`; use `^` / `$` anchors for
  line-level matching.

`kind='pattern'` differs from the **legacy bare-pattern** approach (no
`kind`), which requires 3 groups — `(prefix)(version)(suffix)`. The
`kind='pattern'` form is preferred for new targets because the regex is
shorter and group intent is unambiguous:

```toml
# Legacy 3-group pattern — still supported
[[tool.rrt.version_targets]]
path = "docs/conf.py"
pattern = '^(release = ")([^"]+)(")$'

# Preferred: kind='pattern' with 1 capture group
[[tool.rrt.version_targets]]
path = "docs/conf.py"
kind = "pattern"
pattern = '^release = "([^"]+)"$'
```

### `pin_target_missing`

Controls what happens when a `[[tool.rrt.pin_targets]]` entry pattern
finds no matches in the target file:

| Value | Behavior |
|---|---|
| `"error"` *(default)* | `rrt bump` fails if any pin target has zero matches |
| `"warn"` | `rrt bump` prints a warning and continues |

Set in `[tool.rrt]`:

```toml
[tool.rrt]
pin_target_missing = "warn"
```

Use `"warn"` during a migration where some pin files may not yet contain
the expected pattern, or when a pin target is intentionally optional.

### `version_groups` — per-component versioning

`version_groups` lets a single repository maintain multiple independently
released components, each with its own version, changelog, and release
branch.

```toml
[[tool.rrt.version_groups]]
name = "backend"
release_branch = "release/backend/v{version}"
changelog_file = "backend/CHANGELOG.md"

  [[tool.rrt.version_groups.version_targets]]
  path = "backend/pyproject.toml"
  kind = "pep621"

[[tool.rrt.version_groups]]
name = "sdk"
release_branch = "release/sdk/v{version}"
changelog_file = "sdk/CHANGELOG.md"

  [[tool.rrt.version_groups.version_targets]]
  path = "sdk/package.json"
  kind = "package_json"
```

Each group supports: `release_branch`, `changelog_file`,
`changelog_workflow`, `lock_command`, `generated_files`,
`version_targets`, and `pin_targets`.

Bump a specific group:

```bash
rrt bump minor --group backend
rrt bump patch --group sdk
```

When a single group is configured, `--group` is optional. With multiple
groups, set `default_group_name` to select the default:

```toml
[tool.rrt]
default_group_name = "backend"
```

See also: `rrt workspace bump` to bump all groups to the same version in
one pass.

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
