"""Extra CLI commands that surface unused GlyphSet capabilities."""

from __future__ import annotations

import argparse
import itertools
import subprocess
import sys

from pathlib import Path

from repo_release_tools import output
from repo_release_tools.glyphs import GLYPHS, BoxStyle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_directory(
    root: Path,
    *,
    depth: int | None = None,
    show_all: bool = False,
    _current_depth: int = 0,
) -> list[tuple[str, bool, list | None]]:
    """Return a nested entry list suitable for ``TreeGlyphs.render``.

    Each entry is ``(name, is_dir, children_or_None)``.  Hidden entries
    (names starting with ``.``) are skipped unless *show_all* is True.
    Recursion stops when *depth* is reached (``None`` means unlimited).
    """
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return []

    result: list[tuple[str, bool, list | None]] = []
    for entry in entries:
        if not show_all and entry.name.startswith("."):
            continue
        if entry.is_dir():
            if depth is None or _current_depth < depth:
                children = _walk_directory(
                    entry,
                    depth=depth,
                    show_all=show_all,
                    _current_depth=_current_depth + 1,
                )
            else:
                children = None
            result.append((entry.name, True, children))
        else:
            result.append((entry.name, False, None))
    return result


def _git_diff_lines(
    root: Path,
    *,
    staged: bool = False,
    against: str | None = None,
) -> list[str]:
    """Return raw unified-diff lines from git."""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    if against:
        cmd.append(against)
    result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.splitlines()


def _parse_diff_entries(
    raw_lines: list[str],
) -> list[tuple[str, str, int | None]]:
    """Parse unified-diff output into ``(kind, text, lineno)`` tuples."""
    entries: list[tuple[str, str, int | None]] = []
    lineno: int | None = None
    for line in raw_lines:
        if line.startswith("@@"):
            # Extract the new-file start line from the hunk header.
            parts = line.split(" ")
            for part in parts:
                if part.startswith("+"):
                    try:
                        lineno = int(part.lstrip("+").split(",")[0])
                    except ValueError:
                        lineno = None
                    break
            continue
        if line.startswith("+++") or line.startswith("---") or line.startswith("diff "):
            continue
        if line.startswith("+"):
            entries.append(("added", line[1:], lineno))
            if lineno is not None:
                lineno += 1
        elif line.startswith("-"):
            entries.append(("removed", line[1:], None))
        else:
            if lineno is not None:
                lineno += 1
    return entries


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_tree(args: argparse.Namespace) -> int:
    """Print a directory tree rooted at the given path."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Path not found: {root}", file=sys.stderr)
        return 1
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    depth: int | None = None if args.all else args.depth
    entries = _walk_directory(root, depth=depth, show_all=args.all)
    print(str(root))
    if entries:
        print(GLYPHS.tree.render(entries))
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    """Print a progress bar for the given value (0.0–1.0)."""
    try:
        value = float(args.value)
    except ValueError:
        print(f"Invalid value: {args.value!r} (expected a number between 0 and 1)", file=sys.stderr)
        return 1
    print(GLYPHS.progress.render_bar(value, args.width))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Show a compact file-level diff using DiffGlyphs."""
    root = Path.cwd()
    raw_lines = _git_diff_lines(root, staged=args.staged, against=args.against)
    if not raw_lines:
        print(output.ok("No changes."))
        return 0
    entries = _parse_diff_entries(raw_lines)
    if not entries:
        print(output.ok("No changes."))
        return 0
    for kind, text, lineno in entries:
        print(GLYPHS.diff.line(kind, text, lineno))
    return 0


def cmd_panel(args: argparse.Namespace) -> int:
    """Render a styled key-value panel."""
    pairs = args.pairs
    if len(pairs) % 2 != 0:
        print("Pairs must be an even number of arguments: KEY VALUE ...", file=sys.stderr)
        return 1
    rows = [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]
    style: BoxStyle = args.style
    print(output.panel(args.title, rows, style=style))
    return 0


def cmd_glyph_preview(args: argparse.Namespace) -> int:  # noqa: ARG001
    """Render every glyph family as a terminal capability diagnostic."""
    g = GLYPHS
    lines: list[str] = []

    # Box styles
    lines.append(output.section("Box styles"))
    for label, box in [
        ("single", g.box),
        ("rounded", g.rounded_box),
        ("bold", g.bold_box),
    ]:
        sample = f"{box.h} {box.tl}{box.tr}{box.bl}{box.br} {box.left}{box.right}"
        lines.append(output.status(g.bullet.dot, f"{label:<8} {sample}"))

    # Bullets
    lines.append(output.section("Bullets"))
    bullet_parts = [
        f"ok {g.bullet.ok}",
        f"warn {g.bullet.warning}",
        f"error {g.bullet.error}",
        f"skip {g.bullet.skip}",
    ]
    lines.append(output.status(g.bullet.dot, "  ".join(bullet_parts)))

    # Progress
    lines.append(output.section("Progress"))
    lines.append(output.status(g.bullet.dot, g.progress.render_bar(0.5, 20)))
    spinner_frames = "  ".join(itertools.islice(g.progress.spinner(), 4))
    lines.append(output.status(g.bullet.dot, f"spinner: {spinner_frames}"))

    # Tree
    lines.append(output.section("Tree"))
    sample_tree = g.tree.render([
        ("src/", True, [("module.py", False, None)]),
        ("tests/", True, None),
    ])
    for tree_line in sample_tree.splitlines():
        lines.append(f"  {tree_line}")

    # Diff
    lines.append(output.section("Diff"))
    for kind, text in [
        ("added", "new line"),
        ("removed", "old line"),
        ("modified", "changed line"),
    ]:
        lines.append(f"  {g.diff.line(kind, text)}")

    # Git
    lines.append(output.section("Git"))
    lines.append(output.status(g.bullet.dot, g.git.status_line("main", ahead=1, modified=2)))
    lines.append(output.status(g.bullet.dot, g.git.log_line("abc1234", "feat: example")))

    # Typography
    lines.append(output.section("Typography"))
    lines.append(
        output.status(
            g.bullet.dot,
            f"ellipsis {g.typography.ellipsis}  mdash {g.typography.mdash}  "
            f"ndash {g.typography.ndash}",
        )
    )

    for line in lines:
        print(line)
    return 0


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the tree, progress, diff, panel, and glyph-preview commands."""

    # -- tree -----------------------------------------------------------------
    tree_parser = subparsers.add_parser(
        "tree",
        help="Print a directory tree.",
    )
    tree_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root directory to display (default: current directory).",
    )
    tree_parser.add_argument(
        "--depth",
        type=int,
        default=3,
        metavar="N",
        help="Maximum display depth (default: 3). Ignored when --all is set.",
    )
    tree_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all entries including hidden files and expand all directories.",
    )
    tree_parser.set_defaults(handler=cmd_tree)

    # -- progress -------------------------------------------------------------
    progress_parser = subparsers.add_parser(
        "progress",
        help="Render a progress bar to stdout.",
    )
    progress_parser.add_argument(
        "value",
        help="Progress value between 0.0 and 1.0.",
    )
    progress_parser.add_argument(
        "--width",
        type=int,
        default=20,
        metavar="N",
        help="Bar width in cells (default: 20).",
    )
    progress_parser.set_defaults(handler=cmd_progress)

    # -- diff -----------------------------------------------------------------
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show a compact git diff with DiffGlyphs.",
    )
    diff_parser.add_argument(
        "--staged",
        action="store_true",
        help="Show staged changes only.",
    )
    diff_parser.add_argument(
        "--against",
        default=None,
        metavar="REF",
        help="Compare against a specific ref (branch, tag, or commit).",
    )
    diff_parser.set_defaults(handler=cmd_diff)

    # -- panel ----------------------------------------------------------------
    panel_parser = subparsers.add_parser(
        "panel",
        help="Render a styled key-value panel.",
    )
    panel_parser.add_argument("--title", default="Panel", help="Panel title.")
    panel_parser.add_argument(
        "--style",
        choices=["single", "rounded", "bold", "mixed"],
        default="single",
        help="Box style (default: single).",
    )
    panel_parser.add_argument(
        "pairs",
        nargs="+",
        metavar="KEY_OR_VALUE",
        help="Alternating KEY VALUE pairs to display.",
    )
    panel_parser.set_defaults(handler=cmd_panel)

    # -- glyph-preview --------------------------------------------------------
    glyph_preview_parser = subparsers.add_parser(
        "glyph-preview",
        help="Render a terminal capability diagnostic showing all glyph families.",
    )
    glyph_preview_parser.set_defaults(handler=cmd_glyph_preview)
