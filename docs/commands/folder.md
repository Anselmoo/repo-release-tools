---
title: "rrt folder"
permalink: "/commands/folder/"
---

# rrt folder

Supervise and scaffold repository folder structures with reusable templates.

## Overview

`rrt folder` adds a language-agnostic structure workflow to `repo-release-tools`.
Use it to validate an existing layout, scaffold a starter structure from built-in
templates, or capture a loose template from a repository that already has the
shape you want.

The built-in catalog includes stricter layouts such as `python-package`,
`javascript-package`, `go-module`, and `cargo-inspired`, plus looser starter
profiles for teams that want guidance without rigid exact-match enforcement.

> **Note:** This page is a stub. Run `rrt folder --help` or see the generated
> [CLI reference](rrt-cli.md) for the authoritative command reference.

## Basic usage

```bash
rrt folder check --template python-package
rrt folder scaffold --template docs-only --dry-run
rrt folder design --name captured-template --root .
```

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [Project tree](tree.md)
- [Config health checks](doctor.md)

<!-- rrt:auto:start:doc-footer -->
---

[↑ Docs index](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/index.md) · [CLI reference](https://github.com/Anselmoo/repo-release-tools/blob/main/docs/commands/rrt-cli.md) · [Changelog](https://github.com/Anselmoo/repo-release-tools/blob/main/CHANGELOG.md) · [GitHub](https://github.com/Anselmoo/repo-release-tools)
<!-- rrt:auto:end:doc-footer -->
