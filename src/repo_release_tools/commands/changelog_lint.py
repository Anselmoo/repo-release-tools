"""Lint changelog entries for style consistency.

`rrt changelog lint` validates entries in the ``[Unreleased]`` section (or a
named release) of the configured changelog file.

## Rules

The following rules are applied to each entry bullet by default:

- **sentence-case**: Entry must start with an uppercase letter.
- **no-trailing-period**: Entry must not end with a period.
- **max-length**: Entry must not exceed the configured character limit
  (default 120).
- **no-duplicates**: No two entries in the same section may be identical
  after normalisation (case-fold + strip).

## Configuration

All rules can be disabled or tuned in ``[tool.rrt.changelog_lint]``:

```toml
[tool.rrt.changelog_lint]
sentence_case = true        # default true
no_trailing_period = true   # default true
max_length = 120            # default 120 (0 = disabled)
no_duplicates = true        # default true
```

## Examples

```bash
rrt changelog lint
rrt changelog lint --release v1.3.0
rrt changelog lint --no-fail
```
"""

from __future__ import annotations

import argparse
import re as _re
import sys
from dataclasses import dataclass
from pathlib import Path

from repo_release_tools.changelog import (
    ChangelogFormat,
    detect_changelog_format,
    get_unreleased_section_body,
)
from repo_release_tools.config import RrtConfig, VersionGroup, load_or_autodetect_config
from repo_release_tools.ui import error, success, warning


@dataclass(frozen=True)
class LintConfig:
    """Per-project linting rule configuration."""

    sentence_case: bool = True
    no_trailing_period: bool = True
    max_length: int = 120
    no_duplicates: bool = True


@dataclass
class LintViolation:
    """A single lint violation."""

    rule: str
    entry: str
    detail: str


_BULLET_RE = _re.compile(r"^[-*]\s+(.+)$", _re.MULTILINE)


def _extract_bullets(section_body: str) -> list[str]:
    """Return all bullet text (without leading ``- `` marker) from *section_body*."""
    return [m.group(1).rstrip() for m in _BULLET_RE.finditer(section_body)]


def _lint_entry(entry: str, cfg: LintConfig) -> list[LintViolation]:
    """Run all enabled rules against a single *entry* string."""
    violations: list[LintViolation] = []
    if cfg.sentence_case and entry and not entry[0].isupper():
        violations.append(
            LintViolation(
                rule="sentence-case",
                entry=entry,
                detail=f"Entry must start with an uppercase letter: {entry!r}",
            )
        )
    if cfg.no_trailing_period and entry.endswith("."):
        violations.append(
            LintViolation(
                rule="no-trailing-period",
                entry=entry,
                detail=f"Entry must not end with a period: {entry!r}",
            )
        )
    if cfg.max_length > 0 and len(entry) > cfg.max_length:
        violations.append(
            LintViolation(
                rule="max-length",
                entry=entry,
                detail=(
                    f"Entry exceeds {cfg.max_length} characters ({len(entry)} chars): {entry!r}"
                ),
            )
        )
    return violations


def lint_entries(entries: list[str], cfg: LintConfig) -> list[LintViolation]:
    """Run all rules against *entries* and return every violation."""
    violations: list[LintViolation] = []
    for entry in entries:
        violations.extend(_lint_entry(entry, cfg))

    if cfg.no_duplicates:
        seen: set[str] = set()
        for entry in entries:
            normalized = entry.casefold().strip()
            if normalized in seen:
                violations.append(
                    LintViolation(
                        rule="no-duplicates",
                        entry=entry,
                        detail=f"Duplicate entry: {entry!r}",
                    )
                )
            seen.add(normalized)

    return violations


def _extract_release_section(content: str, version: str, fmt: ChangelogFormat) -> str | None:
    """Extract section body for a named *version* release (reuses changelog_compare logic)."""
    from repo_release_tools.commands.changelog_compare import _extract_section_text

    return _extract_section_text(content, version, fmt)


def cmd_changelog_lint(args: argparse.Namespace) -> int:
    """Lint changelog entries for style consistency."""
    root = Path.cwd()
    try:
        config: RrtConfig = load_or_autodetect_config(root)
    except Exception as exc:
        sys.stderr.write(error(f"Could not load rrt config: {exc}") + "\n")
        return 1

    group_name: str | None = getattr(args, "group", None)
    try:
        group: VersionGroup = config.resolve_group(group_name)
    except Exception as exc:
        sys.stderr.write(error(str(exc)) + "\n")
        return 1

    changelog_path = group.changelog_file
    if not changelog_path.exists():
        sys.stderr.write(error(f"Changelog not found: {changelog_path}") + "\n")
        return 1

    content = changelog_path.read_text(encoding="utf-8")
    fmt = detect_changelog_format(changelog_path)

    release: str | None = getattr(args, "release", None)
    if release:
        section_body = _extract_release_section(content, release, fmt)
        if section_body is None:
            sys.stderr.write(error(f"Release {release!r} not found in {changelog_path}") + "\n")
            return 1
    else:
        section_body = get_unreleased_section_body(content, fmt=fmt)
        if not section_body:
            sys.stdout.write(success("No [Unreleased] entries to lint.") + "\n")
            return 0

    lint_cfg = _load_lint_config(config)
    entries = _extract_bullets(section_body)
    violations = lint_entries(entries, lint_cfg)

    if not violations:
        sys.stdout.write(
            success(f"All {len(entries)} changelog entries passed lint checks.") + "\n"
        )
        return 0

    for v in violations:
        sys.stderr.write(warning(f"[{v.rule}] {v.detail}") + "\n")

    no_fail: bool = getattr(args, "no_fail", False)
    if no_fail:
        sys.stdout.write(
            warning(f"{len(violations)} lint violation(s) found (--no-fail: not failing).") + "\n"
        )
        return 0

    sys.stderr.write(
        error(f"{len(violations)} changelog lint violation(s). Fix entries or use --no-fail.")
        + "\n"
    )
    return 1


def _load_lint_config(config: RrtConfig) -> LintConfig:
    """Read ``[tool.rrt.changelog_lint]`` settings from the resolved config."""
    raw = getattr(config, "extra", None)
    lint_raw = raw.get("changelog_lint", {}) if isinstance(raw, dict) else {}
    if not isinstance(lint_raw, dict):
        lint_raw = {}
    return LintConfig(
        sentence_case=bool(lint_raw.get("sentence_case", True)),
        no_trailing_period=bool(lint_raw.get("no_trailing_period", True)),
        max_length=int(lint_raw.get("max_length", 120)),
        no_duplicates=bool(lint_raw.get("no_duplicates", True)),
    )


def register_subcommand(changelog_subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register ``lint`` under a changelog sub-parser."""
    p = changelog_subparsers.add_parser(
        "lint",
        help="Lint changelog entries for style consistency.",
        description=(
            "Validate entries in [Unreleased] (or a named release) for style rules:\n"
            "sentence case, no trailing period, max length, and no duplicates."
        ),
    )
    p.add_argument(
        "--release",
        metavar="VERSION",
        default=None,
        help="Lint a specific named release section instead of [Unreleased].",
    )
    p.add_argument(
        "--no-fail",
        action="store_true",
        default=False,
        help="Report violations without exiting non-zero.",
    )
    p.add_argument("--group", metavar="NAME", default=None, help="Version group name.")
    p.set_defaults(handler=cmd_changelog_lint)
