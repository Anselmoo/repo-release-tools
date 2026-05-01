"""CI version computation and application command.

Mirrors the behaviour of the ``scripts/ci_version.py`` helper used by
``copilot-plugin-manager``, but driven by ``[tool.rrt]`` configuration
rather than hard-coded file paths.

Version semantics
-----------------
* **Tag builds** (``refs/tags/v*``): the tag name with the ``v`` prefix
  stripped is used as-is.
* **Main branch** (``refs/heads/main``): a PEP 440 dev release is computed
  as ``{base}.dev{GITHUB_RUN_ID}{GITHUB_RUN_ATTEMPT:02d}``.
* **All other refs**: the base version is returned unchanged.

When applying a version the output format depends on the ``ci_format``
field on each ``[[tool.rrt.version_targets]]`` entry:

* ``"pep440"``    – version string applied unchanged (``0.2.0.dev12345601``).
* ``"semver_pre"`` – version converted via :func:`to_semver` before writing
  (``0.2.0-dev.12345601``).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.config import (
    VALID_CI_FORMATS,
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
    rule,
    subtle,
    terminal_width,
)
from repo_release_tools.version_targets import (
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
    def from_env(cls) -> "GitHubContext":
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
                "GITHUB_RUN_ATTEMPT/--run-attempt must be an integer."
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
            p = DryRunPrinter(dry_run=False)
            p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
            if mismatch := check_autodetected_version_consistency(config):
                p.line(mismatch, ok=False, stream=sys.stderr)
                return None
        group = config.resolve_group(getattr(args, "group", None))
        return str(read_group_current_version(group))
    except FileNotFoundError:
        p = DryRunPrinter(dry_run=False)
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.action(format_missing_tool_rrt_guidance(root, []), stream=sys.stderr)
        return None
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(dry_run=False)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)), stream=sys.stderr
            )
            return None
        p = DryRunPrinter(dry_run=False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return None
    except RuntimeError as exc:
        p = DryRunPrinter(dry_run=False)
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
    root = Path.cwd()
    base = _resolve_base(args, root)
    if base is None:
        return 1

    context = _context_from_args(args)
    try:
        version = compute_published_version(base, context)
    except ValueError as exc:
        p = DryRunPrinter(dry_run=False)
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
    root = Path.cwd()

    try:
        config = load_or_autodetect_config(root)
        if config.autodetected:
            p = DryRunPrinter(dry_run=False)
            p.line(format_autodetected_config_notice(config), ok=False, stream=sys.stderr)
        group = config.resolve_group(getattr(args, "group", None))
    except FileNotFoundError:
        p = DryRunPrinter(dry_run=False)
        p.line("No supported rrt config file found.", ok=False, stream=sys.stderr)
        p.action(format_missing_tool_rrt_guidance(root, []), stream=sys.stderr)
        return 1
    except ValueError as exc:
        if is_missing_tool_rrt_error(exc):
            p = DryRunPrinter(dry_run=False)
            p.line("No [tool.rrt] configuration found.", ok=False, stream=sys.stderr)
            p.action(
                format_missing_tool_rrt_guidance(root, iter_config_files(root)), stream=sys.stderr
            )
            return 1
        p = DryRunPrinter(dry_run=False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    except RuntimeError as exc:
        p = DryRunPrinter(dry_run=False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    ci_targets = [t for t in group.version_targets if t.ci_format in VALID_CI_FORMATS]
    if not ci_targets:
        p = DryRunPrinter(False)
        p.line(
            "No version targets with ci_format configured. "
            'Add ci_format = "pep440" or ci_format = "semver_pre" to the selected version group.',
            ok=False,
            stream=sys.stderr,
        )
        return 1

    version: str = args.version

    progress = ProgressLine(file=sys.stdout)
    p = DryRunPrinter(args.dry_run)
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
                p_err = DryRunPrinter(False)
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
            replace_version_in_file(target, version_str, dry_run=args.dry_run)
        except (FileNotFoundError, RuntimeError) as exc:
            progress.clear()
            p = DryRunPrinter(False)
            p.line(str(exc), ok=False, stream=sys.stderr)
            return 1
        if total > 1:
            progress.update_bar(i / total)

    progress.clear()
    p.blank_line()
    if args.dry_run:
        p.line(
            subtle(
                f"{GLYPHS.bullet.skip} [dry-run] complete {GLYPHS.typography.mdash} no files were modified"
            )
        )
    else:
        p.ok("Done.")
    return 0


def cmd_ci_version_sync(args: argparse.Namespace) -> int:
    """Compute the published version from GitHub Actions env and apply it.

    Equivalent to running ``compute`` followed by ``apply`` with the result.
    """
    root = Path.cwd()
    base = _resolve_base(args, root)
    if base is None:
        return 1

    context = _context_from_args(args)
    try:
        version = compute_published_version(base, context)
    except ValueError as exc:
        p = DryRunPrinter(False)
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1
    p = DryRunPrinter(False)
    p.action(f"Applying published version: {version}")

    apply_args = argparse.Namespace(
        version=version, dry_run=args.dry_run, group=getattr(args, "group", None)
    )
    return cmd_ci_version_apply(apply_args)


CI_VERSION_EXAMPLES = (
    "  $ rrt ci-version compute\n  $ rrt ci-version apply 1.2.3.dev4\n  $ rrt ci-version sync"
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
    )
    _add_compute_args(compute_parser)
    compute_parser.set_defaults(handler=cmd_ci_version_compute)

    # apply ------------------------------------------------------------------
    apply_parser = sub.add_parser(
        "apply",
        help="Apply a concrete version string to all ci_format-configured targets.",
    )
    apply_parser.add_argument(
        "version",
        help="Version string to apply (e.g. 0.2.0.dev12345601).",
    )
    apply_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing changes."
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
    )
    _add_compute_args(sync_parser)
    sync_parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing changes."
    )
    sync_parser.set_defaults(handler=cmd_ci_version_sync)
