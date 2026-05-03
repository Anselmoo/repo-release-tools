"""rrt docs — extract and manage source-owned documentation blocks.

## Overview

`rrt docs` extracts inline documentation blocks from source files across
Python, TypeScript/JavaScript, Go, and Rust using static regex analysis.
No runtime AST parsers are required.

## Sub-actions

### generate

Scan source files and emit documentation in the requested format.

```bash
rrt docs generate
rrt docs generate --format md
rrt docs generate --format json
rrt docs generate --format toml   # writes .rrt/docs.lock.toml
rrt docs generate --lang python,go
rrt docs generate --dry-run
```

### check

Verify the lockfile is current with the source tree. Exits 1 if stale.
Detects three lifecycle events that cause drift:

- **file added** — a source file has no entry in the lockfile
- **file deleted** — the lockfile references a file that no longer exists on disk
- **content modified** — a source file's hash does not match its lockfile entry

```bash
rrt docs check
rrt docs check --lock-file .rrt/docs.lock.toml
```

## Extraction modes

Controlled by `[tool.rrt.docs] extraction_mode` in config:

- `explicit` (default): only extract blocks preceded by a ``# sym: NAME``
  (Python) or ``// sym: NAME`` (JS/TS/Go/Rust) marker.
- `implicit`: extract language-native docstrings / comment blocks.
- `both`: explicit markers take priority; fall back to implicit.

## Lockfile

`rrt docs generate --format toml` writes `.rrt/docs.lock.toml` (by default),
a human-readable TOML file tracking each source file's SHA-256 hash and the
symbols it exports.  Use `rrt docs check` or the `rrt-docs-check` pre-commit
hook to fail fast when docs drift from source.

## Examples

```bash
rrt docs generate --format rich            # colourised terminal preview
rrt docs generate --format toml --dry-run  # show lock without writing
rrt docs check                             # exits 1 if lock is stale
```

## Related docs

- [CLI reference](rrt-cli.md)
- [Project tree command](tree.md)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools.config import DocsConfig, load_config
from repo_release_tools.docs_extractor import DocEntry, extract_docs_from_dir
from repo_release_tools.docs_formats import render
from repo_release_tools.state import build_lock, docs_lock_path, lock_is_current
from repo_release_tools.ui import DryRunPrinter, success, warning
from repo_release_tools.ui import error as color_error

# ---------------------------------------------------------------------------
# Source-owned topic docs (used by scripts/generate_cli_docs.py)
# ---------------------------------------------------------------------------

DOCS_OVERVIEW = """\
Extract inline documentation blocks from source files across
Python, TypeScript/JavaScript, Go, and Rust.

Usage:
  rrt docs generate [--format md|txt|rich|clipboard|json|toml]
  rrt docs check
"""

SOURCE_OWNED_TOPIC_DOCS = [
    ("docs", DOCS_OVERVIEW),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config_for_cwd(cwd: Path) -> DocsConfig:
    cfg = load_config(cwd)
    return cfg.docs if cfg.docs is not None else DocsConfig()


# ---------------------------------------------------------------------------
# generate sub-action
# ---------------------------------------------------------------------------


def _cmd_generate(args: argparse.Namespace) -> int:
    cwd = Path(args.root)
    p = DryRunPrinter(dry_run=args.dry_run)
    p.header("rrt docs generate")

    config = _config_for_cwd(cwd)

    # Override languages / formats from CLI if provided
    if getattr(args, "lang", None):
        raw_langs = [l.strip() for l in args.lang.split(",")]  # noqa: E741
        from repo_release_tools.config import _VALID_LANGUAGES

        invalid = [ln for ln in raw_langs if ln not in _VALID_LANGUAGES]
        if invalid:
            sys.stderr.write(
                color_error(
                    f"Unsupported languages: {invalid}. Supported: {list(_VALID_LANGUAGES)}\n"
                )
            )
            return 1
        from dataclasses import replace as dc_replace

        config = dc_replace(config, languages=tuple(raw_langs))

    fmt = getattr(args, "format", None) or config.formats[0]

    p.section("Scanning sources")
    entries = extract_docs_from_dir(cwd, config)
    if not entries:
        p.warn("No documentation entries found.")
        return 0

    p.ok(f"Found {len(entries)} doc entries")

    p.section(f"Rendering ({fmt})")

    if args.dry_run and fmt == "toml":
        # In dry-run mode: build lock but don't write
        from collections import defaultdict

        from repo_release_tools.state import hash_content

        by_file: dict[str, list[DocEntry]] = defaultdict(list)
        for entry in entries:
            by_file[entry.source_file].append(entry)

        sources = []
        for src_file, src_entries in by_file.items():
            combined = "".join(e.hash for e in sorted(src_entries, key=lambda e: e.name))
            sources.append(
                {
                    "source_file": src_file,
                    "hash": hash_content(combined),
                    "symbols": [e.name for e in src_entries],
                    "lang": src_entries[0].lang,
                }
            )
        build_lock(sources)  # validate structure; don't write
        lock_path = docs_lock_path(cwd, config.lock_file)
        p.would_write(str(lock_path), "docs lockfile (dry-run, not written)")
        return 0

    output = render(fmt, entries, config, root=cwd)

    if fmt in ("md", "txt", "json", "toml"):
        # Write to a sensible default output file or stdout
        if fmt == "toml":
            lock_path = docs_lock_path(cwd, config.lock_file)
            p.ok(f"Lockfile written: {lock_path}")
        else:
            sys.stdout.write(output)
    elif fmt == "rich":
        sys.stdout.write(output + "\n")
    elif fmt == "clipboard":
        sys.stdout.write(output)
        p.ok("Output written to stdout (pipe to clipboard utility if needed)")

    p.footer("Done.")
    return 0


# ---------------------------------------------------------------------------
# check sub-action
# ---------------------------------------------------------------------------


def _cmd_check(args: argparse.Namespace) -> int:
    cwd = Path(args.root)
    config = _config_for_cwd(cwd)

    lock_file = getattr(args, "lock_file", None) or config.lock_file
    lock_path = docs_lock_path(cwd, lock_file)

    entries = extract_docs_from_dir(cwd, config)

    from collections import defaultdict

    from repo_release_tools.state import hash_content

    by_file: dict[str, list[DocEntry]] = defaultdict(list)
    for entry in entries:
        by_file[entry.source_file].append(entry)

    sources = []
    for src_file, src_entries in by_file.items():
        combined = "".join(e.hash for e in sorted(src_entries, key=lambda e: e.name))
        sources.append(
            {
                "source_file": src_file,
                "hash": hash_content(combined),
                "symbols": [e.name for e in src_entries],
                "lang": src_entries[0].lang,
            }
        )

    is_current, messages = lock_is_current(lock_path, sources)
    if is_current:
        sys.stdout.write(success("docs lockfile is current\n"))
        return 0

    sys.stderr.write(color_error("docs lockfile is stale:\n"))
    for msg in messages:
        sys.stderr.write(f"  {warning(msg)}\n")
    sys.stderr.write(
        color_error("Run 'rrt docs generate --format toml' to regenerate the lockfile.\n")
    )
    return 1


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def cmd_docs(args: argparse.Namespace) -> int:
    """Dispatch rrt docs sub-actions."""
    sub = getattr(args, "docs_action", "generate")
    if sub == "generate":
        return _cmd_generate(args)
    if sub == "check":
        return _cmd_check(args)
    sys.stderr.write(color_error(f"Unknown docs action: {sub!r}\n"))
    return 1


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------

_FORMATS = ["md", "txt", "rich", "clipboard", "json", "toml"]

DOCS_EPILOG = """\
Examples:
  rrt docs generate                         # explicit mode, md output to stdout
  rrt docs generate --format toml           # write .rrt/docs.lock.toml
  rrt docs generate --format rich           # colourised terminal preview
  rrt docs check                            # exits 1 if lockfile is stale
  rrt docs generate --lang python,go        # multi-language extraction
"""


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the docs command."""
    parser = subparsers.add_parser(
        "docs",
        help="Extract and manage source-owned documentation blocks.",
        description=(
            "Scan source files and extract inline documentation blocks\n"
            "across Python, TypeScript/JavaScript, Go, and Rust.\n\n"
            "Sub-actions: generate (default), check"
        ),
        epilog=DOCS_EPILOG,
    )
    parser.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing files.",
    )

    sub = parser.add_subparsers(dest="docs_action")

    # ── generate ──────────────────────────────────────────────────────────
    gen_p = sub.add_parser(
        "generate",
        help="Extract docs and emit in the selected format.",
    )
    gen_p.add_argument(
        "--format",
        choices=_FORMATS,
        default=None,
        help="Output format (default: first format in config, usually md).",
    )
    gen_p.add_argument(
        "--lang",
        default=None,
        metavar="LANGS",
        help="Comma-separated language filter, e.g. python,go (overrides config).",
    )
    gen_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )
    gen_p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be done without writing files.",
    )

    # ── check ─────────────────────────────────────────────────────────────
    chk_p = sub.add_parser(
        "check",
        help="Exit 1 if the docs lockfile is stale.",
    )
    chk_p.add_argument(
        "--lock-file",
        default=None,
        metavar="PATH",
        help="Path to the lock file (default: from config or .rrt/docs.lock.toml).",
    )
    chk_p.add_argument(
        "--root",
        default=".",
        metavar="PATH",
        help="Project root directory (default: current directory).",
    )

    parser.set_defaults(handler=cmd_docs)
    gen_p.set_defaults(handler=cmd_docs)
    chk_p.set_defaults(handler=cmd_docs)
