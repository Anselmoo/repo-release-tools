# rrt bump

Bump the version of the repository according to the configured version targets.

## Overview

`rrt bump` applies a semver increment (`major`, `minor`, `patch`) to all
configured version targets, optionally updates the changelog, and optionally
creates a release branch.

> **Note:** This page is a stub. Run `rrt bump --help` or see the generated
> [CLI reference](rrt-cli.md) for the authoritative command reference.

## Basic usage

```bash
rrt bump patch
rrt bump minor
rrt bump major
rrt bump patch --dry-run
```

## Related docs

- [Generated CLI reference](rrt-cli.md)
- [Config health checks](doctor.md)
