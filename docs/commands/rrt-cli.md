---
title: "rrt CLI"
permalink: "/commands/rrt-cli/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="../../assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="../../assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt CLI

<!-- Auto-generated from repo_release_tools.cli.build_parser(); run `rrt docs publish` to refresh. -->

<!-- rrt:auto:start:toc -->
- [Global help](#global-help)
- [Command reference](#command-reference)
<!-- rrt:auto:end:toc -->

This reference is generated from the live `argparse` configuration in
`repo_release_tools.cli` and `src/repo_release_tools/commands/*.py`.

Use `rrt docs publish` to rewrite this file or `rrt docs publish --check` to
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
  -h, --help                   Show this message and exit.
  --version                    Show version and exit.
  --format FORMAT              Output format. Defaults to text.
  --no-color                   Disable all ANSI color output.
  -v, --verbose                Increase output verbosity (-v summary, -vv details, -vvv debug).
  --generate-completion SHELL  Print shell completion script for SHELL and exit.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Version & Release
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  bump        Bump project version using [tool.rrt] config.
  changelog   Commands for working with the project changelog.
  ci-version  Compute and apply CI pre-release versions (PEP 440 / SemVer).
  release     Release-specific workflows and checks.
  sync        Fetch all released versions of the configured upstream package and print those that are strictly newer than the current project version.  With --bump, apply each newer version in ascending order, optionally committing and tagging each one.
  workspace   Apply a unified version bump to every listed package.
  tag         Create annotated git tags from the current configured version, or check that existing tags follow the naming convention.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Repository Health
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  doctor     Validate the core automation wiring for the current repository.
  artifacts  Hash and verify generated files against a committed fingerprint lock.
  config     Inspect the resolved rrt configuration after discovery and auto-detection.
  env        Show environment variables and interpreter details that affect rrt behavior.
  eol        Check detected host runtimes and project minimum versions against end-of-life dates.
  toc        Read a Markdown file and print a nested bullet-list TOC to stdout.
  tree       Render a directory tree from the selected root while respecting gitignore rules.
  docs       Scan source files and extract inline documentation blocks
  drift      Lock and check the repo's agent-facing surfaces, such as Claude hooks, agent prompts, and shared skill docs.
  folder     Supervise folder structures against config-defined rules or built-in templates, scaffold missing structure, and infer new templates from existing trees.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
CI & Automation
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  action  Scaffold a starter GitHub Actions workflow that runs repo-release-tools checks.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Git Workflow
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  branch  Branch management helpers for conventional branch naming.
  git     Git workflow helpers for repository status, commit, sync, and history operations.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Setup & Tooling
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  install  Install one or more bundled rrt agent surfaces (skill, agents, hooks) into one or more local/global targets.
  init     Generate a starter rrt configuration for the current repository or manifest.
  skill    Install the bundled rrt user workflow skills.
  agents   Install bundled rrt user agents into one or more local or global agent directories.
  hooks    Install bundled rrt user workflow hook scripts into one or more local hook directories and update the surface's hook registration JSON.

────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
Examples
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  $ rrt branch new feat "add parser"
  $ rrt branch rename --type fix --scope api "repair config loader"
  $ rrt bump patch --dry-run
  $ rrt release check
  $ rrt action init
  $ rrt drift check
  $ rrt git status
  $ rrt doctor
  $ rrt install --target claude-local
  $ rrt skill install --target copilot-local
  $ rrt @args.txt
```

## Command reference

Each command group has its own reference page with the full argparse help.

| Group | Commands | Reference |
|---|---|---|
| **Version & Release** | `bump`, `changelog`, `ci-version`, `release`, `sync`, `workspace`, `tag` | [Version & Release](version-release.md) |
| **Repository Health** | `doctor`, `artifacts`, `config`, `env`, `eol`, `toc`, `tree`, `docs`, `drift`, `folder` | [Repository Health](repo-health.md) |
| **Git Workflow** | `branch`, `git` | [Git Workflow](git-workflow.md) |
| **CI & Automation** | `action` | [CI & Automation](ci-automation.md) |
| **Setup & Tooling** | `install`, `init`, `skill`, `agents`, `hooks` | [Setup & Tooling](setup-tooling.md) |

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
