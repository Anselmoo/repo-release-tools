# rrt config

Inspect and validate the resolved rrt configuration.

## Overview

`rrt config` loads the active rrt configuration and displays it in a
human-readable format. Use it to confirm that auto-detection found the right
file or that an explicit `[tool.rrt]` section was parsed as expected.

> **Note:** This page is a stub. Run `rrt config --help` or see the generated
> [CLI reference](rrt-cli.md) for the authoritative command reference.

## Basic usage

```bash
rrt config
rrt config --format toml
```

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [Config health checks](doctor.md)
