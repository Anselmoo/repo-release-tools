"""`rrt sync` — discover newer upstream releases for the tracked package.

Reads the current project version from the configured version group, fetches
all released versions from the configured upstream registry (PyPI, npm, NuGet,
crates.io, or Packagist), and emits those that are strictly newer than the
current version — one per line by default, or as a JSON array with ``--json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_release_tools.config import load_or_autodetect_config
from repo_release_tools.sync.providers import fetch_versions
from repo_release_tools.ui import DryRunPrinter, VerbosePrinter
from repo_release_tools.version.semver import Version, newer_versions
from repo_release_tools.version.targets import read_group_current_version

# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


def cmd_sync(args: argparse.Namespace) -> int:
    """Print upstream versions newer than the current project version."""
    p = DryRunPrinter(getattr(args, "dry_run", False), verbose=getattr(args, "verbose", 0))
    cfg = load_or_autodetect_config(Path.cwd())
    try:
        group = cfg.resolve_group(getattr(args, "group", None))
    except ValueError as exc:
        p = VerbosePrinter(verbose=getattr(args, "verbose", 0))
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    if not group.upstream_package:
        p.line("No [tool.rrt.upstream] package configured.", ok=False)
        return 1

    current: Version = read_group_current_version(group)
    raw: list[str] = fetch_versions(group.upstream_package, group.upstream_provider)

    parsed: list[Version] = []
    for v in raw:
        try:
            parsed.append(Version.parse(v))
        except ValueError:
            continue  # skip non-semver / PEP 440 pre-release tags

    fresh = newer_versions(current, parsed)

    if getattr(args, "json", False):
        sys.stdout.write(json.dumps([str(v) for v in fresh]) + "\n")
    else:
        for v in fresh:
            sys.stdout.write(str(v) + "\n")
    return 0


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

_SYNC_EXAMPLES = (
    "  $ rrt sync\n  $ rrt sync --json\n  $ rrt sync --group backend\n  $ rrt sync --dry-run"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``rrt sync`` command."""
    parser = subparsers.add_parser(
        "sync",
        help="List upstream releases newer than the current version.",
        description=(
            "Fetch all released versions of the configured upstream package and print "
            "those that are strictly newer than the current project version."
        ),
        epilog=_SYNC_EXAMPLES,
    )
    parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group name (default: first/default group).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON array of newer version strings instead of one-per-line output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without side effects (informational; sync is read-only).",
    )
    parser.set_defaults(handler=cmd_sync)


# ---------------------------------------------------------------------------
# Source-owned topic docs
# ---------------------------------------------------------------------------

_SYNC_DOC = """
## Configuration

`rrt sync` reads upstream version information using the `[tool.rrt.upstream]`
block in your project config:

```toml
[tool.rrt.upstream]
package = "my-package"
provider = "pypi"
```

`package` is the registry name of the upstream package. `provider` selects the
registry to query.

## Supported providers

| Provider | `provider` value | Notes |
|---|---|---|
| PyPI | `pypi` | Python package index; queries `/pypi/<package>/json` |
| npm | `npm` | Node package registry; queries `/package/<package>` |
| NuGet | `nuget` | .NET package registry; queries the NuGet API |
| crates.io | `crates` | Rust crate registry; requires a `User-Agent` header — handled internally |
| Packagist | `packagist` | PHP package registry; `package` must be in `vendor/name` form |

## Basic usage

```bash
# List newer versions one per line (default)
rrt sync

# Emit a JSON array of newer version strings
rrt sync --json

# Target a specific version group
rrt sync --group backend
```

## CI mirror loop

Use `rrt sync` output to drive a CI bump loop that tracks upstream releases:

```bash
for v in $(rrt sync); do
    rrt bump "$v" --no-changelog --force
done
```

This pattern is useful for mirror repositories that must stay in lock-step
with an upstream package without manual intervention.

## Hook

`rrt-sync` is published as a manual-stage pre-commit hook. Add it to your
`.pre-commit-config.yaml` to run it on demand before a release:

```yaml
repos:
  - repo: https://github.com/Anselmoo/repo-release-tools
    rev: v1.10.0
    hooks:
      - id: rrt-sync
```

```bash
pre-commit run rrt-sync --hook-stage manual
```
"""

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("sync", _SYNC_DOC),)
