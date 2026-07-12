---
title: "rrt init"
permalink: "/commands/init/"
---
<!-- rrt:auto:start:page-header -->
<p><a href="https://github.com/Anselmoo/repo-release-tools"><picture>
  <source media="(prefers-color-scheme: dark)" srcset="/repo-release-tools/assets/badges/github-reto-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="/repo-release-tools/assets/badges/github-reto-light.svg">
  <img alt="GitHub" src="/repo-release-tools/assets/badges/github-reto-dark.svg">
</picture></a></p>
<!-- rrt:auto:end:page-header -->


# rrt init

Bootstrap rrt configuration in a new or existing repository.

## Overview

`rrt init` creates or extends a `pyproject.toml` (or `.rrt.toml`) with a
minimal `[tool.rrt]` skeleton so that `rrt bump`, `rrt branch`, and the hooks
can work immediately without manual config editing.

> **Note:** This page is a stub. Run `rrt init --help` or see the generated
> [CLI reference](rrt-cli.md) for the authoritative command reference.

## Basic usage

```bash
rrt init
rrt init --dry-run
```

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [pre-commit / lefthook](hooks.md)

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://anselmoo.github.io/repo-release-tools/) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
