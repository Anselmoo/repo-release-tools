---
title: "rrt install"
permalink: "/commands/install/"
---

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
