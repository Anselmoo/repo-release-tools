---
title: "rrt CI & Automation"
permalink: "/commands/ci-automation/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt CI & Automation

<!-- Auto-generated from repo_release_tools.cli.build_parser(); run `rrt docs publish` to refresh. -->

<!-- rrt:auto:start:toc -->
- [`rrt action`](#rrt-action)
  - [Overview](#overview)
  - [Responsibilities](#responsibilities)
  - [Workflow Content](#workflow-content)
  - [Behavior](#behavior)
  - [Examples](#examples)
  - [Caveats](#caveats)
  - [`rrt action init`](#rrt-action-init)
<!-- rrt:auto:end:toc -->

## `rrt action`

Scaffold GitHub Actions workflows for repo-release-tools.

### Overview

`rrt action` manages the bootstrapping of GitHub Actions workflows to automate
repository policy checks. It centralizes the creation of standard CI
configurations, ensuring that `repo-release-tools` is correctly integrated into
the project's development lifecycle.

The primary subcommand is `init`, which writes a pre-configured workflow file
that performs branch naming, commit subject, and changelog verification on
every push and pull request.

### Responsibilities

- generate starter GitHub Actions workflows using the current `rrt` version
- automate the integration of `repo-release-tools` into the project's CI
- provide safe file operations with dry-run and force-overwrite protections
- emit high-signal, formatted feedback during the scaffolding process

### Workflow Content

The generated workflow (`.github/workflows/rrt.yml`) includes:

- **Triggers**: Runs on `push` to the main branch and on all `pull_request` events.
- **Environment**: Executes on the latest Ubuntu runner.
- **Steps**:
    - Full history checkout (`fetch-depth: 0`) to support git-based checks.
    - Execution of `Anselmoo/repo-release-tools` with standard policy flags
      (branch name, commit subject, and changelog checks).

### Behavior

- Writes to `.github/workflows/rrt.yml` relative to the current working directory.
- Refuses to overwrite an existing workflow unless `--force` is provided.
- Supports `--dry-run` to preview the generated YAML in the terminal without
  writing to disk.
- Uses syntax highlighting when displaying the workflow preview in dry-run mode.

### Examples

- `rrt action init`
- `rrt action init --dry-run`
- `rrt action init --force`

### Caveats

- Requires a Git repository with a `.github/workflows` directory structure
  (automatically created if missing).
- The generated version pin matches the version of `rrt` currently in use.

```text
Usage:  rrt action [OPTIONS] <action_command>

Scaffold a starter GitHub Actions workflow that runs repo-release-tools checks.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  init        Write a starter workflow that uses repo-release-tools.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt action init
  $ rrt action init --dry-run
  $ rrt action init --force
```

### `rrt action init`

```text
Usage:  rrt action init [OPTIONS]

Write a starter .github/workflows/rrt.yml workflow for repo-release-tools CI.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Arguments
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Options
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  -h, --help  Show this message and exit.
  --dry-run   Preview without writing files.
  --force     Overwrite an existing workflow file.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt action init
  $ rrt action init --dry-run
  $ rrt action init --force
```

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
