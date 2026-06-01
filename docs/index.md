---
title: "repo-release-tools"
permalink: "/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# repo-release-tools

`repo-release-tools` has three main surfaces:

- **[Generated CLI reference](commands/rrt-cli.md)** for local release automation, Git
  helpers, config inspection, and the bundled `rrt skill install` command
- **[GitHub Action](action.md)** for CI policy checks that mirror the
  local workflow
- **Generated topic docs**:
  [Semantic branches](commands/branch.md) and [rrt git](commands/git_cmd.md) for
  the branch naming model and Git workflow guidance

If you need command syntax, start with the generated CLI reference first. It is
the canonical home for the current `rrt` command surface.

## Start here

- [Generated CLI reference](commands/rrt-cli.md) — generated reference for branches, bumps, Git
  workflow helpers, config checks, and skill installation
- [GitHub Action](action.md) — CI checks for branch names, commit
  subjects, changelog policy, and optional doctor/dirty-tree gates
- [pre-commit / lefthook](commands/hooks.md) — local hook setup for incremental or
  squash-based changelog workflows
- [Skills](commands/skill.md) — bundled `uvx` and installed-CLI agent skills

## Then follow the workflow

<!-- rrt:auto:start:index-topic-links -->
- [rrt branch](commands/branch.md) — generated branch naming model and allowed branch types
- [rrt git](commands/git_cmd.md) — generated Git helpers and workflow shortcuts
- [rrt tree](commands/tree.md) — generated guide for `rrt tree` output modes, ignore behavior, and traversal controls
- [MCP Server](mcp-server.md) — MCP install and connect guide
<!-- rrt:auto:end:index-topic-links -->

## Command reference by group

The CLI is split into per-group reference pages (auto-generated from the live argparse tree) and
prose topic pages for individual commands.

### Auto-generated group reference pages

| Group | Commands | Page |
|---|---|---|
| **Version & Release** | `bump`, `changelog`, `ci-version`, `release`, `workspace`, `tag` | [version-release](commands/version-release.md) |
| **Repository Health** | `doctor`, `artifacts`, `config`, `env`, `eol`, `toc`, `tree`, `docs`, `drift`, `folder` | [repo-health](commands/repo-health.md) |
| **Git Workflow** | `branch`, `git` | [git-workflow](commands/git-workflow.md) |
| **CI & Automation** | `action` | [ci-automation](commands/ci-automation.md) |
| **Setup & Tooling** | `install`, `init`, `skill`, `agents`, `hooks` | [setup-tooling](commands/setup-tooling.md) |

The [rrt CLI index](commands/rrt-cli.md) page has the global help and links to all groups.

### Prose topic pages

| Doc | Content |
|---|---|
| [branch](commands/branch.md) | Branch naming model and allowed types |
| [bump](commands/bump.md) | Stub — see [version-release](commands/version-release.md) |
| [ci_version](commands/ci_version.md) | Stub — see [version-release](commands/version-release.md) |
| [config_cmd](commands/config_cmd.md) | Stub — see [repo-health](commands/repo-health.md) |
| [doctor](commands/doctor.md) | Repository automation health checks |
| [drift](commands/drift.md) | Agent-facing surface drift detection |
| [env_cmd](commands/env_cmd.md) | Stub — see [repo-health](commands/repo-health.md) |
| [eol_check](commands/eol_check.md) | Runtime end-of-life checks |
| [folder](commands/folder.md) | Folder structure supervision |
| [git_cmd](commands/git_cmd.md) | Git workflow helpers |
| [hooks](commands/hooks.md) | pre-commit / lefthook hook setup |
| [init](commands/init.md) | Stub — see [setup-tooling](commands/setup-tooling.md) |
| [install](commands/install.md) | Agent surface installation |
| [skill](commands/skill.md) | Bundled agent skills |
| [toc](commands/toc.md) | Markdown TOC generation |
| [tree](commands/tree.md) | Directory tree rendering |

## Changelog workflow

`repo-release-tools` supports two changelog styles:

- `incremental` *(default)* — maintain changelog state during development
- `squash` — skip per-commit changelog enforcement and generate or correct
  changelog entries when changes are squashed together

If you are unsure where to start:

1. Read [`commands/rrt-cli.md`](commands/rrt-cli.md) to confirm the available CLI commands and
   `changelog_workflow` config
2. Read [`commands/hooks.md`](commands/hooks.md) for the matching local hook setup
3. Read [`action.md`](action.md) to see how
   `changelog-strategy: auto` follows that workflow in CI

## Visual identity

### Terminal banners

| Dark theme | Light theme |
|---|---|
| ![banner-dark](assets/banner-dark.png) | ![banner-light](assets/banner-light.png) |

*Rendered by `rrt` at launch. ASCII art generated by `banner.py` using Pillow.*

### Badge families

Adaptive SVG badges switch automatically between dark and light variants based
on the viewer's system preference (`prefers-color-scheme`). Five variants per
badge family are available:

These badges are intentionally complete for the current source-of-truth icon
registry in [`src/repo_release_tools/tools/platform.py`](../src/repo_release_tools/tools/platform.py).
If an icon appears missing, update the registry and badge mappings together so
the docs, source-code anchors, and icon list stay in lockstep across platform,
registry, and language labels.

#### Platform

| Label | Color | Dark | Light | Reto Dark | Reto Light |
|---|---|---|---|---|---|
| GitHub | ![](assets/badges/github.svg) | ![](assets/badges/github-dark.svg) | ![](assets/badges/github-light.svg) | ![](assets/badges/github-reto-dark.svg) | ![](assets/badges/github-reto-light.svg) |
| GitLab | ![](assets/badges/gitlab.svg) | ![](assets/badges/gitlab-dark.svg) | ![](assets/badges/gitlab-light.svg) | ![](assets/badges/gitlab-reto-dark.svg) | ![](assets/badges/gitlab-reto-light.svg) |
| Bitbucket | ![](assets/badges/bitbucket.svg) | ![](assets/badges/bitbucket-dark.svg) | ![](assets/badges/bitbucket-light.svg) | ![](assets/badges/bitbucket-reto-dark.svg) | ![](assets/badges/bitbucket-reto-light.svg) |
| Azure DevOps | ![](assets/badges/azure.svg) | ![](assets/badges/azure-dark.svg) | ![](assets/badges/azure-light.svg) | ![](assets/badges/azure-reto-dark.svg) | ![](assets/badges/azure-reto-light.svg) |
| Codeberg | ![](assets/badges/codeberg.svg) | ![](assets/badges/codeberg-dark.svg) | ![](assets/badges/codeberg-light.svg) | ![](assets/badges/codeberg-reto-dark.svg) | ![](assets/badges/codeberg-reto-light.svg) |
| Gitea | ![](assets/badges/gitea.svg) | ![](assets/badges/gitea-dark.svg) | ![](assets/badges/gitea-light.svg) | ![](assets/badges/gitea-reto-dark.svg) | ![](assets/badges/gitea-reto-light.svg) |
| Helm | ![](assets/badges/helm.svg) | ![](assets/badges/helm-dark.svg) | ![](assets/badges/helm-light.svg) | ![](assets/badges/helm-reto-dark.svg) | ![](assets/badges/helm-reto-light.svg) |
| Kubernetes | ![](assets/badges/kubernetes.svg) | ![](assets/badges/kubernetes-dark.svg) | ![](assets/badges/kubernetes-light.svg) | ![](assets/badges/kubernetes-reto-dark.svg) | ![](assets/badges/kubernetes-reto-light.svg) |
| GitHub Actions | ![](assets/badges/githubactions.svg) | ![](assets/badges/githubactions-dark.svg) | ![](assets/badges/githubactions-light.svg) | ![](assets/badges/githubactions-reto-dark.svg) | ![](assets/badges/githubactions-reto-light.svg) |
| Bash | ![](assets/badges/bash.svg) | ![](assets/badges/bash-dark.svg) | ![](assets/badges/bash-light.svg) | ![](assets/badges/bash-reto-dark.svg) | ![](assets/badges/bash-reto-light.svg) |
| Java | ![](assets/badges/java.svg) | ![](assets/badges/java-dark.svg) | ![](assets/badges/java-light.svg) | ![](assets/badges/java-reto-dark.svg) | ![](assets/badges/java-reto-light.svg) |
| Generic | ![](assets/badges/generic.svg) | ![](assets/badges/generic-dark.svg) | ![](assets/badges/generic-light.svg) | ![](assets/badges/generic-reto-dark.svg) | ![](assets/badges/generic-reto-light.svg) |

#### Registry

| Label | Color | Dark | Light | Reto Dark | Reto Light |
|---|---|---|---|---|---|
| PyPI | ![](assets/badges/pypi.svg) | ![](assets/badges/pypi-dark.svg) | ![](assets/badges/pypi-light.svg) | ![](assets/badges/pypi-reto-dark.svg) | ![](assets/badges/pypi-reto-light.svg) |
| npm | ![](assets/badges/npm.svg) | ![](assets/badges/npm-dark.svg) | ![](assets/badges/npm-light.svg) | ![](assets/badges/npm-reto-dark.svg) | ![](assets/badges/npm-reto-light.svg) |
| NuGet | ![](assets/badges/nuget.svg) | ![](assets/badges/nuget-dark.svg) | ![](assets/badges/nuget-light.svg) | ![](assets/badges/nuget-reto-dark.svg) | ![](assets/badges/nuget-reto-light.svg) |
| Cargo | ![](assets/badges/cargo.svg) | ![](assets/badges/cargo-dark.svg) | ![](assets/badges/cargo-light.svg) | ![](assets/badges/cargo-reto-dark.svg) | ![](assets/badges/cargo-reto-light.svg) |
| RubyGems | ![](assets/badges/rubygems.svg) | ![](assets/badges/rubygems-dark.svg) | ![](assets/badges/rubygems-light.svg) | ![](assets/badges/rubygems-reto-dark.svg) | ![](assets/badges/rubygems-reto-light.svg) |
| Packagist | ![](assets/badges/packagist.svg) | ![](assets/badges/packagist-dark.svg) | ![](assets/badges/packagist-light.svg) | ![](assets/badges/packagist-reto-dark.svg) | ![](assets/badges/packagist-reto-light.svg) |
| Docker | ![](assets/badges/docker.svg) | ![](assets/badges/docker-dark.svg) | ![](assets/badges/docker-light.svg) | ![](assets/badges/docker-reto-dark.svg) | ![](assets/badges/docker-reto-light.svg) |

#### Language

| Label | Color | Dark | Light | Reto Dark | Reto Light |
|---|---|---|---|---|---|
| Python | ![](assets/badges/python.svg) | ![](assets/badges/python-dark.svg) | ![](assets/badges/python-light.svg) | ![](assets/badges/python-reto-dark.svg) | ![](assets/badges/python-reto-light.svg) |
| JavaScript | ![](assets/badges/js.svg) | ![](assets/badges/js-dark.svg) | ![](assets/badges/js-light.svg) | ![](assets/badges/js-reto-dark.svg) | ![](assets/badges/js-reto-light.svg) |
| TypeScript | ![](assets/badges/ts.svg) | ![](assets/badges/ts-dark.svg) | ![](assets/badges/ts-light.svg) | ![](assets/badges/ts-reto-dark.svg) | ![](assets/badges/ts-reto-light.svg) |
| Go | ![](assets/badges/go.svg) | ![](assets/badges/go-dark.svg) | ![](assets/badges/go-light.svg) | ![](assets/badges/go-reto-dark.svg) | ![](assets/badges/go-reto-light.svg) |
| Rust | ![](assets/badges/rust.svg) | ![](assets/badges/rust-dark.svg) | ![](assets/badges/rust-light.svg) | ![](assets/badges/rust-reto-dark.svg) | ![](assets/badges/rust-reto-light.svg) |
| .NET | ![](assets/badges/dotnet.svg) | ![](assets/badges/dotnet-dark.svg) | ![](assets/badges/dotnet-light.svg) | ![](assets/badges/dotnet-reto-dark.svg) | ![](assets/badges/dotnet-reto-light.svg) |
| Ruby | ![](assets/badges/ruby.svg) | ![](assets/badges/ruby-dark.svg) | ![](assets/badges/ruby-light.svg) | ![](assets/badges/ruby-reto-dark.svg) | ![](assets/badges/ruby-reto-light.svg) |
| PHP | ![](assets/badges/php.svg) | ![](assets/badges/php-dark.svg) | ![](assets/badges/php-light.svg) | ![](assets/badges/php-reto-dark.svg) | ![](assets/badges/php-reto-light.svg) |
| C++ | ![](assets/badges/cplusplus.svg) | ![](assets/badges/cplusplus-dark.svg) | ![](assets/badges/cplusplus-light.svg) | ![](assets/badges/cplusplus-reto-dark.svg) | ![](assets/badges/cplusplus-reto-light.svg) |
| Swift | ![](assets/badges/swift.svg) | ![](assets/badges/swift-dark.svg) | ![](assets/badges/swift-light.svg) | ![](assets/badges/swift-reto-dark.svg) | ![](assets/badges/swift-reto-light.svg) |
| Kotlin | ![](assets/badges/kotlin.svg) | ![](assets/badges/kotlin-dark.svg) | ![](assets/badges/kotlin-light.svg) | ![](assets/badges/kotlin-reto-dark.svg) | ![](assets/badges/kotlin-reto-light.svg) |
| Dart | ![](assets/badges/dart.svg) | ![](assets/badges/dart-dark.svg) | ![](assets/badges/dart-light.svg) | ![](assets/badges/dart-reto-dark.svg) | ![](assets/badges/dart-reto-light.svg) |
| Perl | ![](assets/badges/perl.svg) | ![](assets/badges/perl-dark.svg) | ![](assets/badges/perl-light.svg) | ![](assets/badges/perl-reto-dark.svg) | ![](assets/badges/perl-reto-light.svg) |
| Scala | ![](assets/badges/scala.svg) | ![](assets/badges/scala-dark.svg) | ![](assets/badges/scala-light.svg) | ![](assets/badges/scala-reto-dark.svg) | ![](assets/badges/scala-reto-light.svg) |
| Haskell | ![](assets/badges/haskell.svg) | ![](assets/badges/haskell-dark.svg) | ![](assets/badges/haskell-light.svg) | ![](assets/badges/haskell-reto-dark.svg) | ![](assets/badges/haskell-reto-light.svg) |

Badge icons sourced from [Simple Icons](https://simpleicons.org) (CC0-1.0) and
[Google Material Icons](https://fonts.google.com/icons) (Apache-2.0). See
`src/repo_release_tools/tools/platform.py` for full attribution.
`Bash` and `Java` appear in both the Platform and Language label sets; they are
listed under Platform only.

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
