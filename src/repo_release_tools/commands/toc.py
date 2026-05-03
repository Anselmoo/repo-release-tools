"""``rrt toc`` — generate and inject a Markdown table of contents.

## Overview

``rrt toc FILE`` reads a Markdown file and prints a nested bullet list of its
headings to stdout.  With ``--inject`` and ``--anchor``, the generated TOC is
written in-place inside a marked anchor block in a target file.

## Usage

```
rrt toc FILE [--min-level N] [--max-level N]
rrt toc FILE --inject TARGET --anchor ID [--min-level N] [--max-level N] [--dry-run]
```

## Anchors

Place a pair of HTML comments in the target file to mark where the TOC
should live:

```markdown
<!-- rrt:auto:start:toc -->
<!-- rrt:auto:end:toc -->
```

The content between the markers is replaced on every ``rrt toc --inject`` run.
Everything outside the markers is preserved unchanged.

## Options

| Flag | Default | Description |
|---|---|---|
| ``FILE`` | — | Markdown file to parse for headings |
| ``--inject FILE`` | — | Target file to update in-place |
| ``--anchor ID`` | — | Anchor ID inside the inject target |
| ``--min-level N`` | 1 | Shallowest heading level to include (1 = ``#``) |
| ``--max-level N`` | 6 | Deepest heading level to include (6 = ``######``) |
| ``--dry-run`` | — | Print result instead of writing (requires ``--inject``) |

``--inject`` and ``--anchor`` must always be used together.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repo_release_tools.tools.inject import (
    ANCHOR_END_TOKEN,
    ANCHOR_START_TOKEN,
    replace_anchored_block,
)
from repo_release_tools.tools.toc import parse_headings, render_toc
from repo_release_tools.ui import DryRunPrinter

TOC_EPILOG = (
    "  $ rrt toc README.md\n"
    "  $ rrt toc README.md --min-level 2 --max-level 3\n"
    "  $ rrt toc README.md --inject README.md --anchor toc\n"
    "  $ rrt toc README.md --inject README.md --anchor toc --dry-run"
)


def cmd_toc(args: argparse.Namespace) -> int:
    """Generate a Markdown TOC from FILE, optionally injecting it into TARGET."""
    p = DryRunPrinter(getattr(args, "dry_run", False))

    inject_file: str | None = getattr(args, "inject", None)
    anchor_id: str | None = getattr(args, "anchor", None)

    if bool(inject_file) != bool(anchor_id):
        p.line(
            "--inject and --anchor must be used together.",
            ok=False,
            stream=sys.stderr,
        )
        return 1

    source = Path(args.file)
    if not source.exists():
        p.line(f"Source file does not exist: {source}", ok=False, stream=sys.stderr)
        return 1

    text = source.read_text(encoding="utf-8")
    headings = parse_headings(text)
    toc = render_toc(headings, min_level=args.min_level, max_level=args.max_level)

    if not toc:
        p.line("No headings found in the requested level range.", ok=False, stream=sys.stderr)
        return 1

    if inject_file and anchor_id:
        target = Path(inject_file)
        if not target.exists():
            p.line(f"Inject target does not exist: {target}", ok=False, stream=sys.stderr)
            return 1

        existing = target.read_text(encoding="utf-8")
        updated = replace_anchored_block(existing, anchor_id=anchor_id, content=toc)
        if updated is None:
            p.line(
                f"{target} is missing anchor "
                f"<!-- {ANCHOR_START_TOKEN}{anchor_id} --> / "
                f"<!-- {ANCHOR_END_TOKEN}{anchor_id} -->.",
                ok=False,
                stream=sys.stderr,
            )
            return 1

        p.header("Generate TOC", Source=str(source), Target=str(target), Anchor=anchor_id)
        p.section("Changes")
        if p.dry_run:
            p.would_write(str(target), f"anchor {anchor_id!r}")
            p.blank_line()
            sys.stdout.write(updated)
        else:
            target.write_text(updated, encoding="utf-8")
        p.footer(f"Done. Updated anchor {anchor_id!r} in {target.name}.")
        return 0

    sys.stdout.write(toc + "\n")
    return 0


def register(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the ``toc`` subcommand on *sub*."""
    parser: argparse.ArgumentParser = sub.add_parser(
        "toc",
        help="Generate a Markdown table of contents from headings.",
        description=(
            "Read a Markdown file and print a nested bullet-list TOC to stdout.\n\n"
            "With --inject and --anchor the generated TOC is written in-place inside\n"
            "an anchor block in a target file.  Markers delimit the block:\n\n"
            "  <!-- rrt:auto:start:ID -->\n"
            "  <!-- rrt:auto:end:ID -->\n\n"
            "Everything outside the markers is preserved unchanged.\n"
            "--inject and --anchor must always be used together."
        ),
        epilog=TOC_EPILOG,
    )
    parser.add_argument(
        "file",
        metavar="FILE",
        help="Markdown file to parse for headings.",
    )
    parser.add_argument(
        "--inject",
        default=None,
        metavar="FILE",
        help=(
            "Markdown file to update in-place. Requires --anchor. "
            "The anchored block is replaced; all other content is preserved."
        ),
    )
    parser.add_argument(
        "--anchor",
        default=None,
        metavar="ID",
        help=(
            "Anchor ID to replace inside the --inject file. "
            f"Place <!-- {ANCHOR_START_TOKEN}<ID> --> and "
            f"<!-- {ANCHOR_END_TOKEN}<ID> --> markers in the target file."
        ),
    )
    parser.add_argument(
        "--min-level",
        type=int,
        default=1,
        metavar="N",
        help="Shallowest heading level to include (default: 1 = #).",
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=6,
        metavar="N",
        help="Deepest heading level to include (default: 6 = ######).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the result instead of writing (only effective with --inject).",
    )
    parser.set_defaults(handler=cmd_toc)
