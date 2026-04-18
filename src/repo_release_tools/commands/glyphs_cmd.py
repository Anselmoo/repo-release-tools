"""Glyph-based utility commands for rrt.

Surfaces capabilities of the GlyphSet that were previously only available
as Python APIs:

* ``rrt tree``          — repo/directory tree view (TreeGlyphs)
* ``rrt progress``      — scriptable progress bar (ProgressGlyphs)
* ``rrt diff``          — compact git diff summary (DiffGlyphs)
* ``rrt panel``         — key-value panel renderer (BoxGlyphs / BoxStyle)
* ``rrt glyph-preview`` — terminal capability diagnostic (all glyph families)
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from repo_release_tools import git, output
from repo_release_tools.glyphs import GLYPHS, display_width


# ---------------------------------------------------------------------------
# rrt tree
# ---------------------------------------------------------------------------

_GITIGNORE_SKIP = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "*.egg-info",
    }
)


def _should_skip(name: str) -> bool:
    """Return True for names that should always be hidden from the tree."""
    return name in _GITIGNORE_SKIP or name.endswith(".egg-info")


def _build_tree(
    root: Path,
    *,
    max_depth: int,
    show_hidden: bool,
    current_depth: int = 0,
) -> list[tuple[str, bool, list | None]]:
    """Recursively build the tree entry list for TreeGlyphs.render()."""
    entries: list[tuple[str, bool, list | None]] = []
    try:
        children_raw = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return entries

    for child in children_raw:
        if not show_hidden and child.name.startswith("."):
            continue
        if _should_skip(child.name):
            continue

        if child.is_dir():
            if current_depth < max_depth:
                sub = _build_tree(
                    child,
                    max_depth=max_depth,
                    show_hidden=show_hidden,
                    current_depth=current_depth + 1,
                )
                entries.append((child.name, True, sub or None))
            else:
                entries.append((child.name, True, None))
        else:
            entries.append((child.name, False, None))
    return entries


def cmd_tree(args: argparse.Namespace) -> int:
    """Print a repo/directory tree using TreeGlyphs."""
    root = Path(args.path).resolve()
    if not root.exists():
        print(output.error(f"Path does not exist: {root}"), file=sys.stderr)
        return 1

    entries = _build_tree(root, max_depth=args.depth, show_hidden=args.all)
    if not entries:
        print(output.warning("Directory is empty."))
        return 0

    print()
    print(output.section(str(root.name)))
    print(GLYPHS.tree.render(entries))
    print()
    return 0


# ---------------------------------------------------------------------------
# rrt progress
# ---------------------------------------------------------------------------


def cmd_progress(args: argparse.Namespace) -> int:
    """Render a progress bar to stdout (useful in scripts and CI)."""
    try:
        value = float(args.value)
    except ValueError:
        print(
            output.error(f"Invalid value: {args.value!r} — expected a number between 0 and 1."),
            file=sys.stderr,
        )
        return 1

    if not 0.0 <= value <= 1.0:
        print(
            output.error(f"Value {value} is out of range — must be between 0.0 and 1.0."),
            file=sys.stderr,
        )
        return 1

    bar = GLYPHS.progress.render_bar(value, width=args.width)
    print(bar)
    return 0


# ---------------------------------------------------------------------------
# rrt diff
# ---------------------------------------------------------------------------


def _parse_diff_line(raw: str) -> tuple[str, str, int | None]:
    """Parse a unified diff header or context line into (kind, text, lineno)."""
    if raw.startswith("+++") or raw.startswith("---"):
        return ("unchanged", raw, None)
    if raw.startswith("@@"):
        # Extract new-file line number from @@ -a,b +c,d @@ context
        try:
            after_plus = raw.split("+")[1].split(",")[0].split(" ")[0]
            lineno = int(after_plus)
        except (IndexError, ValueError):
            lineno = None
        return ("unchanged", raw, lineno)
    if raw.startswith("+"):
        return ("added", raw[1:], None)
    if raw.startswith("-"):
        return ("removed", raw[1:], None)
    return ("unchanged", raw[1:] if raw.startswith(" ") else raw, None)


def cmd_diff(args: argparse.Namespace) -> int:
    """Show a compact git diff using DiffGlyphs."""
    root = Path.cwd()
    if not git.is_git_repository(root):
        print(f"{root} is not inside a Git work tree.", file=sys.stderr)
        return 1

    cmd = ["git", "diff", "--unified=3"]
    if args.staged:
        cmd.append("--staged")
    if args.against:
        cmd.append(args.against)

    raw = git.capture(cmd, root)
    if not raw.strip():
        print(output.ok("No diff to show."))
        return 0

    current_file: str = ""
    lineno: int = 0

    print()
    for raw_line in raw.splitlines():
        # File header
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            print()
            print(output.section(current_file))
            lineno = 0
            continue
        if (
            raw_line.startswith("--- ")
            or raw_line.startswith("diff ")
            or raw_line.startswith("index ")
        ):
            continue

        kind, text, hunk_start = _parse_diff_line(raw_line)
        if hunk_start is not None:
            lineno = hunk_start
            # Print the @@ header dimmed
            print(f"  {GLYPHS.typography.mdash} {text.strip()}")
            continue

        rendered = GLYPHS.diff.line(
            kind, text.rstrip(), lineno=lineno if kind != "unchanged" else None
        )
        print(f"  {rendered}")
        if kind != "removed":
            lineno += 1

    print()
    return 0


# ---------------------------------------------------------------------------
# rrt panel
# ---------------------------------------------------------------------------


def _parse_key_value_pairs(pairs: list[str]) -> list[tuple[str, str]]:
    """Convert a flat list [k1, v1, k2, v2, ...] to [(k1,v1), (k2,v2), ...]."""
    if len(pairs) % 2 != 0:
        raise ValueError(f"Expected an even number of KEY VALUE arguments, got {len(pairs)}.")
    return [(pairs[i], pairs[i + 1]) for i in range(0, len(pairs), 2)]


def cmd_panel(args: argparse.Namespace) -> int:
    """Render a styled key-value panel."""
    try:
        rows = _parse_key_value_pairs(args.pairs)
    except ValueError as exc:
        print(output.error(str(exc)), file=sys.stderr)
        return 1

    if not rows:
        print(output.warning("No rows to display."))
        return 0

    print()
    print(output.panel(args.title, rows, style=args.style))
    print()
    return 0


# ---------------------------------------------------------------------------
# rrt glyph-preview
# ---------------------------------------------------------------------------


def _preview_row(label: str, glyphs: str) -> str:
    """Format a label + glyph sample row."""
    return f"  {f'{label} '.ljust(12)} {glyphs}"


def cmd_glyph_preview(args: argparse.Namespace) -> int:
    """Render a terminal capability diagnostic showing all glyph families."""
    b = GLYPHS.box
    rb = GLYPHS.rounded_box
    bb = GLYPHS.bold_box

    print()
    print(output.section("Glyph preview"))

    # ── Box styles ──────────────────────────────────────────────────────────
    print(output.section("Box styles"))
    print(
        _preview_row(
            "single",
            f"{b.tl}{b.h * 3}{b.tr} {b.v} {b.bl}{b.h * 3}{b.br}  {b.cross} {b.top} {b.bottom} {b.left} {b.right}",
        )
    )
    print(
        _preview_row(
            "rounded",
            f"{rb.tl}{rb.h * 3}{rb.tr} {rb.v} {rb.bl}{rb.h * 3}{rb.br}  {rb.cross} {rb.top} {rb.bottom}",
        )
    )
    print(
        _preview_row(
            "bold",
            f"{bb.tl}{bb.h * 3}{bb.tr} {bb.v} {bb.bl}{bb.h * 3}{bb.br}  {bb.cross} {bb.top} {bb.bottom}",
        )
    )
    print(
        _preview_row(
            "double", f"{b.dtl}{b.dh * 3}{b.dtr} {b.dv} {b.dbl}{b.dh * 3}{b.dbr}  {b.dcross}"
        )
    )

    # ── Panel examples ───────────────────────────────────────────────────────
    print()
    print(output.section("Panel styles"))
    for style in ("single", "rounded", "bold", "mixed"):
        sample_rows = [("Style", style), ("Corners", "ok")]
        print(output.panel(style.capitalize(), sample_rows, style=style))  # type: ignore[arg-type]
        print()

    # ── Bullets ──────────────────────────────────────────────────────────────
    print(output.section("Bullets"))
    print(_preview_row("ok", str(GLYPHS.bullet.ok)))
    print(_preview_row("warning", str(GLYPHS.bullet.warning)))
    print(_preview_row("error", str(GLYPHS.bullet.error)))
    print(_preview_row("skip", str(GLYPHS.bullet.skip)))
    print(_preview_row("dot", str(GLYPHS.bullet.dot)))

    # ── Arrows ───────────────────────────────────────────────────────────────
    print()
    print(output.section("Arrows"))
    print(_preview_row("right", str(GLYPHS.arrow.right)))
    print(_preview_row("left", str(GLYPHS.arrow.left)))
    print(_preview_row("up/down", f"{GLYPHS.arrow.up}  {GLYPHS.arrow.down}"))

    # ── Diff ─────────────────────────────────────────────────────────────────
    print()
    print(output.section("Diff"))
    print(_preview_row("added", GLYPHS.diff.line("added", "new code", lineno=12)))
    print(_preview_row("removed", GLYPHS.diff.line("removed", "old code", lineno=11)))
    print(_preview_row("modified", GLYPHS.diff.line("modified", "changed", lineno=5)))
    print(_preview_row("renamed", f"{GLYPHS.diff.renamed} old.py  {GLYPHS.arrow.right}  new.py"))

    # ── Progress ─────────────────────────────────────────────────────────────
    print()
    print(output.section("Progress"))
    for pct in (0.0, 0.25, 0.5, 0.75, 1.0):
        print(_preview_row(f"{pct:.0%}", GLYPHS.progress.render_bar(pct, width=20)))

    # ── Typography ───────────────────────────────────────────────────────────
    print()
    print(output.section("Typography"))
    print(_preview_row("ellipsis", str(GLYPHS.typography.ellipsis)))
    print(_preview_row("mdash", str(GLYPHS.typography.mdash)))
    print(_preview_row("ndash", str(GLYPHS.typography.ndash)))

    # ── Tree ─────────────────────────────────────────────────────────────────
    print()
    print(output.section("Tree"))
    sample_tree: list[tuple[str, bool, list | None]] = [
        (
            "src",
            True,
            [
                ("module.py", False, None),
                ("utils.py", False, None),
            ],
        ),
        (
            "tests",
            True,
            [
                ("test_module.py", False, None),
            ],
        ),
        ("README.md", False, None),
    ]
    print(GLYPHS.tree.render(sample_tree))

    # ── Git ──────────────────────────────────────────────────────────────────
    print()
    print(output.section("Git"))
    print(_preview_row("status", GLYPHS.git.status_line("feat/example", ahead=2, modified=1)))
    print(_preview_row("log", GLYPHS.git.log_line("abc1234", "feat: add glyph preview", ("main",))))

    # ── Terminal info ─────────────────────────────────────────────────────────
    print()
    print(output.section("Terminal"))
    from repo_release_tools.glyphs import IS_LEGACY_TERMINAL, _AMBIGUOUS_IS_WIDE

    print(_preview_row("IS_LEGACY", str(IS_LEGACY_TERMINAL)))
    print(_preview_row("CJK_WIDE", str(_AMBIGUOUS_IS_WIDE)))
    print(_preview_row("width('─')", str(display_width("─"))))
    print()
    return 0


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register glyph-based commands."""

    # rrt tree
    tree_parser = subparsers.add_parser(
        "tree",
        help="Print a directory/repo tree view.",
    )
    tree_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Root path to render (default: current directory).",
    )
    tree_parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=4,
        help="Maximum depth to expand (default: 4).",
    )
    tree_parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Include hidden files and directories.",
    )
    tree_parser.set_defaults(handler=cmd_tree)

    # rrt progress
    progress_parser = subparsers.add_parser(
        "progress",
        help="Render a progress bar (value between 0.0 and 1.0).",
    )
    progress_parser.add_argument(
        "value",
        help="Progress value between 0.0 and 1.0.",
    )
    progress_parser.add_argument(
        "--width",
        type=int,
        default=20,
        help="Bar width in characters (default: 20).",
    )
    progress_parser.set_defaults(handler=cmd_progress)

    # rrt diff
    diff_parser = subparsers.add_parser(
        "diff",
        help="Show a compact git diff using rrt glyph formatting.",
    )
    diff_parser.add_argument(
        "--staged",
        action="store_true",
        help="Show staged changes instead of working-tree changes.",
    )
    diff_parser.add_argument(
        "--against",
        metavar="REF",
        default=None,
        help="Diff against a specific commit or ref.",
    )
    diff_parser.set_defaults(handler=cmd_diff)

    # rrt panel
    panel_parser = subparsers.add_parser(
        "panel",
        help="Render a styled key-value panel to stdout.",
    )
    panel_parser.add_argument(
        "--title",
        default="Summary",
        help="Panel title (default: Summary).",
    )
    panel_parser.add_argument(
        "--style",
        choices=("single", "rounded", "bold", "mixed"),
        default="single",
        metavar="STYLE",
        type=str,
        help="Box style: single, rounded, bold, or mixed (default: single).",
    )
    panel_parser.add_argument(
        "pairs",
        nargs="*",
        metavar="KEY VALUE",
        help="Key-value pairs to display (must come in pairs).",
    )
    panel_parser.set_defaults(handler=cmd_panel)

    # rrt glyph-preview
    preview_parser = subparsers.add_parser(
        "glyph-preview",
        help="Show a terminal capability diagnostic with all rrt glyph families.",
    )
    preview_parser.set_defaults(handler=cmd_glyph_preview)
