"""Compute and apply CI release versions from ``[tool.rrt]`` config.

# file: ci_version.py

## Overview

The ``rrt ci-version`` command family centralizes deterministic version
computation and safe application for CI and release automation. It reads the
repository's ``[tool.rrt]`` configuration, discovers version targets and group
defaults, and uses the current CI environment (or explicit CLI overrides) to
produce machine-friendly version identifiers suitable for downstream CI
targets and release workflows.

Subcommands:

- ``compute`` — deterministically compute the version for this run and emit a
    single raw line for scripting and capture.
- ``apply`` — update configured targets that declare a ``ci_format``,
    transforming values when needed (for example converting PEP 440 dev
    releases into Cargo-compatible prerelease identifiers).
- ``sync`` — compute then apply the published version in one operation; both
    ``apply`` and ``sync`` support ``--dry-run`` for safe previews.

Version rules (summary):

- Tag builds (``refs/tags/v*``) yield the tag name with the leading ``v``
    removed.
- Mainline (`refs/heads/main`) builds produce a PEP 440 dev release using
    ``{base}.dev{GITHUB_RUN_ID}{GITHUB_RUN_ATTEMPT:02d}``.
- Other refs return the configured base version unchanged. CLI flags such as
    ``--ref``, ``--run-id``, or ``--base`` override environment-derived values.

Output formats & safety:

- Supported target formats: ``pep440`` and ``semver_pre`` (the latter maps
    PEP 440 dev suffixes to SemVer prerelease tokens).
- The command validates conversions and fails fast on incompatible inputs to
    avoid writing invalid CI data.
- ``compute`` is machine-friendly (single-line stdout); ``apply``/``sync`` are
    human-friendly with progress, dry-run previews, and explicit error messages.

Examples::

        rrt ci-version compute
        rrt ci-version apply 1.2.3.dev42 --group backend --dry-run

"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.commands._version_render import render_version_write_events
from repo_release_tools.config import (
    VALID_CI_FORMATS,
    find_repo_root,
    format_autodetected_config_notice,
    format_missing_tool_rrt_guidance,
    is_missing_tool_rrt_error,
    iter_config_files,
    load_or_autodetect_config,
)
from repo_release_tools.ui import (
    GLYPHS,
    DryRunPrinter,
    ProgressLine,
    VerbosePrinter,
    rule,
    subtle,
    terminal_width,
)
from repo_release_tools.version.targets import (
    check_autodetected_version_consistency,
    read_group_current_version,
    replace_version_in_file,
)

# Regex that matches the PEP 440 dev-release suffix so it can be converted
# to a Cargo-compatible SemVer prerelease identifier.
_SEMVER_DEV_RE = re.compile(r"\.dev(?P<build>\d+)$")


# ---------------------------------------------------------------------------
# GitHub Actions context
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GitHubContext:
    """GitHub Actions environment variables needed for version computation."""

    ref: str
    ref_name: str
    run_id: str
    run_attempt: str

    @classmethod
    def from_env(cls) -> GitHubContext:
        """Build a context object from the current process environment."""
        return cls(
            ref=os.environ.get("GITHUB_REF", ""),
            ref_name=os.environ.get("GITHUB_REF_NAME", ""),
            run_id=os.environ.get("GITHUB_RUN_ID", "0"),
            run_attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        )


# ---------------------------------------------------------------------------
# Pure version helpers
# ---------------------------------------------------------------------------


def to_semver(version: str) -> str:
    """Convert a PEP 440 dev-release string to a Cargo-compatible SemVer prerelease.

    ``0.2.0.dev12345601`` → ``0.2.0-dev.12345601``

    Release versions (no ``.dev`` suffix) are returned unchanged.
    """
    return _SEMVER_DEV_RE.sub(r"-dev.\g<build>", version)


def compute_published_version(base_version: str, context: GitHubContext) -> str:
    """Compute the published version for the current GitHub Actions run.

    * Tag builds (``refs/tags/v*``): tag name without ``v`` prefix.
    * ``refs/heads/main``: ``{base}.dev{run_id}{attempt:02d}`` (PEP 440).
    * All other refs: *base_version* unchanged.
    """
    if context.ref.startswith("refs/tags/v"):
        # Prefer ref_name when available, but fall back to the last path
        # component of ref (e.g. "refs/tags/v1.2.3" → "v1.2.3") so that
        # --ref can be used independently of --ref-name.
        tag_source = context.ref_name or context.ref.rsplit("/", 1)[-1]
        tag_version = tag_source.removeprefix("v")
        return tag_version or base_version

    if context.ref == "refs/heads/main":
        try:
            attempt = int(context.run_attempt)
        except ValueError as exc:
            raise ValueError(
                f"Invalid GitHub run attempt value {context.run_attempt!r}; "
                "GITHUB_RUN_ATTEMPT/--run-attempt must be an integer.",
            ) from exc
        return f"{base_version}.dev{context.run_id}{attempt:02d}"

    return base_version


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _context_from_args(args: argparse.Namespace) -> GitHubContext:
    """Build a :class:`GitHubContext` merging CLI flags over env variables."""
    env = GitHubContext.from_env()
    return GitHubContext(
        ref=getattr(args, "ref", None) or env.ref,
        ref_name=getattr(args, "ref_name", None) or env.ref_name,
        run_id=getattr(args, "run_id", None) or env.run_id,
        run_attempt=getattr(args, "run_attempt", None) or env.run_attempt,
    )


def _resolve_base(args: argparse.Namespace, root: Path) -> str | None:
    """Return the base version string from ``--base`` or the first version target."""
    if args.base:
        return args.base
    try:
        config = load_or_autodetect_config(root)
        if config.autodetected:
            p = VerbosePrinter()
            p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
            if mismatch := check_autodetected_version_consistency(config):
                p.line(mismatch, ok=False, stream=sys.stderr)
                return None
        group = config.resolve_group(getattr(args, "group", None))
        return str(read_group_current_version(group))
    except FileNotFoundError:
        p = VerbosePrinter()
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.action(format_missing_tool_rrt_guidance(root, []), stream=sys.stderr)
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = VerbosePrinter()
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                stream=sys.stderr,
            )
            return None
        p = VerbosePrinter()
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None
    except RuntimeError as exc:
        p = VerbosePrinter()
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_ci_version_compute(args: argparse.Namespace) -> int:
    """Compute and print the published version for the current GitHub Actions run.

    Outputs a single version string on stdout so the result can be captured
    in shell scripts, e.g.::

        VERSION=$(rrt ci-version compute)
    """
    verbose: int = getattr(args, "verbose", 0) or 0

    root = find_repo_root(Path.cwd())
    base = _resolve_base(args, root)
    if base is None:
        return 1

    context = _context_from_args(args)
    try:
        version = compute_published_version(base, context)
    except ValueError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    # Machine-readable output: keep raw version on stdout
    sys.stdout.write(version + "\n")
    return 0


def cmd_ci_version_apply(args: argparse.Namespace) -> int:
    """Apply an explicit version string to all ``ci_format``-configured targets.

    Python targets (``ci_format = "pep440"``) receive the version as-is.
    Cargo / TOML targets (``ci_format = "semver_pre"``) receive the version
    after conversion via :func:`to_semver`.
    """
    verbose: int = getattr(args, "verbose", 0) or 0
    root = find_repo_root(Path.cwd())

    try:
        config = load_or_autodetect_config(root)
        if config.autodetected:
            p = VerbosePrinter(verbose=verbose)
            p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
        group = config.resolve_group(getattr(args, "group", None))
    except FileNotFoundError:
        p = VerbosePrinter(verbose=verbose)
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.action(format_missing_tool_rrt_guidance(root, []), stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = VerbosePrinter(verbose=verbose)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)),
                stream=sys.stderr,
            )
            return 1
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    ci_targets = [t for t in group.version_targets if t.ci_format in VALID_CI_FORMATS]
    if not ci_targets:
        p = VerbosePrinter(verbose=verbose)
        p.line(
            "No version targets with ci_format configured. "
            'Add ci_format = "pep440" or ci_format = "semver_pre" to the selected version group.',
            ok=False,
            stream=sys.stderr,
        )
        return 1

    version: str = args.version

    progress = ProgressLine(file=sys.stdout)
    p = DryRunPrinter(args.dry_run, verbose=verbose)
    p.line(rule("Applying CI versions", width=terminal_width()))
    total = len(ci_targets)
    for i, target in enumerate(ci_targets, 1):
        if target.ci_format == "semver_pre":
            version_str = to_semver(version)
            # If the version contains a PEP 440 dev marker but to_semver() made
            # no change, the suffix pattern was not a plain `.devN`. Fail fast
            # rather than writing an invalid Cargo SemVer string.
            if version_str == version and ".dev" in version:
                progress.clear()
                p_err = VerbosePrinter(verbose=verbose)
                p_err.line(
                    f"Cannot convert {version!r} to a Cargo-compatible SemVer prerelease. "
                    "Only versions ending in '.dev<digits>' are supported (e.g. 0.2.0.dev42).",
                    ok=False,
                    stream=sys.stderr,
                )
                return 1
        else:
            version_str = version
        if total > 1 and i > 1:
            progress.clear()
        try:
            event = replace_version_in_file(target, version_str, dry_run=args.dry_run)
            render_version_write_events([event])
        except (FileNotFoundError, RuntimeError) as exc:
            progress.clear()
            p = VerbosePrinter(verbose=verbose)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1
        if total > 1:
            progress.update_bar(i / total)

    progress.clear()
    p.blank_line()
    if args.dry_run:
        p.line(
            subtle(
                f"{GLYPHS.bullet.skip} [dry-run] complete {GLYPHS.typography.mdash} no files were modified",
            ),
        )
    else:
        p.ok("Done.")
    return 0


def cmd_ci_version_sync(args: argparse.Namespace) -> int:
    """Compute the published version from GitHub Actions env and apply it.

    Equivalent to running ``compute`` followed by ``apply`` with the result.
    """
    verbose: int = getattr(args, "verbose", 0) or 0

    root = find_repo_root(Path.cwd())
    base = _resolve_base(args, root)
    if base is None:
        return 1

    context = _context_from_args(args)
    try:
        version = compute_published_version(base, context)
    except ValueError as exc:
        p = VerbosePrinter(verbose=verbose)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    p = VerbosePrinter(verbose=verbose)
    p.action(f"Applying published version: {version}")

    apply_args = argparse.Namespace(
        version=version,
        dry_run=args.dry_run,
        group=getattr(args, "group", None),
    )
    return cmd_ci_version_apply(apply_args)


CI_VERSION_EXAMPLES = (
    "  $ rrt ci-version compute\n  $ rrt ci-version apply 1.2.3.dev4\n  $ rrt ci-version sync"
)

CI_VERSION_COMPUTE_EXAMPLES = (
    "  $ rrt ci-version compute\n"
    "  $ rrt ci-version compute --base 1.2.3 --ref refs/heads/main --run-id 42 --run-attempt 3"
)

CI_VERSION_APPLY_EXAMPLES = (
    "  $ rrt ci-version apply 1.2.3.dev4201\n"
    "  $ rrt ci-version apply 1.2.3.dev4201 --group backend --dry-run"
)

CI_VERSION_SYNC_EXAMPLES = (
    "  $ rrt ci-version sync --dry-run\n"
    "  $ rrt ci-version sync --group backend --ref refs/heads/main --run-id 42 --run-attempt 1"
)


# ---------------------------------------------------------------------------
# CLI registration
# ---------------------------------------------------------------------------


def _add_compute_args(parser: argparse.ArgumentParser) -> None:
    """Add version-computation flags shared by ``compute`` and ``sync``."""
    parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to read/apply when multiple release groups are configured.",
    )
    parser.add_argument(
        "--base",
        default=None,
        metavar="VERSION",
        help="Base version to compute from (default: read from first configured version target).",
    )
    parser.add_argument(
        "--ref",
        default=None,
        metavar="REF",
        dest="ref",
        help="Git ref override (default: $GITHUB_REF).",
    )
    parser.add_argument(
        "--ref-name",
        default=None,
        metavar="NAME",
        dest="ref_name",
        help="Git ref-name override (default: $GITHUB_REF_NAME).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        dest="run_id",
        help="GitHub Actions run ID override (default: $GITHUB_RUN_ID).",
    )
    parser.add_argument(
        "--run-attempt",
        default=None,
        metavar="N",
        dest="run_attempt",
        help="GitHub Actions run-attempt override (default: $GITHUB_RUN_ATTEMPT).",
    )


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``ci-version`` command and its subcommands."""
    parser = subparsers.add_parser(
        "ci-version",
        help="Compute and apply CI pre-release versions (PEP 440 / SemVer).",
        description="Compute and apply CI pre-release versions (PEP 440 / SemVer).",
        epilog=CI_VERSION_EXAMPLES,
    )
    sub = parser.add_subparsers(
        dest="ci_version_cmd",
        metavar="<ci_version_cmd>",
        parser_class=type(parser),
        required=True,
    )

    # compute ----------------------------------------------------------------
    compute_parser = sub.add_parser(
        "compute",
        help="Print the published version for the current GitHub Actions run.",
        description="Print the CI/published version for the current GitHub Actions context, using --base and --group overrides when provided.",
        epilog=CI_VERSION_COMPUTE_EXAMPLES,
    )
    _add_compute_args(compute_parser)
    compute_parser.set_defaults(handler=cmd_ci_version_compute)

    # apply ------------------------------------------------------------------
    apply_parser = sub.add_parser(
        "apply",
        help="Apply a concrete version string to all ci_format-configured targets.",
        description="Apply one explicit CI version string to every configured ci_format target in the selected version group.",
        epilog=CI_VERSION_APPLY_EXAMPLES,
    )
    apply_parser.add_argument(
        "version",
        help="Version string to apply (e.g. 0.2.0.dev12345601).",
    )
    apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing changes.",
    )
    apply_parser.add_argument(
        "--group",
        default=None,
        metavar="GROUP",
        help="Version group to update when multiple release groups are configured.",
    )
    apply_parser.set_defaults(handler=cmd_ci_version_apply)

    # sync -------------------------------------------------------------------
    sync_parser = sub.add_parser(
        "sync",
        help="Compute the published version from GitHub Actions env and apply it.",
        description="Compute the current GitHub Actions CI version and apply it to every configured ci_format target.",
        epilog=CI_VERSION_SYNC_EXAMPLES,
    )
    _add_compute_args(sync_parser)
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing changes.",
    )
    sync_parser.set_defaults(handler=cmd_ci_version_sync)
