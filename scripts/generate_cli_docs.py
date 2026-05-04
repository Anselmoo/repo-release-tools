#!/usr/bin/env python3
"""Backward-compatibility shim — all logic now lives in the rrt package.

The canonical entry points are:
  rrt docs publish          # generate and write CLI-reference docs
  rrt docs publish --check  # verify docs are up to date
  rrt docs inject           # inject shared anchor blocks
  rrt docs inject --check   # verify anchor blocks are up to date

This script is retained so that any external callers or poe tasks that still
reference ``generate_cli_docs`` continue to work during the transition period.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from repo_release_tools.docs_publisher import (  # noqa: F401 — re-export
    GENERATED_DOC_TARGETS,
    SOURCE_OWNED_TOPIC_DOCS,
    TOPIC_PAGE_OUTPUTS,
    DocTarget,
    HelpSection,
    generate_index_topic_links_markdown,
    generate_markdown,
    generate_readme_links_markdown,
    iter_generated_doc_targets,
    iter_help_sections,
    render_help,
)
from repo_release_tools.tools.inject import (  # noqa: F401 — re-export
    ANCHOR_END_TOKEN,
    ANCHOR_START_TOKEN,
    SupportsWrite,
    apply_generated_docs,
    replace_anchored_block,
)

# ---------------------------------------------------------------------------
# Poe task entry points (backward compat)
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT = Path("docs/commands/rrt-cli.md")


def task_generate() -> int:
    """Poe task: generate and write CLI reference docs."""
    from repo_release_tools import docs_publisher  # noqa: PLC0415

    exit_code = 0
    for target in docs_publisher.iter_generated_doc_targets():
        exit_code = max(
            exit_code,
            apply_generated_docs(
                target.render(),
                output_path=target.output_path,
                check=False,
                write=True,
                fail_on_change=False,
                stdout=sys.stdout,
                stderr=sys.stderr,
                anchor_id=target.anchor_id,
            ),
        )
    return exit_code


def task_check() -> int:
    """Poe task: verify all generated docs are up to date."""
    from repo_release_tools import docs_publisher  # noqa: PLC0415

    exit_code = 0
    for target in docs_publisher.iter_generated_doc_targets():
        exit_code = max(
            exit_code,
            apply_generated_docs(
                target.render(),
                output_path=target.output_path,
                check=True,
                write=False,
                fail_on_change=False,
                stdout=sys.stdout,
                stderr=sys.stderr,
                anchor_id=target.anchor_id,
            ),
        )
    return exit_code


def task_inject_shared_blocks() -> int:
    """Poe task: inject all shared anchor blocks."""
    return _apply_shared_blocks(check=False)


def task_check_shared_blocks() -> int:
    """Poe task: verify all shared anchor blocks are up to date."""
    return _apply_shared_blocks(check=True)


def _apply_shared_blocks(*, check: bool) -> int:
    """Inject or verify all shared anchor blocks defined in [tool.rrt.docs.shared_blocks]."""
    import repo_release_tools as rrt_package  # noqa: PLC0415
    from repo_release_tools.config import load_config  # noqa: PLC0415

    root = Path.cwd()
    try:
        cfg = load_config(root)
    except (FileNotFoundError, ValueError):
        sys.stdout.write("No rrt config found; skipping shared_blocks injection.\n")
        return 0

    if cfg.docs is None or not cfg.docs.shared_blocks:
        return 0

    repo_url = "https://github.com/Anselmoo/repo-release-tools"
    exit_code = 0
    for block in cfg.docs.shared_blocks:
        if block.template is not None:
            template_path = root / block.template
            if not template_path.exists():
                sys.stderr.write(
                    f"SharedBlock {block.anchor_id!r}: template {block.template!r} not found.\n"
                )
                exit_code = 1
                continue
            content = template_path.read_text(encoding="utf-8").rstrip("\n")
        else:
            assert block.content is not None
            content = block.content.rstrip("\n")

        content = content.replace("{version}", rrt_package.__version__)
        content = content.replace("{repo_url}", repo_url)

        matched = sorted({p for pattern in block.targets for p in root.glob(pattern)})
        if not matched:
            sys.stdout.write(f"SharedBlock {block.anchor_id!r}: no target files matched.\n")
            continue

        for target_path in matched:
            exit_code = max(
                exit_code,
                apply_generated_docs(
                    content,
                    output_path=target_path,
                    check=check,
                    write=not check,
                    fail_on_change=False,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                    anchor_id=block.anchor_id,
                ),
            )

    return exit_code


# ---------------------------------------------------------------------------
# Direct invocation (backward compat)
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the generator CLI parser."""
    parser = argparse.ArgumentParser(
        description="Generate docs/commands/rrt-cli.md from the live rrt parser."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination Markdown file. Defaults to docs/commands/rrt-cli.md.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the generated content differs from the on-disk file.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the generated content to disk. Default when --check is not used.",
    )
    parser.add_argument(
        "--fail-on-change",
        action="store_true",
        help="After writing, exit non-zero so hook workflows stop for re-staging.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI docs generator."""
    args = build_arg_parser().parse_args(list(argv) if argv is not None else None)
    write = args.write or not args.check
    return apply_generated_docs(
        generate_markdown(),
        output_path=args.output,
        check=args.check,
        write=write,
        fail_on_change=args.fail_on_change,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
