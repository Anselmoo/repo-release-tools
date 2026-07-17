"""Field-level manifest sync for values duplicated across independent JSON files.

## Overview

`rrt fields` keeps a single logical fact — a value embedded in more than one
JSON manifest — from silently drifting. The motivating case: a Claude Code
plugin marketplace's root `.claude-plugin/marketplace.json` lists each
plugin's `description`, copied by hand from that plugin's own
`plugin.json`. Nothing catches it when the two copies diverge.

This is the same shape of problem `rrt artifacts` and `rrt drift` already
solve — a sensitive value silently drifting from its source of truth — but
at individual JSON field granularity rather than whole-file content hash.

Unlike `rrt artifacts`, **there is no lockfile**. The source of truth is
itself a git-tracked file, so `--check` always compares the live source
field against each live target field directly, on every run.

## Configuration

Add `[[tool.rrt.field_targets]]` entries to `pyproject.toml` (or `.rrt.toml`):

```toml
[[tool.rrt.field_targets]]
source = "plugins/self-assess/.claude-plugin/plugin.json"
source_field = "description"
targets = [
  { path = ".claude-plugin/marketplace.json", field = "plugins[name=self-assess].description" },
  { path = "README.md", anchor = "self-assess-description" },
]
```

- `source` — relative path to the source-of-truth JSON file.
- `source_field` — a path into the parsed source JSON (see "Field path
  syntax" below).
- `targets` — a list of write destinations, each setting exactly one of:
  - `field` — a JSON target. `path` is the target JSON file; `field` uses
    the same path syntax as `source_field`.
  - `anchor` — a Markdown/MDX/RST target. `path` is the prose file; `anchor`
    is the anchor id of an `<!-- rrt:auto:start:<id> -->` /
    `{/* rrt:auto:start:<id> */}` / `.. rrt:auto:start:<id>` block already
    present in that file (format auto-detected from the file extension, the
    same primitive used by `rrt docs publish`/`inject` and `rrt tree
    --inject`). A target file missing the anchor markers fails loudly
    (exit 1) rather than being silently skipped.

### Field path syntax

Only two forms are supported, deliberately — this is a hand-rolled stdlib
resolver, not a general JSONPath/JMESPath engine (no new runtime
dependency is taken on for it):

- Dotted keys for nested objects: `author.name`
- One bracket-filter form, for selecting an array element by a matching
  field: `arrayKey[matchField=matchValue]` — selects the element of the
  array at `arrayKey` whose `matchField` equals `matchValue`. Chainable
  with further dotted segments, e.g. `plugins[name=self-assess].description`.

## Subcommands

- `--check` — resolve the source field and each target field, compare.
  Advisory by default (warns on mismatch, exits 0); `--strict` makes any
  mismatch exit 1 (for CI gates).
- `--sync` — overwrite each target field with the current source field
  value, in place, preserving the target file's existing key order and
  formatting (a value-only edit). Supports `--dry-run`.
- `--list` — show every configured `(source_field -> target.field)`
  mapping with its current match/mismatch status.

## Examples

```bash
rrt fields --check
rrt fields --check --strict
rrt fields --sync --dry-run
rrt fields --sync
rrt fields --list
```

## Caveats

- Only JSON source files are supported in this first pass (TOML/YAML sources
  are not handled). Targets may be JSON (`field`) or Markdown/MDX/RST
  (`anchor`).
- A `field` target path must resolve to an existing key on an existing
  object — `--sync` will not create new keys.
- An `anchor` target file must already contain the matching anchor marker
  pair; `--sync`/`--check` fail loudly rather than creating or skipping it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repo_release_tools.config import (
    RrtConfig,
    find_repo_root,
    load_or_autodetect_config,
)
from repo_release_tools.config.model import FieldTarget, FieldTargetEntry
from repo_release_tools.tools.inject import (
    _detect_inject_format,
    extract_anchored_block,
    replace_anchored_block,
)
from repo_release_tools.ui import (
    DryRunPrinter,
    VerbosePrinter,
    rule,
    terminal_width,
)

SOURCE_OWNED_TOPIC_DOCS: tuple[tuple[str, str], ...] = (("fields", __doc__ or ""),)
FIELDS_EPILOG = (
    "  $ rrt fields --check\n  $ rrt fields --check --strict\n"
    "  $ rrt fields --sync --dry-run\n  $ rrt fields --list"
)

# One path segment: a plain key, or an array-filter key[matchField=matchValue].
_SEGMENT_RE = re.compile(r"^([^.\[\]=]+)(?:\[([^.\[\]=]+)=([^\[\]]+)\])?$")


class FieldPathError(ValueError):
    """Raised when a field path segment cannot be resolved against JSON data."""


def _split_path(path: str) -> list[str]:
    """Split a field path into segments, on ``.`` outside of ``[...]``."""
    segments: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in path:
        if ch == "[":
            depth += 1
            current.append(ch)
        elif ch == "]":
            depth -= 1
            current.append(ch)
        elif ch == "." and depth == 0:
            segments.append("".join(current))
            current = []
        else:
            current.append(ch)
    segments.append("".join(current))
    return segments


def _parse_segment(segment: str) -> tuple[str, str | None, str | None]:
    """Parse one path segment into ``(key, match_field, match_value)``."""
    if not segment:
        raise FieldPathError("field path contains an empty segment")
    match = _SEGMENT_RE.match(segment)
    if not match:
        raise FieldPathError(f"invalid field path segment {segment!r}")
    key, match_field, match_value = match.groups()
    return key, match_field, match_value


def _step(current: Any, segment: str) -> Any:
    """Resolve one path segment against *current*, returning the next value."""
    key, match_field, match_value = _parse_segment(segment)
    if not isinstance(current, dict):
        raise FieldPathError(f"cannot look up key {key!r} on a non-object value")
    if key not in current:
        raise FieldPathError(f"key {key!r} not found")
    current = current[key]
    if match_field is None:
        return current
    if not isinstance(current, list):
        raise FieldPathError(f"{key!r} is not an array; cannot apply [{match_field}=...] filter")
    for item in current:
        if isinstance(item, dict) and str(item.get(match_field)) == match_value:
            return item
    raise FieldPathError(f"no element of {key!r} has {match_field}={match_value!r}")


def resolve_field(data: Any, path: str) -> Any:
    """Resolve *path* (dotted keys + one bracket-filter form) against *data*."""
    segments = _split_path(path)
    if not segments or not segments[0]:
        raise FieldPathError("field path must be a non-empty string")
    current = data
    for segment in segments:
        current = _step(current, segment)
    return current


def _navigate_to_parent(data: Any, segments: list[str]) -> tuple[Any, str]:
    """Walk all but the last segment; return ``(container, last_segment)``."""
    current = data
    for segment in segments[:-1]:
        current = _step(current, segment)
    return current, segments[-1]


def set_field(data: Any, path: str, value: Any) -> None:
    """Set *path* to *value* in-place on *data* (mutates existing keys only)."""
    segments = _split_path(path)
    if not segments or not segments[0]:
        raise FieldPathError("field path must be a non-empty string")
    parent, last_segment = _navigate_to_parent(data, segments)
    key, match_field, _match_value = _parse_segment(last_segment)
    if match_field is not None:
        raise FieldPathError(f"field path {path!r} must end in a plain key, not an array filter")
    if not isinstance(parent, dict):
        raise FieldPathError(f"cannot set key {key!r} on a non-object value")
    if key not in parent:
        raise FieldPathError(f"key {key!r} not found; --sync only updates existing keys")
    parent[key] = value


def _load_json_file(path: Path) -> Any:
    """Read and parse a JSON file, raising ``FieldPathError`` on failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FieldPathError(f"cannot read {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FieldPathError(f"invalid JSON in {path}: {exc}") from exc


def _write_json_file(path: Path, data: Any) -> None:
    """Write *data* back to *path* as 2-space-indented JSON with a trailing newline."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _read_text_file(path: Path) -> str:
    """Read a target file's raw text, raising ``FieldPathError`` on failure."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FieldPathError(f"cannot read {path}: {exc}") from exc


def _target_label(entry: FieldTargetEntry) -> str:
    """Return a human-readable label for a target entry: its field path or anchor id."""
    if entry.anchor is not None:
        return f"anchor:{entry.anchor}"
    return entry.field or ""


@dataclass(frozen=True)
class FieldComparison:
    """Result of comparing one target (a JSON field or an anchor block) against its source field."""

    source: str
    source_field: str
    target_path: str
    target_field: str | None = None
    target_anchor: str | None = None
    source_value: Any = None
    target_value: Any = None
    error: str | None = None

    @property
    def matches(self) -> bool:
        """Return whether the target currently matches the source field."""
        return self.error is None and self.source_value == self.target_value

    @property
    def target_label(self) -> str:
        """Return a human-readable label: the field path, or ``anchor:<id>``."""
        if self.target_anchor is not None:
            return f"anchor:{self.target_anchor}"
        return self.target_field or ""


def _compare_field_target(field_target: FieldTarget, root: Path) -> list[FieldComparison]:
    """Resolve one ``FieldTarget``'s source field and compare it to each of its targets."""
    source_path = root / field_target.source
    source_value: Any = None
    source_error: str | None = None
    try:
        source_data = _load_json_file(source_path)
        source_value = resolve_field(source_data, field_target.source_field)
    except FieldPathError as exc:
        source_error = f"{field_target.source}#{field_target.source_field}: {exc}"

    results: list[FieldComparison] = []
    for entry in field_target.targets:
        if source_error is not None:
            results.append(
                FieldComparison(
                    source=field_target.source,
                    source_field=field_target.source_field,
                    target_path=entry.path,
                    target_field=entry.field,
                    target_anchor=entry.anchor,
                    error=source_error,
                )
            )
            continue
        target_path = root / entry.path
        try:
            if entry.anchor is not None:
                text = _read_text_file(target_path)
                fmt = _detect_inject_format(target_path)
                extracted = extract_anchored_block(text, anchor_id=entry.anchor, fmt=fmt)
                if extracted is None:
                    raise FieldPathError(f"missing anchor markers for {entry.anchor!r}")
                results.append(
                    FieldComparison(
                        source=field_target.source,
                        source_field=field_target.source_field,
                        target_path=entry.path,
                        target_anchor=entry.anchor,
                        source_value=str(source_value).strip(),
                        target_value=extracted.strip(),
                    )
                )
            else:
                assert entry.field is not None  # exactly one of field/anchor per validate()
                target_data = _load_json_file(target_path)
                target_value = resolve_field(target_data, entry.field)
                results.append(
                    FieldComparison(
                        source=field_target.source,
                        source_field=field_target.source_field,
                        target_path=entry.path,
                        target_field=entry.field,
                        source_value=source_value,
                        target_value=target_value,
                    )
                )
        except ValueError as exc:
            results.append(
                FieldComparison(
                    source=field_target.source,
                    source_field=field_target.source_field,
                    target_path=entry.path,
                    target_field=entry.field,
                    target_anchor=entry.anchor,
                    source_value=source_value,
                    error=f"{entry.path}#{_target_label(entry)}: {exc}",
                )
            )
    return results


def _compare_field_targets(field_targets: list[FieldTarget], root: Path) -> list[FieldComparison]:
    """Flatten comparisons across every configured ``field_targets`` entry."""
    comparisons: list[FieldComparison] = []
    for field_target in field_targets:
        comparisons.extend(_compare_field_target(field_target, root))
    return comparisons


@dataclass(frozen=True)
class Options:
    """Typed view of ``argparse.Namespace`` for ``rrt fields``.

    Built once via :meth:`from_args` at the top of :func:`cmd_fields` so every
    flag has a single, typed read site instead of scattered
    ``getattr(args, ..., default)`` calls throughout the function body.
    """

    verbose: int
    check: bool
    sync: bool
    list: bool
    dry_run: bool
    strict: bool

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Options:
        """Build an :class:`Options` from a parsed ``argparse.Namespace``."""
        return cls(
            verbose=getattr(args, "verbose", 0) or 0,
            check=getattr(args, "check", False),
            sync=getattr(args, "sync", False),
            list=getattr(args, "list", False),
            dry_run=getattr(args, "dry_run", False),
            strict=getattr(args, "strict", False),
        )


def _run_fields_check(
    p: VerbosePrinter,
    field_targets: list[FieldTarget],
    root: Path,
    *,
    strict: bool,
) -> int:
    """Compare every configured field mapping and report drift.

    Advisory by default (exits 0 on mismatch, warns); ``--strict`` makes any
    drift or resolution error an error (exit 1), for CI gates.
    """
    comparisons = _compare_field_targets(field_targets, root)
    problems = [c for c in comparisons if not c.matches]
    if not problems:
        p.line(f"All {len(comparisons)} field mapping(s) verified — no drift detected.", ok=True)
        return 0

    for c in problems:
        if c.error:
            msg = f"{c.source}#{c.source_field} -> {c.target_path}#{c.target_label}: {c.error}"
        else:
            msg = (
                f"{c.source}#{c.source_field} -> {c.target_path}#{c.target_label}: "
                f"mismatch (source={c.source_value!r}, target={c.target_value!r})"
            )
        if strict:
            p.line(msg, ok=False, stream=sys.stderr)
        else:
            p.warn(msg)

    if strict:
        p.line(
            f"{len(problems)} field mismatch(es) found. Run --sync to update.",
            ok=False,
            stream=sys.stderr,
        )
        return 1
    p.blank_line()
    p.warn("⊙ [advisory] Field drift detected — run rrt fields --sync to update.")
    return 0


def _run_fields_sync(
    field_targets: list[FieldTarget],
    root: Path,
    *,
    dry_run: bool,
) -> int:
    """Write every target field to match its current source field value."""
    rp = DryRunPrinter(dry_run=dry_run)
    rp.header("Sync field targets")

    comparisons = _compare_field_targets(field_targets, root)
    errors = [c for c in comparisons if c.error]
    for c in errors:
        rp.line(
            f"{c.source}#{c.source_field} -> {c.target_path}#{c.target_label}: {c.error}",
            ok=False,
            stream=sys.stderr,
        )
    if errors:
        return 1

    loaded: dict[Path, Any] = {}
    loaded_text: dict[Path, str] = {}
    written = 0
    unchanged = 0
    for c in comparisons:
        if c.matches:
            unchanged += 1
            continue
        target_path = root / c.target_path
        if dry_run:
            rp.would_write(c.target_path, f"{c.target_label} = {c.source_value!r}")
            written += 1
            continue
        if c.target_anchor is not None:
            text = loaded_text.get(target_path)
            if text is None:
                text = target_path.read_text(encoding="utf-8")
            fmt = _detect_inject_format(target_path)
            updated = replace_anchored_block(
                text, anchor_id=c.target_anchor, content=str(c.source_value), fmt=fmt
            )
            # The anchor markers were already confirmed present for this exact
            # (path, anchor_id, fmt) during the error-gated comparison above,
            # so replace_anchored_block cannot return None here.
            assert updated is not None
            loaded_text[target_path] = updated
            written += 1
            continue
        assert c.target_field is not None  # target_anchor is None, so this is a JSON target
        data = loaded.get(target_path)
        if data is None:
            data = _load_json_file(target_path)
            loaded[target_path] = data
        set_field(data, c.target_field, c.source_value)
        written += 1

    if not dry_run:
        for target_path, data in loaded.items():
            _write_json_file(target_path, data)
        for target_path, text in loaded_text.items():
            target_path.write_text(text, encoding="utf-8")

    if written == 0:
        rp.footer(f"All {unchanged} field mapping(s) already in sync — nothing to write.")
        return 0

    total_files = len(loaded) + len(loaded_text)
    if dry_run:
        rp.footer(f"Would update {written} field(s); {unchanged} already in sync.")
    else:
        rp.footer(
            f"Updated {written} field(s) across {total_files} target file(s); "
            f"{unchanged} already in sync."
        )
    return 0


def _print_field_list(field_targets: list[FieldTarget], root: Path) -> None:
    """Print a status table of every configured field mapping."""
    width = terminal_width()
    p = VerbosePrinter()
    p.line(f"[FIELDS] {len(field_targets)} source field(s) configured", ok=True)
    p.blank_line()

    for field_target in field_targets:
        label = f"{field_target.source}#{field_target.source_field}"
        p.line(rule(label, width=width))
        for c in _compare_field_target(field_target, root):
            label_text = f"{c.target_path}#{c.target_label}"
            if c.error:
                p.line(f"{label_text:<60}  {c.error}", ok=False)
            elif c.matches:
                p.line(f"{label_text:<60}  ✓", ok=True)
            else:
                p.line(f"{label_text:<60}  MISMATCH", ok=False)


def cmd_fields(args: argparse.Namespace) -> int:
    """Run field-level manifest sync check, sync, or list."""
    opts = Options.from_args(args)
    p = VerbosePrinter(verbose=opts.verbose)

    if opts.dry_run and not opts.sync:
        p.line(
            "--dry-run requires --sync; it has no effect with --check or --list",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    root = find_repo_root(Path.cwd())

    try:
        config: RrtConfig = load_or_autodetect_config(root)
    except Exception as exc:
        p.line(str(exc), ok=False, stream=sys.stderr)
        return 1

    field_targets = config.field_targets

    if not field_targets:
        p.warn("No field_targets configured in [tool.rrt]. Nothing to track.")
        return 0

    if opts.check:
        return _run_fields_check(p, field_targets, root, strict=opts.strict)

    if opts.sync:
        return _run_fields_sync(field_targets, root, dry_run=opts.dry_run)

    if opts.list:
        _print_field_list(field_targets, root)
        return 0

    # Default: same as --check, but always advisory (never exits 1),
    # mirroring rrt artifacts' bare-invocation status summary.
    return _run_fields_check(p, field_targets, root, strict=False)


def _add_fields_strict_argument(parser: argparse.ArgumentParser, *, default: bool) -> None:
    """Register the ``strict`` flag on ``parser`` with the caller's chosen default/polarity.

    Mirrors :func:`repo_release_tools.commands.artifacts_cmd._add_artifacts_strict_argument`
    exactly — a human running ``rrt fields --check`` expects advisory output
    unless they opt into a hard gate with ``--strict``.
    """
    if default:
        parser.add_argument(
            "--no-strict",
            dest="strict",
            action="store_false",
            default=True,
            help="Downgrade failures to warnings instead of exiting 1.",
        )
    else:
        parser.add_argument(
            "--strict",
            dest="strict",
            action="store_true",
            default=False,
            help="With --check: exit 1 on any field mismatch (for CI gates).",
        )


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the fields subcommand."""
    parser = subparsers.add_parser(
        "fields",
        help="Field-level manifest sync for values duplicated across JSON files.",
        description=(
            "Check or sync a JSON field value that's duplicated as a copy across\n"
            "one or more other JSON files. No lockfile — the source file is the\n"
            "source of truth, compared live on every run."
        ),
        epilog=FIELDS_EPILOG,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        default=False,
        help="Compare each target field against its source field. Advisory by default.",
    )
    mode.add_argument(
        "--sync",
        action="store_true",
        default=False,
        help="Write each target field to match its current source field value.",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="Display all configured field mappings and their current match status.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what --sync would do without writing any files.",
    )
    _add_fields_strict_argument(parser, default=False)
    parser.set_defaults(handler=cmd_fields)
