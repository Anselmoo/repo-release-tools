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
