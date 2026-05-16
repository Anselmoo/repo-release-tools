---
title: "rrt install"
permalink: "/commands/install/"
---
<!-- rrt:auto:start:page-header -->
[![GitHub](../assets/badges/github.svg)](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:page-header -->

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->


# rrt install

Install bundled rrt user workflow surfaces from one unified entrypoint.

## Overview

`rrt install` wraps the existing surface installers:

- `rrt skill install`
- `rrt agents install`
- `rrt hooks install`

By default it installs all three surfaces. Use `--surface` to limit the scope.

## Examples

```bash
rrt install --target claude-local
rrt install --surface skill --target copilot-local
rrt install --surface agents --surface hooks --target codex-global --dry-run
```
