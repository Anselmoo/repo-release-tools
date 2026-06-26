"""`rrt sync` — discover newer upstream releases for the tracked package.

Reads the current project version from the configured version group, fetches
all released versions from the configured upstream registry (PyPI, npm, NuGet,
crates.io, or Packagist), and emits those that are strictly newer than the
current version — one per line by default, or as a JSON array with ``--json``.

When ``--bump`` is given the command shifts from list-only to mirror-orchestration
mode: for every newer version (ascending) it applies version targets, optionally
commits the result, and optionally creates an annotated tag.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repo_release_tools.commands.bump import apply_version
from repo_release_tools.commands.tag import cmd_tag_create
from repo_release_tools.config import load_or_autodetect_config
from repo_release_tools.sync.providers import fetch_versions
from repo_release_tools.ui import (
    DryRunPrinter,
    VerbosePrinter,
    info,
    rule,
    subtle,
    success,
    terminal_width,
)
from repo_release_tools.version.semver import Version, newer_versions
from repo_release_tools.version.targets import read_group_current_version
from repo_release_tools.workflow import git

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stage_and_commit(
    root: Path,
    changed: list[Path],
    message: str,
    *,
    dry_run: bool,
) -> None:
    """Stage *changed* files relative to *root* and create a git commit.

    Reuses the same ``workflow.git.run`` path as ``cmd_bump`` (the
    ``if not args.no_commit:`` block in bump.py around line 520-526).
    """
    rel_files = [str(p.relative_to(root)) for p in dict.fromkeys(changed)]
    git.run(
        ["git", "add", *rel_files],
        root,
        dry_run=dry_run,
        label="git add",
    )
    git.run(
        ["git", "commit", "-m", message],
        root,
        dry_run=dry_run,
        label="git commit",
    )


# ---------------------------------------------------------------------------
# Command handler
# ---------------------------------------------------------------------------


def cmd_sync(args: argparse.Namespace) -> int:
    """Print upstream versions newer than the current project version.

    With ``--bump``: apply each newer version to the configured targets in
    ascending order, then optionally commit and tag.
    """
    dry_run: bool = getattr(args, "dry_run", False)
    p = DryRunPrinter(dry_run, verbose=getattr(args, "verbose", 0))
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

    do_bump: bool = getattr(args, "bump", False)
    do_commit: bool = getattr(args, "commit", False)
    do_tag: bool = getattr(args, "tag", False)
    commit_message_tmpl: str | None = getattr(args, "commit_message", None)

    # ── List-only mode (no --bump) ──────────────────────────────────────────
    if not do_bump:
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps([str(v) for v in fresh]) + "\n")
        else:
            for v in fresh:
                sys.stdout.write(str(v) + "\n")
        return 0

    # ── Mirror-orchestration mode (--bump) ──────────────────────────────────
    root = cfg.root
    tmpl = commit_message_tmpl or group.upstream_commit_message

    if dry_run:
        # ── Dry-run: print plan, write/commit/tag nothing ──────────────────
        sys.stdout.write(
            success(
                f"✓ [DRY RUN] Mirror upstream {group.upstream_package} ({group.upstream_provider})"
            )
            + "\n"
        )
        sys.stdout.write(info(f"→ Current: {current}") + "\n")
        sys.stdout.write("\n")
        sys.stdout.write(rule("Plan", width=terminal_width()) + "\n")

        if not fresh:
            sys.stdout.write(subtle("⊙ [dry-run] No newer versions — nothing to do.") + "\n")
        else:
            for v in fresh:
                # Compute changed paths without writing (dry_run=True)
                changed = apply_version(group, str(v), cfg, dry_run=True)
                file_names = ", ".join(p.name for p in dict.fromkeys(changed))
                sys.stdout.write(
                    subtle(f"⊙ [dry-run] Would bump → {v} (files: {file_names})") + "\n"
                )
                if do_commit:
                    msg = tmpl.format(version=v)
                    sys.stdout.write(subtle(f'⊙ [dry-run] Would commit: "{msg}"') + "\n")
                if do_tag:
                    sys.stdout.write(subtle(f"⊙ [dry-run] Would tag: v{v}") + "\n")

        sys.stdout.write("\n")
        sys.stdout.write(subtle("⊙ [dry-run] complete – no changes made") + "\n")
        return 0

    # ── Live mode: apply each version in ascending order ───────────────────
    if not fresh:
        return 0  # no-op — exit 0 as specified

    for v in fresh:
        # 1. Apply version targets + pin targets.
        changed = apply_version(group, str(v), cfg, dry_run=False)

        # 2. Optional commit.
        if do_commit:
            msg = tmpl.format(version=v)
            _stage_and_commit(root, changed, msg, dry_run=False)

        # 3. Optional tag (after commit so it lands on the right SHA).
        if do_tag:
            tag_ns = argparse.Namespace(
                dry_run=False,
                push=False,
                prefix="v",
                message=None,
                force=False,
                group=getattr(args, "group", None),
                verbose=getattr(args, "verbose", 0),
            )
            rc = cmd_tag_create(tag_ns)
            if rc != 0:
                return rc

    return 0


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------

_SYNC_EXAMPLES = (
    "  $ rrt sync\n"
    "  $ rrt sync --json\n"
    "  $ rrt sync --group backend\n"
    "  $ rrt sync --bump\n"
    "  $ rrt sync --bump --commit --tag\n"
    "  $ rrt sync --bump --commit --commit-message 'chore: mirror {version}' --dry-run"
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``rrt sync`` command."""
    parser = subparsers.add_parser(
        "sync",
        help="List upstream releases newer than the current version.",
        description=(
            "Fetch all released versions of the configured upstream package and print "
            "those that are strictly newer than the current project version.  "
            "With --bump, apply each newer version in ascending order, "
            "optionally committing and tagging each one."
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
        help="Preview without side effects.",
    )

    # ── Mirror-orchestration flags ──────────────────────────────────────────
    mirror_grp = parser.add_argument_group("Mirror orchestration")
    mirror_grp.add_argument(
        "--bump",
        action="store_true",
        help=(
            "Apply each newer version to version_targets + pin_targets in ascending order.  "
            "Without this flag the command lists newer versions only."
        ),
    )
    mirror_grp.add_argument(
        "--commit",
        action="store_true",
        help="After each version's apply, stage changed files and create a git commit.",
    )
    mirror_grp.add_argument(
        "--tag",
        action="store_true",
        help="After each version's apply (and optional commit), create an annotated git tag.",
    )
    mirror_grp.add_argument(
        "--commit-message",
        default=None,
        metavar="TMPL",
        help=(
            "Override the commit message template.  "
            "Use {version} as a placeholder (e.g. 'chore: mirror {version}').  "
            "Defaults to group.upstream_commit_message ('Mirror: {version}')."
        ),
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
commit_message = "Mirror: {version}"
```

`package` is the registry name of the upstream package. `provider` selects the
registry to query.  `commit_message` is a Python format string; `{version}` is
replaced with the new version string and used as the git commit message when
``--commit`` is given.

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

## Mirror-orchestration mode

```bash
# Apply every newer version to version targets (no git side-effects)
rrt sync --bump

# Apply + commit each version with the default message "Mirror: <version>"
rrt sync --bump --commit

# Apply + commit + annotated tag per version
rrt sync --bump --commit --tag

# Preview the plan without touching anything
rrt sync --bump --commit --tag --dry-run

# Custom commit message template
rrt sync --bump --commit --commit-message "chore: mirror {version}"
```

## CI mirror loop

Use `rrt sync` output to drive a CI bump loop that tracks upstream releases:

```bash
for v in $(rrt sync); do
    rrt bump "$v" --no-changelog --force
done
```

Or let `rrt sync --bump --commit --tag` handle the full loop in a single call.

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
